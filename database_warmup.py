
import os

from binance_trade_bot import warmup_database

if __name__ == "__main__":
    warmup_database()
    os._exit(os.EX_OK)