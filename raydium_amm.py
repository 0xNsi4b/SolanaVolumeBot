import aiohttp
import logging
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed
from solana.rpc.types import TokenAccountOpts

from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from spl.token.instructions import (
    CloseAccountParams,
    close_account,
    create_associated_token_account,
    get_associated_token_address
)

from config import UNIT_BUDGET, UNIT_PRICE
from constants import SOL
from solana_helpers import create_wsol_account_instructions, compile_and_send_transaction, \
    get_token_balance
from constants import TOKEN_PROGRAM_ID, RAY_AUTHORITY_V4, OPEN_BOOK_PROGRAM, RAY_V4
from layouts import SWAP_LAYOUT, MARKET_STATE_LAYOUT_V3, LIQUIDITY_STATE_LAYOUT_V4

logger = logging.getLogger(__name__)


def calculate_transaction_amounts(amount_in: float, in_reserve, out_reserve,
                                  slippage: int):
    logging.debug(f"Calculating amounts: amount_in={amount_in}, in_reserve={in_reserve}, "
                  f"out_reserve={out_reserve}, slippage={slippage}")
    constant_product = in_reserve * out_reserve
    new_in_reserve = in_reserve + amount_in
    new_out_reserve = constant_product / new_in_reserve
    amount_out = out_reserve - new_out_reserve
    minimum_amount_out = amount_out * (1 - slippage / 100)

    logging.debug(f"Calculated values: effective_amount_in={amount_in}, "
                  f"amount_out={amount_out}, minimum_amount_out={minimum_amount_out}")
    return amount_in, minimum_amount_out

async def get_reserve(client: AsyncClient, pool_keys: dict) -> tuple:
    try:
        base_vault = pool_keys["base_vault"]
        quote_vault = pool_keys["quote_vault"]
        base_decimal = pool_keys["base_decimals"]
        quote_decimal = pool_keys["quote_decimals"]
        base_mint = pool_keys["base_mint"]

        balances_response = await client.get_multiple_accounts_json_parsed(
            [base_vault, quote_vault],
            Processed
        )
        balances = balances_response.value

        pool_coin_account = balances[0]
        pool_pc_account = balances[1]

        pool_coin_account_balance = pool_coin_account.data.parsed['info']['tokenAmount']['uiAmount']
        pool_pc_account_balance = pool_pc_account.data.parsed['info']['tokenAmount']['uiAmount']

        sol_mint_address = Pubkey.from_string(SOL)

        if base_mint == sol_mint_address:
            base_reserve = pool_coin_account_balance
            quote_reserve = pool_pc_account_balance
            token_decimal = quote_decimal
        else:
            base_reserve = pool_pc_account_balance
            quote_reserve = pool_coin_account_balance
            token_decimal = base_decimal

        return base_reserve, quote_reserve, token_decimal

    except Exception as e:
        logging.error(f"Error occurred: {e}")

def make_swap_instruction(amount_in: int, minimum_amount_out: int, token_account_in: Pubkey,
                                token_account_out: Pubkey, accounts: dict, owner: Keypair) -> Instruction | None:
    keys = [
        AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["amm_id"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=RAY_AUTHORITY_V4, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["open_orders"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["target_orders"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["base_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["quote_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=OPEN_BOOK_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["market_id"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["bids"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["asks"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["event_queue"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["market_base_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["market_quote_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["market_authority"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=token_account_in, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_account_out, is_signer=False, is_writable=True),
        AccountMeta(pubkey=owner.pubkey(), is_signer=True, is_writable=False)
    ]

    data = SWAP_LAYOUT.build(
        dict(
            instruction=9,
            amount_in=amount_in,
            min_amount_out=minimum_amount_out
        )
    )
    return Instruction(RAY_V4, data, keys)


async def fetch_pool_keys(client: AsyncClient, pair_address: str) -> dict:
    amm_id = Pubkey.from_string(pair_address)
    account_info = await client.get_account_info_json_parsed(amm_id)
    amm_data_decoded = LIQUIDITY_STATE_LAYOUT_V4.parse(account_info.value.data)
    market_id = Pubkey.from_bytes(amm_data_decoded.serumMarket)
    market_info = await client.get_account_info_json_parsed(market_id)
    market_decoded = MARKET_STATE_LAYOUT_V3.parse(market_info.value.data)

    pool_keys = {
        "amm_id": amm_id,
        "base_mint": Pubkey.from_bytes(market_decoded.base_mint),
        "quote_mint": Pubkey.from_bytes(market_decoded.quote_mint),
        "base_decimals": amm_data_decoded.coinDecimals,
        "quote_decimals": amm_data_decoded.pcDecimals,
        "open_orders": Pubkey.from_bytes(amm_data_decoded.ammOpenOrders),
        "target_orders": Pubkey.from_bytes(amm_data_decoded.ammTargetOrders),
        "base_vault": Pubkey.from_bytes(amm_data_decoded.poolCoinTokenAccount),
        "quote_vault": Pubkey.from_bytes(amm_data_decoded.poolPcTokenAccount),
        "withdrawQueue": Pubkey.from_bytes(amm_data_decoded.poolWithdrawQueue),
        "market_id": market_id,
        "market_authority": Pubkey.create_program_address(
            [bytes(market_id)] + [bytes([market_decoded.vault_signer_nonce])] + [bytes(7)], OPEN_BOOK_PROGRAM),
        "market_base_vault": Pubkey.from_bytes(market_decoded.base_vault),
        "market_quote_vault": Pubkey.from_bytes(market_decoded.quote_vault),
        "bids": Pubkey.from_bytes(market_decoded.bids),
        "asks": Pubkey.from_bytes(market_decoded.asks),
        "event_queue": Pubkey.from_bytes(market_decoded.event_queue)
    }

    return pool_keys


async def get_pool_keys(base_mint):
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{base_mint}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
        if len(data.get('pairs', [])) == 0:
            return None
        raydium_pairs = [
            pair for pair in data['pairs']
            if pair.get('dexId') == 'raydium' and pair.get('quoteToken', {}).get('address') == SOL
        ]
        if not raydium_pairs:
            return None
        raydium_pair_id = raydium_pairs[0]['pairAddress']
        logging.debug(f"Raydium pair: {raydium_pair_id}")
        return raydium_pair_id
    except Exception as e:
        logging.error(f"Error in fetching price of pool: {e}")
        return None


async def _process_start_swap(client: AsyncClient, token_address: str):
    pair_address = await get_pool_keys(token_address)
    if not pair_address:
        logging.critical("No pair address found...")
        return False

    pool_keys = await fetch_pool_keys(client, pair_address)
    if not pool_keys:
        logging.critical("No pool keys found...")
        return False

    logging.debug(f"Fetched pool keys: {pool_keys}")

    mint = pool_keys['base_mint'] if str(pool_keys['base_mint']) != SOL else pool_keys['quote_mint']
    logging.debug(f"Selected mint: {mint}")
    return mint, pool_keys


async def buy(client: AsyncClient, key_pair: Keypair, token_address: str, sol_in: float, slippage: int) -> bool:
    try:
        logging.info(f"Starting buy transaction for token: {token_address}")
        mint, pool_keys = await _process_start_swap(client, token_address)
        token_account_check = await client.get_token_accounts_by_owner(key_pair.pubkey(),
                                                                       TokenAccountOpts(mint),
                                                                       Processed)
        if token_account_check.value:
            token_account = token_account_check.value[0].pubkey
            token_account_instr = None
            logging.debug(f"Found existing token account: {token_account}")
        else:
            token_account = get_associated_token_address(key_pair.pubkey(), mint)
            token_account_instr = create_associated_token_account(key_pair.pubkey(), key_pair.pubkey(), mint)
            logging.debug(f"Creating associated token account: {token_account}")

        base_reserve, quote_reserve, token_decimal = await get_reserve(client, pool_keys)
        amount_in, minimum_amount_out = calculate_transaction_amounts(sol_in, base_reserve, quote_reserve, slippage)
        amount_in = int(amount_in * (10 ** 9))
        minimum_amount_out = int(minimum_amount_out * (10 ** token_decimal))

        wsol_token_account, wsol_instr = create_wsol_account_instructions(key_pair, amount_in)
        swap_instr = make_swap_instruction(amount_in, minimum_amount_out, wsol_token_account, token_account, pool_keys, key_pair)
        close_instr = close_account(CloseAccountParams(TOKEN_PROGRAM_ID, wsol_token_account, key_pair.pubkey(), key_pair.pubkey()))

        instructions = [
            set_compute_unit_limit(UNIT_BUDGET),
            set_compute_unit_price(UNIT_PRICE),
            *wsol_instr,
            swap_instr,
            close_instr
        ]
        if token_account_instr:
            instructions.insert(4, token_account_instr)
            logging.debug(f"Added token account instruction for: {token_account}")

        await compile_and_send_transaction(client, key_pair, instructions)

    except Exception as e:
        logging.error(f"Error during buy transaction: {e}")
        return False


async def sell(client: AsyncClient, key_pair: Keypair, token_address: str, percentage: int, slippage: int) -> bool:
    try:
        logging.info(f"Starting sell transaction for token: {token_address}")
        mint, pool_keys = await _process_start_swap(client, token_address)
        token_balance = await get_token_balance(client, key_pair, mint)
        if token_balance == 0:
            logging.critical("No token balance available to sell.")
            return False
        token_in = token_balance * percentage / 100
        logging.debug(f"Token amount: {token_balance}")
        base_reserve, quote_reserve, token_decimal = await get_reserve(client, pool_keys)

        amount_in, minimum_amount_out = calculate_transaction_amounts(token_in, quote_reserve, base_reserve, slippage)

        token_account = get_associated_token_address(key_pair.pubkey(), mint)
        wsol_token_account, wsol_instr = create_wsol_account_instructions(key_pair,  0)

        amount_in = int(amount_in * (10 ** token_decimal))
        minimum_amount_out = int(minimum_amount_out * (10 ** 9))
        swap_instr =  make_swap_instruction(amount_in, minimum_amount_out, token_account,
                                            wsol_token_account, pool_keys, key_pair)
        create_instr, sync_instr, close_instr = wsol_instr
        instructions = [
            set_compute_unit_limit(UNIT_BUDGET),
            set_compute_unit_price(UNIT_PRICE),
            create_instr,
            swap_instr,
            close_instr,
        ]
        if percentage == 100:
            close_token_instr = close_account(CloseAccountParams(
                account=token_account,
                dest=key_pair.pubkey(),
                owner=key_pair.pubkey(),
                program_id=TOKEN_PROGRAM_ID))
            instructions.append(close_token_instr)
            logging.debug(f"Added close token account instruction for: {token_account}")

        await compile_and_send_transaction(client, key_pair, instructions)


    except Exception as e:
        logging.error(f"Error during sell transaction: {e}")
        return False