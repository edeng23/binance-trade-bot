from typing import Dict, Set

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
    non_existent_tickers: Set[str] = set()
    orders: Dict[str, BinanceOrder] = {}


class BinanceStreamManager:
    def __init__(self, cache: BinanceCache, api_key: str, api_secret: str, logger: Logger):
        self.cache = cache
        self.logger = logger
        self.bwam = BinanceWebSocketApiManager(process_stream_data=self.process_stream_data, output_default="UnicornFy")
        self.bwam.create_stream(["!userData"], ["arr"], api_key=api_key, api_secret=api_secret)
        self.bwam.create_stream(["!miniTicker"], ["arr"], api_key=api_key, api_secret=api_secret)

    def process_stream_data(self, stream_data, stream_buffer_name=False):  # pylint: disable=unused-argument
        event_type = stream_data["event_type"]
        if event_type == "executionReport":
            self.logger.debug(f"execution report: {stream_data}")
            order = BinanceOrder(stream_data)
            self.cache.orders[order.id] = order
        elif event_type == "balanceUpdate":
            self.logger.debug(f"Balance update: {stream_data}")
            del self.cache.balances[stream_data["asset"]]
        elif event_type == "outboundAccountPosition":
            self.logger.debug(f"outboundAccountPosition: {stream_data}")
            for bal in stream_data["balances"]:
                self.cache.balances[bal["asset"]] = float(bal["free"])
        elif event_type == "24hrMiniTicker":
            for event in stream_data["data"]:
                self.cache.ticker_values[event["symbol"]] = float(event["close_price"])
        else:
            self.logger.error(f"Unknown event type found: {event_type}\n{stream_data}")

    def close(self):
        self.bwam.stop_manager_with_all_streams()
