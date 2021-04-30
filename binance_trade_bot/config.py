# Config consts
import configparser
import os

from .models import Coin

CFG_FL_NAME = "user.cfg"
USER_CFG_SECTION = "binance_user_config"


class Config:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    def __init__(self):
        # Init config
        config = configparser.ConfigParser()
        config["DEFAULT"] = {
            "bridge": "USDT",
            "scout_multiplier": "5",
            "scout_sleep_time": "5",
            "hourToKeepScoutHistory": "1",
            "tld": "com",
            "strategy": "default",
            "sell_timeout": "0",
            "buy_timeout": "0",
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

        self.TWITTER_BEARER_TOKEN = = os.environ.get("TWITTER_BEARER_TOKEN") or config.get(USER_CFG_SECTION, "twitter_bearer_token")
        self.GOOGLE_APPLICATION_CREDENTIALS = = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or config.get(USER_CFG_SECTION, "google_application_credentials")
        self.ELON_TWITTER_USERNAME = os.environ.get("ELON_TWITTER_USERNAME") or config.get(USER_CFG_SECTION, "elon_twitter_username")
        self.ELON_CRYPTO_RULES = os.environ.get("ELON_CRYPTO_RULES") or config.get(USER_CFG_SECTION, "elon_crypto_rules")
        self.ELON_MARGIN_TYPE = os.environ.get("ELON_MARGIN_TYPE") or config.get(USER_CFG_SECTION, "elon_margin_type")
        self.ELON_AUTO_BUY_DELAY_SECONDS = os.environ.get("ELON_AUTO_BUY_DELAY_SECONDS") or config.get(USER_CFG_SECTION, "elon_auto_buy_delay_seconds")
        self.ELON_AUTO_SELL_DELAY_SECONDS = os.environ.get("ELON_AUTO_SELL_DELAY_SECONDS") or config.get(USER_CFG_SECTION, "elon_auto_sell_delay_seconds")
        self.ELON_ORDER_SIZE_MAX = os.environ.get("ELON_ORDER_SIZE_MAX") or config.get(USER_CFG_SECTION, "elon_order_size_max")
