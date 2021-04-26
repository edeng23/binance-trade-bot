import math
import time
from typing import Dict, List

from binance.client import Client
from binance.exceptions import BinanceAPIException
from cachetools import TTLCache, cached

from .config import Config
from .database import Database
from .logger import Logger
from .models import Coin


class AllTickers:  # pylint: disable=too-few-public-methods
    def __init__(self, all_tickers: List[Dict]):
        self.all_tickers = all_tickers

    def get_price(self, ticker_symbol):
        ticker = next((t for t in self.all_tickers if t["symbol"] == ticker_symbol), None)
        return float(ticker["price"]) if ticker else None


class BinanceAPIManager:
    def __init__(self, config: Config, db: Database, logger: Logger):
        self.binance_client = Client(
            config.BINANCE_API_KEY,
            config.BINANCE_API_SECRET_KEY,
            tld=config.BINANCE_TLD,
        )
        self.db = db
        self.logger = logger
        self.config = config

    @cached(cache=TTLCache(maxsize=1, ttl=43200))
    def get_trade_fees(self) -> Dict[str, float]:
        return {ticker["symbol"]: ticker["taker"] for ticker in self.binance_client.get_trade_fee()["tradeFee"]}

    @cached(cache=TTLCache(maxsize=1, ttl=60))
    def get_using_bnb_for_fees(self):
        return self.binance_client.get_bnb_burn_spot_margin()["spotBNBBurn"]

    def get_fee(self, origin_coin: Coin, target_coin: Coin, selling: bool):
        base_fee = self.get_trade_fees()[origin_coin + target_coin]
        if not self.get_using_bnb_for_fees():
            return base_fee
        # The discount is only applied if we have enough BNB to cover the fee
        amount_trading = (
            self._sell_quantity(origin_coin.symbol, target_coin.symbol)
            if selling
            else self._buy_quantity(origin_coin.symbol, target_coin.symbol)
        )
        fee_amount = amount_trading * base_fee * 0.75
        if origin_coin.symbol == "BNB":
            fee_amount_bnb = fee_amount
        else:
            origin_price = self.get_market_ticker_price(origin_coin + Coin("BNB"))
            if origin_price is None:
                return base_fee
            fee_amount_bnb = fee_amount * origin_price
        bnb_balance = self.get_currency_balance("BNB")
        if bnb_balance >= fee_amount_bnb:
            return base_fee * 0.75
        return base_fee

    def get_all_market_tickers(self) -> AllTickers:
        """
        Get ticker price of all coins
        """
        return AllTickers(self.binance_client.get_all_tickers())

    def get_market_ticker_price(self, ticker_symbol: str):
        """
        Get ticker price of a specific coin
        """
        for ticker in self.binance_client.get_symbol_ticker():
            if ticker["symbol"] == ticker_symbol:
                return float(ticker["price"])
        return None

    def get_currency_balance(self, currency_symbol: str):
        """
        Get balance of a specific coin
        """
        for currency_balance in self.binance_client.get_account()["balances"]:
            if currency_balance["asset"] == currency_symbol:
                return float(currency_balance["free"])
        return None

    def retry(self, func, *args, **kwargs):
        time.sleep(1)
        attempts = 0
        while attempts < 20:
            try:
                return func(*args, **kwargs)
            except Exception as e:  # pylint: disable=broad-except
                self.logger.info("Failed to Buy/Sell. Trying Again.")
                if attempts == 0:
                    self.logger.info(e)
                attempts += 1
        return None

    def get_symbol_filter(self, origin_symbol: str, target_symbol: str, filter_type: str):
        return next(
            _filter
            for _filter in self.binance_client.get_symbol_info(origin_symbol + target_symbol)["filters"]
            if _filter["filterType"] == filter_type
        )

    @cached(cache=TTLCache(maxsize=2000, ttl=43200))
    def get_alt_tick(self, origin_symbol: str, target_symbol: str):
        step_size = self.get_symbol_filter(origin_symbol, target_symbol, "LOT_SIZE")["stepSize"]
        if step_size.find("1") == 0:
            return 1 - step_size.find(".")
        return step_size.find("1") - 1

    @cached(cache=TTLCache(maxsize=2000, ttl=43200))
    def get_min_notional(self, origin_symbol: str, target_symbol: str):
        return float(self.get_symbol_filter(origin_symbol, target_symbol, "MIN_NOTIONAL")["minNotional"])

    def wait_for_order(self, origin_symbol, target_symbol, order_id):
        while True:
            try:
                order_status = self.binance_client.get_order(symbol=origin_symbol + target_symbol, orderId=order_id)
                break
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(1)
            except Exception as e:  # pylint: disable=broad-except
                self.logger.info(f"Unexpected Error: {e}")
                time.sleep(1)

        self.logger.info(order_status)

        while order_status["status"] != "FILLED":
            try:
                order_status = self.binance_client.get_order(symbol=origin_symbol + target_symbol, orderId=order_id)

                if self._should_cancel_order(order_status):
                    cancel_order = None
                    while cancel_order is None:
                        cancel_order = self.binance_client.cancel_order(
                            symbol=origin_symbol + target_symbol, orderId=order_id
                        )
                    self.logger.info("Order timeout, canceled...")

                    # sell partially
                    if order_status["status"] == "PARTIALLY_FILLED" and order_status["side"] == "BUY":
                        self.logger.info("Sell partially filled amount")

                        order_quantity = self._sell_quantity(origin_symbol, target_symbol)
                        partially_order = None
                        while partially_order is None:
                            partially_order = self.binance_client.order_market_sell(
                                symbol=origin_symbol + target_symbol, quantity=order_quantity
                            )

                    self.logger.info("Going back to scouting mode...")
                    return None

                if order_status["status"] == "CANCELED":
                    self.logger.info("Order is canceled, going back to scouting mode...")
                    return None

                time.sleep(1)
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(1)
            except Exception as e:  # pylint: disable=broad-except
                self.logger.info(f"Unexpected Error: {e}")
                time.sleep(1)

        return order_status

    def _should_cancel_order(self, order_status):
        minutes = (time.time() - order_status["time"] / 1000) / 60
        timeout = 0

        if order_status["side"] == "SELL":
            timeout = float(self.config.SELL_TIMEOUT)
        else:
            timeout = float(self.config.BUY_TIMEOUT)

        if timeout and minutes > timeout and order_status["status"] == "NEW":
            return True

        if timeout and minutes > timeout and order_status["status"] == "PARTIALLY_FILLED":
            if order_status["side"] == "SELL":
                return True

            if order_status["side"] == "BUY":
                current_price = self.get_market_ticker_price(order_status["symbol"])
                if float(current_price) * (1 - 0.001) > float(order_status["price"]):
                    return True

        return False

    def buy_alt(self, origin_coin: Coin, target_coin: Coin, all_tickers: AllTickers):
        return self.retry(self._buy_alt, origin_coin, target_coin, all_tickers)

    def _buy_quantity(
        self, origin_symbol: str, target_symbol: str, target_balance: float = None, from_coin_price: float = None
    ):
        target_balance = target_balance or self.get_currency_balance(target_symbol)
        from_coin_price = from_coin_price or self.get_all_market_tickers().get_price(origin_symbol + target_symbol)

        origin_tick = self.get_alt_tick(origin_symbol, target_symbol)
        return math.floor(target_balance * 10 ** origin_tick / from_coin_price) / float(10 ** origin_tick)

    def _buy_alt(self, origin_coin: Coin, target_coin: Coin, all_tickers):
        """
        Buy altcoin
        """
        trade_log = self.db.start_trade_log(origin_coin, target_coin, False)
        origin_symbol = origin_coin.symbol
        target_symbol = target_coin.symbol

        origin_balance = self.get_currency_balance(origin_symbol)
        target_balance = self.get_currency_balance(target_symbol)
        from_coin_price = all_tickers.get_price(origin_symbol + target_symbol)

        order_quantity = self._buy_quantity(origin_symbol, target_symbol, target_balance, from_coin_price)
        self.logger.info(f"BUY QTY {order_quantity} of <{origin_symbol}>")

        # Try to buy until successful
        order = None
        while order is None:
            try:
                order = self.binance_client.order_limit_buy(
                    symbol=origin_symbol + target_symbol,
                    quantity=order_quantity,
                    price=from_coin_price,
                )
                self.logger.info(order)
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(1)
            except Exception as e:  # pylint: disable=broad-except
                self.logger.info(f"Unexpected Error: {e}")

        trade_log.set_ordered(origin_balance, target_balance, order_quantity)

        stat = self.wait_for_order(origin_symbol, target_symbol, order["orderId"])

        if stat is None:
            return None

        self.logger.info(f"Bought {origin_symbol}")
        trade_log.set_complete(stat["cummulativeQuoteQty"])

        return order

    def sell_alt(self, origin_coin: Coin, target_coin: Coin, all_tickers: AllTickers):
        return self.retry(self._sell_alt, origin_coin, target_coin, all_tickers)

    def _sell_quantity(self, origin_symbol: str, target_symbol: str, origin_balance: float = None):
        origin_balance = origin_balance or self.get_currency_balance(origin_symbol)

        origin_tick = self.get_alt_tick(origin_symbol, target_symbol)
        return math.floor(origin_balance * 10 ** origin_tick) / float(10 ** origin_tick)

    def _sell_alt(self, origin_coin: Coin, target_coin: Coin, all_tickers: AllTickers):
        """
        Sell altcoin
        """
        trade_log = self.db.start_trade_log(origin_coin, target_coin, True)
        origin_symbol = origin_coin.symbol
        target_symbol = target_coin.symbol

        origin_balance = self.get_currency_balance(origin_symbol)
        target_balance = self.get_currency_balance(target_symbol)
        from_coin_price = all_tickers.get_price(origin_symbol + target_symbol)

        order_quantity = self._sell_quantity(origin_symbol, target_symbol, origin_balance)
        self.logger.info(f"Selling {order_quantity} of {origin_symbol}")

        self.logger.info(f"Balance is {origin_balance}")
        order = None
        while order is None:
            # Should sell at calculated price to avoid lost coin
            order = self.binance_client.order_limit_sell(
                symbol=origin_symbol + target_symbol, quantity=(order_quantity), price=from_coin_price
            )

        self.logger.info("order")
        self.logger.info(order)

        trade_log.set_ordered(origin_balance, target_balance, order_quantity)

        # Binance server can take some time to save the order
        self.logger.info("Waiting for Binance")

        stat = self.wait_for_order(origin_symbol, target_symbol, order["orderId"])

        if stat is None:
            return None

        new_balance = self.get_currency_balance(origin_symbol)
        while new_balance >= origin_balance:
            new_balance = self.get_currency_balance(origin_symbol)

        self.logger.info(f"Sold {origin_symbol}")

        trade_log.set_complete(stat["cummulativeQuoteQty"])

        return order
