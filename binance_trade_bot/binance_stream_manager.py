import time
from typing import Dict

from autobahn.twisted.websocket import connectWS
from binance.client import Client
from binance.websockets import BinanceClientFactory, BinanceClientProtocol, BinanceSocketManager
from twisted.internet import reactor, ssl

from .logger import Logger


class CustomBinanceSocketManager(BinanceSocketManager):
    """
    A custom implementation that fixes disconnection detection
    """

    def _start_socket(self, path, callback, prefix="ws/"):
        if path in self._conns:
            return False

        factory_url = self.STREAM_URL + prefix + path
        factory = BinanceClientFactory(factory_url)
        factory.protocol = BinanceClientProtocol
        factory.callback = callback
        factory.reconnect = True
        factory.setProtocolOptions(autoPingInterval=5, autoPingTimeout=5)
        context_factory = ssl.ClientContextFactory()

        self._conns[path] = connectWS(factory, context_factory)
        return path


class BinanceCache:  # pylint: disable=too-few-public-methods
    ticker_values: Dict[str, float] = {}
    balances: Dict[str, float] = {}


class BinanceStreamManager:
    def __init__(self, cache: BinanceCache, client: Client, logger: Logger):
        self.cache = cache
        self.logger = logger
        self.bm = CustomBinanceSocketManager(client)

        self.ticker_price_socket_conn_key = self._start_ticker_values_socket()
        self.user_socket_conn_key = self._start_user_socket()

        self.bm.start()

    def retry(self, func, *args, **kwargs):
        attempts = 0
        time.sleep(1 + attempts * 5)
        while attempts < 20:
            try:
                return func(*args, **kwargs)
            except Exception as e:  # pylint: disable=broad-except
                self.logger.info("Failed to connect to websocket. Trying Again.")
                if attempts == 0:
                    self.logger.info(e)
                attempts += 1
        return None

    def _start_ticker_values_socket(self):
        conn = self.bm.start_ticker_socket(self._process_ticker_values)
        if conn:
            return conn
        return self.retry(self._start_ticker_values_socket)

    def _start_user_socket(self):
        conn = self.bm.start_user_socket(self._process_user_socket)
        if conn:
            return conn
        return self.retry(self._start_user_socket)

    def _process_ticker_values(self, msg):
        if "e" in msg and msg["e"] == "error":
            self.bm.stop_socket(self.ticker_price_socket_conn_key)
            self.ticker_price_socket_conn_key = self._start_ticker_values_socket()
            self.cache.ticker_values.clear()
            return

        for ticker in msg:
            self.cache.ticker_values[ticker["s"]] = float(ticker["c"])

    def _process_user_socket(self, msg):
        if msg["e"] == "error":
            self.bm.stop_socket(self.user_socket_conn_key)
            self.user_socket_conn_key = self._start_user_socket()
            self.cache.balances.clear()
            return
        if msg["e"] == "outboundAccountPosition":
            for bal in msg["B"]:
                self.cache.balances[bal["a"]] = float(bal["f"])
        elif msg["e"] == "balanceUpdate":
            del self.cache.balances[msg["a"]]

    def close(self):
        self.bm.close()
        reactor.stop()
