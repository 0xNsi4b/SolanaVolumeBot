import requests
from solana.transaction import Transaction
from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey
from construct import Struct as cStruct
from construct import Int8ul, Int64ul

AMM_PROGRAM_ID = Pubkey.from_string('675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8')
TOKEN_PROGRAM_ID = Pubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA')
SERUM_PROGRAM_ID = Pubkey.from_string('srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX')

SWAP_LAYOUT = cStruct(
    "instruction" / Int8ul,
    "amount_in" / Int64ul,
    "min_amount_out" / Int64ul
)


def extract_pool_info(pools_list: list, pool_id: str) -> dict:
    for pool in pools_list:
        if pool['id'] == pool_id:
            return pool
    raise Exception(f'{pool_id} pool not found!')


def fetch_pool_keys(pool_id: str) -> dict:
    pools = requests.get('https://api.raydium.io/v2/sdk/liquidity/mainnet.json').json()['official']
    amm_info = extract_pool_info(pools, pool_id)
    return {
        'amm_id': Pubkey.from_string(pool_id),
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


def make_swap_instruction(wallet, amount_in: int, token_account_in: Pubkey, token_account_out: Pubkey,
                          accounts: dict) -> Instruction:
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


def buy(conn, wallet, from_token, to_token, amount):
    swap_tx = Transaction()
    pool_keys = fetch_pool_keys('58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2')
    signers = [wallet]
    token_account_in = from_token
    token_account_out = to_token
    amount_in = amount * 10 ** pool_keys['quote_decimals']
    instruction = make_swap_instruction(wallet, amount_in, token_account_in, token_account_out, pool_keys)
    swap_tx.add(instruction)
    return conn.send_transaction(swap_tx, *signers)
