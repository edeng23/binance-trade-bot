from datetime import datetime

from binance_trade_bot import backtest

if __name__ == "__main__":
    resulting_balances = backtest(datetime(2021, 1, 1), datetime.now())
    print(resulting_balances)
