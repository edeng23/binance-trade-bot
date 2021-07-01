from datetime import datetime

from binance_trade_bot import backtest

if __name__ == "__main__":
    history = []
    for manager in backtest(datetime(2021, 3, 1), datetime(2021, 5, 28)):
        btc_value = manager.collate_coins("BTC")
        bridge_value = manager.collate_coins(manager.config.BRIDGE.symbol)
        btc_fees_value = manager.collate_fees("BTC")
        bridge_fees_value = manager.collate_fees(manager.config.BRIDGE.symbol)
        trades = manager.trades
        history.append((btc_value, bridge_value, trades, btc_fees_value, bridge_fees_value))
        btc_diff = round((btc_value - history[0][0]) / history[0][0] * 100, 3)
        bridge_diff = round((bridge_value - history[0][1]) / history[0][1] * 100, 3)
        print("------")
        print("TIME:", manager.datetime)
        print("TRADES:", trades)
        print("PAID FEES:", manager.paid_fees)
        print("BTC FEES VALUE:", btc_fees_value)
        print(f"{manager.config.BRIDGE.symbol} FEES VALUE:", bridge_fees_value)
        print("BALANCES:", manager.balances)
        print("BTC VALUE:", btc_value, f"({btc_diff}%)")
        print(f"{manager.config.BRIDGE.symbol} VALUE:", bridge_value, f"({bridge_diff}%)")
        print("------")
