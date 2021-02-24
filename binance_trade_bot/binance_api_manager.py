import math
import time
from logging import Logger

from binance.client import Client
from binance.exceptions import BinanceAPIException

from .database import TradeLog
from .models import Coin


class BinanceApiManager:
    def __init__(self, api_key: str, api_secret_key: str, tld: str, logger: Logger):
        self.client = Client(api_key, api_secret_key, tld=tld)
        self.logger = logger

    def get_all_market_tickers(self):
        """
        Get ticker price of all coins
        """
        return self.client.get_all_tickers()

    def get_market_ticker_price(self, ticker_symbol):
        """
        Get ticker price of a specific coin
        """
        for ticker in self.client.get_symbol_ticker():
            if ticker["symbol"] == ticker_symbol:
                return float(ticker["price"])
        return None

    def get_currency_balance(self, currency_symbol: str):
        """
        Get balance of a specific coin
        """
        for currency_balance in self.client.get_account()["balances"]:
            if currency_balance["asset"] == currency_symbol:
                return float(currency_balance["free"])
        return None

    def retry(self, func, *args, **kwargs):
        time.sleep(1)
        attempts = 0
        while attempts < 20:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.info("Failed to Buy/Sell. Trying Again.")
                if attempts == 0:
                    self.logger.info(e)
                attempts += 1

    def wait_for_order(self, alt_symbol, crypto_symbol, order):
        while True:
            try:
                time.sleep(3)
                stat = self.client.get_order(
                    symbol=alt_symbol + crypto_symbol, orderId=order["orderId"]
                )
                break
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(10)
            except Exception as e:
                self.logger.info("Unexpected Error: {0}".format(e))

        self.logger.info(stat)

        while stat["status"] != "FILLED":
            try:
                stat = self.client.get_order(
                    symbol=alt_symbol + crypto_symbol, orderId=order["orderId"]
                )
                time.sleep(1)
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(2)
            except Exception as e:
                self.logger.info(f"Unexpected Error: {e}")

        return stat

    def get_ticks(self, alt_symbol, crypto_symbol):
        ticks = {}
        for filt in self.client.get_symbol_info(alt_symbol + crypto_symbol)["filters"]:
            if filt["filterType"] == "LOT_SIZE":
                ticks[alt_symbol] = filt["stepSize"].find("1") - 2
                break
        return ticks

    def buy_alt(self, alt: Coin, crypto: Coin):
        return self.retry(self._buy_alt, alt, crypto)

    def _buy_alt(self, alt: Coin, crypto: Coin):
        """
        Buy altcoin
        """
        trade_log = TradeLog(alt, crypto, False)
        alt_symbol = alt.symbol
        crypto_symbol = crypto.symbol

        ticks = self.get_ticks(alt_symbol, crypto_symbol)

        alt_balance = self.get_currency_balance(alt_symbol)
        crypto_balance = self.get_currency_balance(crypto_symbol)

        order_quantity = math.floor(
            crypto_balance
            * 10 ** ticks[alt_symbol]
            / self.get_market_ticker_price(alt_symbol + crypto_symbol)
        ) / float(10 ** ticks[alt_symbol])
        self.logger.info(f"BUY QTY {order_quantity}")

        # Try to buy until successful
        order = None
        while order is None:
            try:
                order = self.client.order_limit_buy(
                    symbol=alt_symbol + crypto_symbol,
                    quantity=order_quantity,
                    price=self.get_market_ticker_price(alt_symbol + crypto_symbol),
                )
                self.logger.info(order)
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(1)
            except Exception as e:
                self.logger.info(f"Unexpected Error: {e}")

        trade_log.set_ordered(alt_balance, crypto_balance, order_quantity)

        stat = self.wait_for_order(alt_symbol, crypto_symbol, order)

        self.logger.info(f"Bought {alt_symbol}")

        trade_log.set_complete(stat["cummulativeQuoteQty"])

        return order

    def sell_alt(self, alt: Coin, crypto: Coin):
        return self.retry(self._sell_alt, alt, crypto)

    def _sell_alt(self, alt: Coin, crypto: Coin):
        """
        Sell altcoin
        """
        trade_log = TradeLog(alt, crypto, True)
        alt_symbol = alt.symbol
        crypto_symbol = crypto.symbol

        ticks = self.get_ticks(alt_symbol, crypto_symbol)

        order_quantity = math.floor(
            self.get_currency_balance(alt_symbol) * 10 ** ticks[alt_symbol]
        ) / float(10 ** ticks[alt_symbol])
        self.logger.info(f"Selling {order_quantity} of {alt_symbol}")

        alt_balance = self.get_currency_balance(alt_symbol)
        crypto_balance = self.get_currency_balance(crypto_symbol)
        self.logger.info(f"Balance is {alt_balance}")
        order = None
        while order is None:
            order = self.client.order_market_sell(
                symbol=alt_symbol + crypto_symbol, quantity=order_quantity
            )

        self.logger.info("order")
        self.logger.info(order)

        trade_log.set_ordered(alt_balance, crypto_balance, order_quantity)

        # Binance server can take some time to save the order
        self.logger.info("Waiting for Binance")
        time.sleep(5)

        stat = self.wait_for_order(alt_symbol, crypto_symbol, order)

        new_balance = self.get_currency_balance(alt_symbol)
        while new_balance >= alt_balance:
            new_balance = self.get_currency_balance(alt_symbol)

        self.logger.info(f"Sold {alt_symbol}")

        trade_log.set_complete(stat["cummulativeQuoteQty"])

        return order
