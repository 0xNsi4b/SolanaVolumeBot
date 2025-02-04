import logging

from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts, TokenAccountOpts
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.token.associated import get_associated_token_address
from solders.transaction import VersionedTransaction
from spl.token.instructions import create_associated_token_account, \
    sync_native, SyncNativeParams, close_account, CloseAccountParams

from constants import TOKEN_PROGRAM_ID, WSOL


logger = logging.getLogger(__name__)

async def get_token_balance(client: AsyncClient, key_pair: Keypair, mint: Pubkey):
    try:
        pubkey_str = key_pair.pubkey()
        response = await client.get_token_accounts_by_owner(pubkey_str, TokenAccountOpts(mint=mint))
        if response.value:
            token_account_pubkey = response.value[0].pubkey
            balance_info = await client.get_token_account_balance(token_account_pubkey)
            return balance_info.value.ui_amount
        else:
            logging.info(f"No token accounts found for {pubkey_str}")
            return 0
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return 0

def create_wsol_account_instructions(key_pair: Keypair, amount_in):
    wsol_token_account = get_associated_token_address(key_pair.pubkey(), WSOL)
    create_instr = create_associated_token_account(
        payer=key_pair.pubkey(),
        owner=key_pair.pubkey(),
        mint=WSOL
    )
    transfer_instr = transfer(
        TransferParams(
            from_pubkey=key_pair.pubkey(),
            to_pubkey=wsol_token_account,
            lamports=amount_in
        )
    )
    sync_instr = sync_native(
        SyncNativeParams(
            account=wsol_token_account,
            program_id=TOKEN_PROGRAM_ID)
    )
    close_instr = close_account(
        CloseAccountParams(account=wsol_token_account,
                           dest=key_pair.pubkey(),
                           owner=key_pair.pubkey(),
                           program_id=TOKEN_PROGRAM_ID)
    )
    if amount_in > 0:
        wsol_inst = [create_instr, transfer_instr, sync_instr]
    else:
        wsol_inst = [create_instr, sync_instr, close_instr]
    logging.debug(f"Generated WSOL account instructions for {wsol_token_account}")
    return wsol_token_account, wsol_inst

async def compile_and_send_transaction(client: AsyncClient, key_pair: Keypair, instructions):
    logging.debug("Compiling transaction message...")
    latest_blockhash = await client.get_latest_blockhash()
    compiled_message = MessageV0.try_compile(
        key_pair.pubkey(),
        instructions,
        [],
        latest_blockhash.value.blockhash,
    )
    logging.debug("Sending transaction...")
    txn = VersionedTransaction(compiled_message, [key_pair])
    response = await client.simulate_transaction(txn)
    logging.info(f"{response}")
    txn_send = await client.send_transaction(txn, opts=TxOpts(skip_preflight=True))
    logging.info(f"Transaction Signature: https://solscan.io/tx/{txn_send.value}")
    return txn_send.value