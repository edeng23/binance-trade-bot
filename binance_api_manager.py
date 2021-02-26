from binance.client import Client
from binance.exceptions import BinanceAPIException
from database import TradeLog
from models import Coin
from logger import Logger
import math, requests, time


class BinanceAPIManager:
    def __init__(self, APIKey: str, APISecret: str, Tld: str, logger: Logger):
        self.BinanceClient = Client(APIKey, APISecret, None, Tld)
        self.logger = logger

    def get_all_market_tickers(self):
        """
        Get ticker price of all coins
        """
        return self.BinanceClient.get_all_tickers()

    def get_market_ticker_price(self, ticker_symbol: str):
        """
        Get ticker price of a specific coin
        """
        for ticker in self.BinanceClient.get_symbol_ticker():
            if ticker[u"symbol"] == ticker_symbol:
                return float(ticker[u"price"])
        return None

    def get_currency_balance(self, currency_symbol: str):
        """
        Get balance of a specific coin
        """
        for currency_balance in self.BinanceClient.get_account()[u"balances"]:
            if currency_balance[u"asset"] == currency_symbol:
                return float(currency_balance[u"free"])
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
        return None

    def buy_alt(self, alt: Coin, crypto: Coin):
        return self.retry(self._buy_alt, alt, crypto)

    def _buy_alt(self, alt: Coin, crypto: Coin):
        """
        Buy altcoin
        """
        trade_log = TradeLog(alt, crypto, False)
        alt_symbol = alt.symbol
        crypto_symbol = crypto.symbol
        ticks = {}
        for filt in self.BinanceClient.get_symbol_info(alt_symbol + crypto_symbol)[
            "filters"
        ]:
            if filt["filterType"] == "LOT_SIZE":
                if filt["stepSize"].find("1") == 0:
                    ticks[alt_symbol] = 1 - filt["stepSize"].find(".")
                else:
                    ticks[alt_symbol] = filt["stepSize"].find("1") - 1
                break

        alt_balance = self.get_currency_balance(alt_symbol)
        crypto_balance = self.get_currency_balance(crypto_symbol)

        order_quantity = math.floor(
            crypto_balance
            * 10 ** ticks[alt_symbol]
            / self.get_market_ticker_price(alt_symbol + crypto_symbol)
        ) / float(10 ** ticks[alt_symbol])
        self.logger.info("BUY QTY {0}".format(order_quantity))

        # Try to buy until successful
        order = None
        while order is None:
            try:
                order = self.BinanceClient.order_limit_buy(
                    symbol=alt_symbol + crypto_symbol,
                    quantity=order_quantity,
                    price=self.get_market_ticker_price(alt_symbol + crypto_symbol),
                )
                self.logger.info(order)
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(1)
            except Exception as e:
                self.logger.info("Unexpected Error: {0}".format(e))

        trade_log.set_ordered(alt_balance, crypto_balance, order_quantity)

        order_recorded = False
        while not order_recorded:
            try:
                time.sleep(3)
                stat = self.BinanceClient.get_order(
                    symbol=alt_symbol + crypto_symbol, orderId=order[u"orderId"]
                )
                order_recorded = True
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(10)
            except Exception as e:
                self.logger.info("Unexpected Error: {0}".format(e))
        while stat[u"status"] != "FILLED":
            try:
                stat = self.BinanceClient.get_order(
                    symbol=alt_symbol + crypto_symbol, orderId=order[u"orderId"]
                )
                time.sleep(1)
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(2)
            except Exception as e:
                self.logger.info("Unexpected Error: {0}".format(e))

        self.logger.info("Bought {0}".format(alt_symbol))

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
        ticks = {}
        for filt in self.BinanceClient.get_symbol_info(alt_symbol + crypto_symbol)[
            "filters"
        ]:
            if filt["filterType"] == "LOT_SIZE":
                if filt["stepSize"].find("1") == 0:
                    ticks[alt_symbol] = 1 - filt["stepSize"].find(".")
                else:
                    ticks[alt_symbol] = filt["stepSize"].find("1") - 1
                break

        order_quantity = math.floor(
            self.get_currency_balance(alt_symbol) * 10 ** ticks[alt_symbol]
        ) / float(10 ** ticks[alt_symbol])
        self.logger.info("Selling {0} of {1}".format(order_quantity, alt_symbol))

        alt_balance = self.get_currency_balance(alt_symbol)
        crypto_balance = self.get_currency_balance(crypto_symbol)
        self.logger.info("Balance is {0}".format(alt_balance))
        order = None
        while order is None:
            order = self.BinanceClient.order_market_sell(
                symbol=alt_symbol + crypto_symbol, quantity=(order_quantity)
            )

        self.logger.info("order")
        self.logger.info(order)

        trade_log.set_ordered(alt_balance, crypto_balance, order_quantity)

        # Binance server can take some time to save the order
        self.logger.info("Waiting for Binance")
        time.sleep(5)
        order_recorded = False
        stat = None
        while not order_recorded:
            try:
                time.sleep(3)
                stat = self.BinanceClient.get_order(
                    symbol=alt_symbol + crypto_symbol, orderId=order[u"orderId"]
                )
                order_recorded = True
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(10)
            except Exception as e:
                self.logger.info("Unexpected Error: {0}".format(e))

        self.logger.info(stat)
        while stat[u"status"] != "FILLED":
            self.logger.info(stat)
            try:
                stat = self.BinanceClient.get_order(
                    symbol=alt_symbol + crypto_symbol, orderId=order[u"orderId"]
                )
                time.sleep(1)
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(2)
            except Exception as e:
                self.logger.info("Unexpected Error: {0}".format(e))

        new_balance = self.get_currency_balance(alt_symbol)
        while new_balance >= alt_balance:
            new_balance = self.get_currency_balance(alt_symbol)

        self.logger.info("Sold {0}".format(alt_symbol))

        trade_log.set_complete(stat["cummulativeQuoteQty"])

        return order
