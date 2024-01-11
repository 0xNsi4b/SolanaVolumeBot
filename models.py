import base64
import random
import time
import base58
import requests
import solders
import pandas as pd
from solana.rpc.commitment import Commitment
from solana.rpc.types import TxOpts, TokenAccountOpts
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from raydium import buy, sell


def get_sol_balance():
    jupiter_quote_api = "https://price.jup.ag/v4/price"
    quote_response = requests.get(jupiter_quote_api,
                                  params={'ids': 'SOL'})
    return quote_response.json()['data']['SOL']['price']


def get_quote_response(from_token, to_token, amount):
    jupiter_quote_api = "https://quote-api.jup.ag/v6/quote"
    quote_response = requests.get(jupiter_quote_api,
                                  params={'inputMint': from_token, 'outputMint': to_token, 'amount': amount})
    return quote_response.json()


def read_csv():
    return pd.read_csv('settings.csv').to_dict('records')[0]


def get_balance(connection, owner, token):
    balance_pubkey = connection.get_token_accounts_by_owner(owner, TokenAccountOpts(Pubkey.from_string(token)))
    if len(balance_pubkey.value) == 0:
        return 0, 0
    b = connection.get_token_account_balance(balance_pubkey.value[0].pubkey)
    return int(b.value.amount), float(b.value.ui_amount)


def read_lst():
    with open('private_keys.txt') as file:
        file_list = file.readlines()
    return [line.strip() for line in file_list]


def raydium_swap(connection, wallet, from_token, to_token, amount):
    amount = int(amount)
    if from_token == 'So11111111111111111111111111111111111111112':
        buy(connection, wallet, to_token, amount)
    elif from_token == 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB':
        sell(connection, wallet, from_token, amount)
        time.sleep(random.randint(25, 40))
        balance = int(connection.get_balance(wallet.pubkey()).value * 0.85)
        amount = balance / (10 ** 9)
        buy(connection, wallet, to_token, amount)
    else:
        sell(connection, wallet, from_token, amount)
        time.sleep(random.randint(25, 40))
        balance = int(connection.get_balance(wallet.pubkey()).value * 0.85)
        amount = balance / (10 ** 9)
        buy(connection, wallet, 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB', amount)


def jupiter_swap(connection, wallet, from_token, to_token, amount):

    transaction_parameters = {
        "quoteResponse": get_quote_response(from_token, to_token, amount),
        "userPublicKey": wallet.pubkey().__str__(),
        "wrapUnwrapSOL": True
    }

    swap_transaction = requests.post(url='https://quote-api.jup.ag/v6/swap',
                                     json=transaction_parameters).json()['swapTransaction']

    raw_tx = VersionedTransaction.from_bytes(base64.b64decode(swap_transaction))
    signature = wallet.sign_message(solders.message.to_bytes_versioned(raw_tx.message))
    signed_tx = VersionedTransaction.populate(raw_tx.message, [signature])
    tx_id = connection.send_raw_transaction(bytes(signed_tx),
                                            opts=TxOpts(skip_confirmation=False,
                                                        preflight_commitment=Commitment("confirmed")))
    print(f"From: {from_token} To: {to_token} Tx: https://solscan.io/tx/{tx_id.value}")


def run_swapper(token, key, settings):
    sol = 'So11111111111111111111111111111111111111112'
    usdt = 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'

    if settings['usdt']:
        amount, num = swapper(usdt, token, key, settings)
        value_token = amount * num
    else:
        amount, num = swapper(sol, token, key, settings)
        value_token = amount * num * float(get_sol_balance())

    return value_token


def swapper(token_volume, my_token, key, settings):
    wallet = Keypair.from_bytes(base58.b58decode(key))
    connection = Client("https://mainnet.helius-rpc.com/?api-key=33f03c8f-affc-40da-8784-8a3d7e8af61b")
    balance, amount = get_balance(connection, wallet.pubkey(), my_token)
    num = 0

    if settings['raydium']:
        swap = raydium_swap
        print('d')
    else:
        swap = jupiter_swap
        print('s')

    if balance > 0:
        swap(connection, wallet, token_volume, my_token, str(balance))
        time.sleep(random.randint(25, 40))
        num += 1

    if token_volume == 'So11111111111111111111111111111111111111112':
        balance = int(connection.get_balance(wallet.pubkey()).value * 0.85)
        amount = balance / (10 ** 9)
    else:
        balance, amount = get_balance(connection, wallet.pubkey(), token_volume)

    swap(connection, wallet, token_volume, my_token, str(balance))
    num += 1
    time.sleep(random.randint(25, 40))
    balance, a = get_balance(connection, wallet.pubkey(), my_token)
    if random.randint(0, 1):
        swap(connection, wallet, my_token, token_volume, str(balance))
        num += 1
    return float(amount), num


def main():
    lst = read_lst()
    print(lst)
    settings = read_csv()
    token = settings['token']

    value = float(settings['value'])
    value_done = 0
    while value > value_done:
        try:
            if len(lst) > 1:
                key = lst.pop(0)
                lst.append(key)
                value_done += run_swapper(token, key, settings)
                print(value_done)
                time.sleep(random.randint(settings['sleep_min'], settings['sleep_max']))
            else:
                value_done += run_swapper(token, lst[0], settings)
                print(value_done)
                time.sleep(random.randint(settings['sleep_min'], settings['sleep_max']))
        except Exception as error:
            print(f'Error {error}')


if __name__ == '__main__':
    main()
            