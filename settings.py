# settings.py

# RPC endpoint for the Solana cluster
RPC = ""

# Token address to trade
TOKEN_ADDRESS = ""

# Allowed slippage percentage for trades
SLIPPAGE = 10

# Amount of SOL to spend when buying the token
SOL_IN = 0.0001

# Range for the percentage of tokens to sell (if a sale is triggered, a random percentage in this range is chosen)
SELL_PERCENTAGE_MIN = 50  # minimum sale percentage
SELL_PERCENTAGE_MAX = 100  # maximum sale percentage

# Probability that a sale operation is executed after a purchase (0.0 to 1.0)
SELL_PROBABILITY = 0.5

# Number of trade cycles to perform.
# If set to 0 or None, the cycles will run indefinitely.
CYCLES = 10

# Delay between trade cycles in seconds
DELAY_BETWEEN_ROUNDS = 5

# File path containing private keys (one per line in Base58 format)
PRIVATE_KEYS_FILE = "private_keys.txt"

# Maximum number of concurrent tasks (simulating multithreading)
THREADS = 5