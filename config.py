import os
from dotenv import load_dotenv

load_dotenv()
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
RPC = os.getenv("RPC")
UNIT_BUDGET = 100_000
UNIT_PRICE = 1_000_000


if not PRIVATE_KEY or not RPC:
    raise EnvironmentError("PRIVATE_KEY and RPC environment variables must be set")
