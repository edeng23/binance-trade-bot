import configparser
import os

import binance.client

from .models import Coin

CFG_FL_NAME = "user.cfg"
USER_CFG_SECTION = "binance_user_config"


class Config:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    ORDER_TYPE_MARKET = "market"
    ORDER_TYPE_LIMIT = "limit"

    PRICE_TYPE_ORDERBOOK = "orderbook"
    PRICE_TYPE_TICKER = "ticker"

    def __init__(self):
        # Init config
        config = configparser.ConfigParser()
        config["DEFAULT"] = {
            "bridge": "USDT",
            "scout_multiplier": "5",
            "scout_sleep_time": "5",
            "hourToKeepScoutHistory": "1",
            "tld": "com",
            "trade_fee": "auto",
            "strategy": "default",
            "sell_timeout": "0",
            "buy_timeout": "0",
            "sell_order_type": self.ORDER_TYPE_MARKET,
            "buy_order_type": self.ORDER_TYPE_LIMIT,
            "sell_max_price_change": "0.005",
            "buy_max_price_change": "0.005",
            "price_type": self.PRICE_TYPE_ORDERBOOK,
            "max_idle_hours": "3",
        }

        if not os.path.exists(CFG_FL_NAME):
            print("No configuration file (user.cfg) found! See README. Assuming default config...")
            config[USER_CFG_SECTION] = {}
        else:
            config.read(CFG_FL_NAME)

        self.BRIDGE_SYMBOL = os.environ.get("BRIDGE_SYMBOL") or config.get(USER_CFG_SECTION, "bridge")
        self.BRIDGE = Coin(self.BRIDGE_SYMBOL, False)

        # Prune settings
        self.SCOUT_HISTORY_PRUNE_TIME = float(
            os.environ.get("HOURS_TO_KEEP_SCOUTING_HISTORY") or config.get(USER_CFG_SECTION, "hourToKeepScoutHistory")
        )

        # Get config for scout
        self.SCOUT_MULTIPLIER = float(
            os.environ.get("SCOUT_MULTIPLIER") or config.get(USER_CFG_SECTION, "scout_multiplier")
        )
        self.SCOUT_SLEEP_TIME = int(
            os.environ.get("SCOUT_SLEEP_TIME") or config.get(USER_CFG_SECTION, "scout_sleep_time")
        )

        # Get config for binance
        self.BINANCE_API_KEY = os.environ.get("API_KEY") or config.get(USER_CFG_SECTION, "api_key")
        self.BINANCE_API_SECRET_KEY = os.environ.get("API_SECRET_KEY") or config.get(USER_CFG_SECTION, "api_secret_key")
        self.BINANCE_TLD = os.environ.get("TLD") or config.get(USER_CFG_SECTION, "tld")

        # Get supported coin list from the environment
        supported_coin_list = [
            coin.strip() for coin in os.environ.get("SUPPORTED_COIN_LIST", "").split() if coin.strip()
        ]

        self.TRADE_FEE = os.environ.get("TRADE_FEE") or config.get(USER_CFG_SECTION, "trade_fee")

        # Get supported coin list from supported_coin_list file
        if not supported_coin_list and os.path.exists("supported_coin_list"):
            with open("supported_coin_list") as rfh:
                for line in rfh:
                    line = line.strip()
                    if not line or line.startswith("#") or line in supported_coin_list:
                        continue
                    supported_coin_list.append(line)
        self.SUPPORTED_COIN_LIST = supported_coin_list

        self.CURRENT_COIN_SYMBOL = os.environ.get("CURRENT_COIN_SYMBOL") or config.get(USER_CFG_SECTION, "current_coin")

        self.STRATEGY = os.environ.get("STRATEGY") or config.get(USER_CFG_SECTION, "strategy")

        self.SELL_TIMEOUT = os.environ.get("SELL_TIMEOUT") or config.get(USER_CFG_SECTION, "sell_timeout")
        self.BUY_TIMEOUT = os.environ.get("BUY_TIMEOUT") or config.get(USER_CFG_SECTION, "buy_timeout")

        order_type_map = {
            self.ORDER_TYPE_LIMIT: binance.client.Client.ORDER_TYPE_LIMIT,
            self.ORDER_TYPE_MARKET: binance.client.Client.ORDER_TYPE_MARKET,
        }

        sell_order_type = os.environ.get("SELL_ORDER_TYPE") or config.get(
            USER_CFG_SECTION, "sell_order_type", fallback=self.ORDER_TYPE_MARKET
        )
        if sell_order_type not in order_type_map:
            raise Exception(
                f"{self.ORDER_TYPE_LIMIT} or {self.ORDER_TYPE_MARKET} expected, got {sell_order_type}"
                "for sell_order_type"
            )
        self.SELL_ORDER_TYPE = order_type_map[sell_order_type]

        self.SELL_MAX_PRICE_CHANGE = os.environ.get("SELL_MAX_PRICE_CHANGE") or config.get(USER_CFG_SECTION, "sell_max_price_change")

        buy_order_type = os.environ.get("BUY_ORDER_TYPE") or config.get(
            USER_CFG_SECTION, "buy_order_type", fallback=self.ORDER_TYPE_LIMIT
        )
        if buy_order_type not in order_type_map:
            raise Exception(
                f"{self.ORDER_TYPE_LIMIT} or {self.ORDER_TYPE_MARKET} expected, got {buy_order_type}"
                "for buy_order_type"
            )
        if buy_order_type == self.ORDER_TYPE_MARKET:
            raise Exception(
                "Market buys are reported to do extreme losses, they are disabled right now,"
                "comment this line only if you know what you're doing"
            )
        self.BUY_ORDER_TYPE = order_type_map[buy_order_type]

        self.BUY_MAX_PRICE_CHANGE = os.environ.get("BUY_MAX_PRICE_CHANGE") or config.get(USER_CFG_SECTION, "buy_max_price_change")

        price_types = {
            self.PRICE_TYPE_ORDERBOOK,
            self.PRICE_TYPE_TICKER
        }

        price_type = os.environ.get("PRICE_TYPE") or config.get(
            USER_CFG_SECTION, "price_type", fallback=self.PRICE_TYPE_ORDERBOOK
        )
        if price_type not in price_types:
            raise Exception(f"{self.PRICE_TYPE_ORDERBOOK} or {self.PRICE_TYPE_TICKER} expected, got {price_type} for price_type")
        self.PRICE_TYPE = price_type

        self.MAX_IDLE_HOURS = os.environ.get("MAX_IDLE_HOURS") or config.get(USER_CFG_SECTION, "max_idle_hours")
