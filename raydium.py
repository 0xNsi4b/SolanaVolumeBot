import json

import base58
import requests
from solana.rpc.api import Client
from solana.rpc.commitment import Commitment
from solders.keypair import Keypair
from spl.token.core import _TokenCore
from spl.token.instructions import create_associated_token_account, get_associated_token_address, CloseAccountParams, \
    close_account
from spl.token.client import Token
from solana.transaction import Transaction
from solders.instruction import AccountMeta, Instruction
from solana.rpc.types import TokenAccountOpts
from solders.pubkey import Pubkey
from construct import Int8ul, Int64ul
from construct import Struct as cStruct


AMM_PROGRAM_ID = Pubkey.from_string('675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8')
SERUM_PROGRAM_ID = Pubkey.from_string('srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX')

SWAP_LAYOUT = cStruct(
    "instruction" / Int8ul,
    "amount_in" / Int64ul,
    "min_amount_out" / Int64ul
)


def extract_pool_info(pools_list: list, mint: str) -> dict:
    for pool in pools_list:
        if pool['baseMint'] == mint and pool['quoteMint'] == 'So11111111111111111111111111111111111111112':
            return pool
        elif pool['quoteMint'] == mint and pool['baseMint'] == 'So11111111111111111111111111111111111111112':
            return pool
    raise Exception(f'{mint} pool not found!')


def sell_get_token_account(ctx,
                           owner: Pubkey.from_string,
                           mint: Pubkey.from_string):
    try:
        account_data = ctx.get_token_accounts_by_owner(owner, TokenAccountOpts(mint))
        return account_data.value[0].pubkey
    except:
        print("Mint Token Not found")
        return None


def get_token_account(ctx,
                      owner: Pubkey.from_string,
                      mint: Pubkey.from_string):
    try:
        account_data = ctx.get_token_accounts_by_owner(owner, TokenAccountOpts(mint))
        return account_data.value[0].pubkey, None
    except:
        swap_associated_token_address = get_associated_token_address(owner, mint)
        swap_token_account_instructions = create_associated_token_account(owner, owner, mint)
        return swap_associated_token_address, swap_token_account_instructions


def fetch_pool_keys(mint: str) -> dict:
    amm_info = {}
    all_pools = {}
    resp = requests.get('https://api.raydium.io/v2/sdk/liquidity/mainnet.json', stream=True)
    pools = resp.json()
    official = pools['official']
    unofficial = pools['unOfficial']
    all_pools = official + unofficial
    try:
        amm_info = extract_pool_info(all_pools, mint)
    except:
        return "failed"

    return {
        'amm_id': Pubkey.from_string(amm_info['id']),
        'authority': Pubkey.from_string(amm_info['authority']),
        'base_mint': Pubkey.from_string(amm_info['baseMint']),
        'base_decimals': amm_info['baseDecimals'],
        'quote_mint': Pubkey.from_string(amm_info['quoteMint']),
        'quote_decimals': amm_info['quoteDecimals'],
        'lp_mint': Pubkey.from_string(amm_info['lpMint']),
        'open_orders': Pubkey.from_string(amm_info['openOrders']),
        'target_orders': Pubkey.from_string(amm_info['targetOrders']),
        'base_vault': Pubkey.from_string(amm_info['baseVault']),
        'quote_vault': Pubkey.from_string(amm_info['quoteVault']),
        'market_id': Pubkey.from_string(amm_info['marketId']),
        'market_base_vault': Pubkey.from_string(amm_info['marketBaseVault']),
        'market_quote_vault': Pubkey.from_string(amm_info['marketQuoteVault']),
        'market_authority': Pubkey.from_string(amm_info['marketAuthority']),
        'bids': Pubkey.from_string(amm_info['marketBids']),
        'asks': Pubkey.from_string(amm_info['marketAsks']),
        'event_queue': Pubkey.from_string(amm_info['marketEventQueue'])
    }


def make_swap_instruction(amount_in: int, token_account_in: Pubkey.from_string, token_account_out: Pubkey.from_string,
                          accounts: dict, mint, ctx, wallet) -> Instruction:

    account_program_id = ctx.get_account_info_json_parsed(mint)
    TOKEN_PROGRAM_ID = account_program_id.value.owner

    keys = [
        AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["amm_id"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["authority"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["open_orders"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["target_orders"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["base_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["quote_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=SERUM_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["market_id"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["bids"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["asks"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["event_queue"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["market_base_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["market_quote_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["market_authority"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=token_account_in, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_account_out, is_signer=False, is_writable=True),
        AccountMeta(pubkey=wallet.pubkey(), is_signer=True, is_writable=False)
    ]
    data = SWAP_LAYOUT.build(
        dict(
            instruction=9,
            amount_in=int(amount_in),
            min_amount_out=0
        )
    )
    return Instruction(AMM_PROGRAM_ID, data, keys)


def sell(conn, wallet, token, amount):
    mint = Pubkey.from_string(token)
    sol = Pubkey.from_string("So11111111111111111111111111111111111111112")

    # Get swap token program id
    token_program_id = conn.get_account_info_json_parsed(mint).value.owner

    # Get Pool Keys
    pool_keys = fetch_pool_keys(str(mint))
    if pool_keys == "failed":
        print(f"a|Sell Pool ERROR {token}", f"[Raydium]: Pool Key Not Found")
        return "failed"

    swap_token_account = sell_get_token_account(conn, wallet.pubkey(), mint)
    WSOL_token_account, WSOL_token_account_Instructions = get_token_account(conn, wallet.pubkey(), sol)

    if swap_token_account is None:
        print("swap_token_account not found...")
        return "failed"

    # Make swap instructions
    instructions_swap = make_swap_instruction(
        amount,
        swap_token_account,
        WSOL_token_account,
        pool_keys,
        mint,
        conn,
        wallet
    )

    # Close wsol account
    params = CloseAccountParams(account=WSOL_token_account, dest=wallet.pubkey(), owner=wallet.pubkey(),
                                            program_id=token_program_id)
    close_acc = (close_account(params))

    swap_tx = Transaction()
    signers = [wallet]
    if WSOL_token_account_Instructions is not None:
        swap_tx.add(WSOL_token_account_Instructions)
    swap_tx.add(instructions_swap)
    swap_tx.add(close_acc)

    # Execute Transaction
    txn = conn.send_transaction(swap_tx, *signers)
    print(f"Sell: {Pubkey.from_string(token)} Tx: https://solscan.io/tx/{txn.value}")


def buy(conn, wallet, from_token, amount):
    mint = Pubkey.from_string(from_token)

    # Get swap token program id
    account_program_id = conn.get_account_info_json_parsed(mint)
    token_program_id = account_program_id.value.owner

    pool_keys = fetch_pool_keys(str(mint))
    if pool_keys == "failed":
        print(f"a|BUY Pool ERROR {from_token}", f"[Raydium]: Pool Key Not Found")
        return "failed"

    # Set Mint Token accounts addresses
    swap_associated_token_address, swap_token_account_instructions = get_token_account(conn,
                                                                                       wallet.pubkey(), mint)

    balance_needed = Token.get_min_balance_rent_for_exempt_for_account(conn)
    WSOL_token_account, swap_tx, payer, Wsol_account_keyPair, opts, = _TokenCore._create_wrapped_native_account_args(
        token_program_id, wallet.pubkey(), wallet, amount,
        False, balance_needed, Commitment("confirmed"))

    # Create Swap Instructions
    instructions_swap = make_swap_instruction(amount,
                                              WSOL_token_account,
                                              swap_associated_token_address,
                                              pool_keys,
                                              mint,
                                              conn,
                                              wallet
                                              )

    params = CloseAccountParams(account=WSOL_token_account, dest=payer.pubkey(), owner=payer.pubkey(),
                                program_id=token_program_id)

    close_acc = (close_account(params))

    if swap_token_account_instructions is not None:
        swap_tx.add(swap_token_account_instructions)
    swap_tx.add(instructions_swap)
    swap_tx.add(close_acc)

    # Execute Transaction
    txn = conn.send_transaction(swap_tx, payer, Wsol_account_keyPair)
    print(f"Buy: {Pubkey.from_string(from_token)} Tx: https://solscan.io/tx/{txn.value}")

