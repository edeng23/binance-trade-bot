import sys
import threading
import time
from typing import Dict, Set, Tuple

import binance.client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from unicorn_binance_websocket_api import BinanceWebSocketApiManager

from .logger import Logger


class BinanceOrder:  # pylint: disable=too-few-public-methods
    def __init__(self, report):
        self.event = report
        self.symbol = report["symbol"]
        self.side = report["side"]
        self.order_type = report["order_type"]
        self.id = report["order_id"]
        self.cumulative_quote_qty = float(report["cumulative_quote_asset_transacted_quantity"])
        self.status = report["current_order_status"]
        self.price = float(report["order_price"])
        self.time = report["transaction_time"]

    def __repr__(self):
        return f"<BinanceOrder {self.event}>"


class BinanceCache:  # pylint: disable=too-few-public-methods
    ticker_values: Dict[str, float] = {}
    balances: Dict[str, float] = {}
    balances_mutex: threading.Lock = threading.Lock()
    non_existent_tickers: Set[str] = set()
    orders: Dict[str, BinanceOrder] = {}


class OrderGuard:
    def __init__(self, pending_orders: Set[Tuple[str, int]], origin_symbol: str, target_symbol: str, order_id: int):
        self.pending_orders = pending_orders
        self.tag = (origin_symbol + target_symbol, order_id)

    def __enter__(self):
        self.pending_orders.add(self.tag)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pending_orders.remove(self.tag)


class BinanceStreamManager:
    def __init__(
        self, cache: BinanceCache, api_key: str, api_secret: str, binance_client: binance.client.Client, logger: Logger
    ):
        self.cache = cache
        self.logger = logger
        self.bwApiManager = BinanceWebSocketApiManager(output_default="UnicornFy", enable_stream_signal_buffer=True)
        self.bwApiManager.create_stream(["arr"], ["!miniTicker"], api_key=api_key, api_secret=api_secret)
        self.bwApiManager.create_stream(["arr"], ["!userData"], api_key=api_key, api_secret=api_secret)
        self.binance_client = binance_client
        self.pending_orders: Set[Tuple[str, int]] = set()
        self._processorThread = threading.Thread(target=self._stream_processor)
        self._processorThread.start()

    def acquire_order_guard(self, origin_symbol: str, target_symbol: str, order_id: int):
        return OrderGuard(self.pending_orders, origin_symbol, target_symbol, order_id)

    def _fetch_pending_orders(self):
        orders = self.pending_orders.copy()
        for (symbol, order_id) in orders:
            order = None
            while True:
                try:
                    order = self.binance_client.get_order(symbol=symbol, orderId=order_id)
                except (BinanceRequestException, BinanceAPIException):
                    pass
                if order is not None:
                    break
                time.sleep(1)
            fake_report = {
                "symbol": order["symbol"],
                "side": order["side"],
                "order_type": order["type"],
                "order_id": order["orderId"],
                "cumulative_quote_asset_transacted_quantity": float(order["cummulativeQuoteQty"]),
                "current_order_status": order["status"],
                "order_price": float(order["price"]),
                "transaction_time": order["time"],
            }
            self.logger.info(f"Pending order {order_id} for symbol {symbol} fetched:\n{fake_report}", False)
            self.cache.orders[fake_report["order_id"]] = BinanceOrder(fake_report)

    def _invalidate_balances(self):
        with self.cache.balances_mutex:
            self.cache.balances.clear()

    def _stream_processor(self):
        while True:
            if self.bwApiManager.is_manager_stopping():
                sys.exit()

            stream_signal = self.bwApiManager.pop_stream_signal_from_stream_signal_buffer()
            stream_data = self.bwApiManager.pop_stream_data_from_stream_buffer()

            if stream_signal is not False:
                signal_type = stream_signal["type"]
                stream_id = stream_signal["stream_id"]
                if signal_type == "CONNECT":
                    stream_info = self.bwApiManager.get_stream_info(stream_id)
                    if "!userData" in stream_info["markets"]:
                        self.logger.debug("Connect for userdata arrived", False)
                        self._fetch_pending_orders()
                        self._invalidate_balances()
            if stream_data is not False:
                self._process_stream_data(stream_data)
            if stream_data is False and stream_signal is False:
                time.sleep(0.01)

    def _process_stream_data(self, stream_data):
        event_type = stream_data["event_type"]
        if event_type == "executionReport":  # !userData
            self.logger.debug(f"execution report: {stream_data}")
            order = BinanceOrder(stream_data)
            self.cache.orders[order.id] = order
        elif event_type == "balanceUpdate":  # !userData
            self.logger.debug(f"Balance update: {stream_data}")
            with self.cache.balances_mutex:
                del self.cache.balances[stream_data["asset"]]
        elif event_type == "outboundAccountPosition":  # !userData
            self.logger.debug(f"outboundAccountPosition: {stream_data}")
            with self.cache.balances_mutex:
                for bal in stream_data["balances"]:
                    self.cache.balances[bal["asset"]] = float(bal["free"])
        elif event_type == "24hrMiniTicker":
            for event in stream_data["data"]:
                self.cache.ticker_values[event["symbol"]] = float(event["close_price"])
        else:
            self.logger.error(f"Unknown event type found: {event_type}\n{stream_data}")

    def close(self):
        self.bwApiManager.stop_manager_with_all_streams()
