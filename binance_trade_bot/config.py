# Config consts
import configparser
import os
from argparse import ArgumentParser
from typing import Dict

from .models import Coin

CFG_FL_NAME = "user.cfg"
USER_CFG_SECTION = "binance_user_config"

CONFIG_TO_ENV = {
    "bridge": "BRIDGE_SYMBOL",
    "hourToKeepScoutHistory": "HOURS_TO_KEEP_SCOUTING_HISTORY",
    "scout_multiplier": "SCOUT_MULTIPLIER",
    "scout_sleep_time": "SCOUT_SLEEP_TIME",
    "api_key": "API_KEY",
    "api_secret_key": "API_SECRET_KEY",
    "tld": "TLD",
    "current_coin": "CURRENT_COIN_SYMBOL",
    "strategy": "STRATEGY",
    "sell_timeout": "SELL_TIMEOUT",
    "buy_timeout": "BUY_TIMEOUT",
}


class Config:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    def __init__(self, config_values: Dict = None):
        # Init config

        if config_values is None:
            config_values = {}
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

        self.BRIDGE_SYMBOL = Config._get_option("bridge", config, config_values)
        self.BRIDGE = Coin(self.BRIDGE_SYMBOL, False)

        # Prune settings
        self.SCOUT_HISTORY_PRUNE_TIME = float(Config._get_option("hourToKeepScoutHistory", config, config_values))

        # Get config for scout
        self.SCOUT_MULTIPLIER = float(Config._get_option("scout_multiplier", config, config_values))
        self.SCOUT_SLEEP_TIME = int(Config._get_option("scout_sleep_time", config, config_values))

        # Get config for binance
        self.BINANCE_API_KEY = Config._get_option("api_key", config, config_values)
        self.BINANCE_API_SECRET_KEY = Config._get_option("api_secret_key", config, config_values)
        self.BINANCE_TLD = Config._get_option("tld", config, config_values)

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

        self.CURRENT_COIN_SYMBOL = Config._get_option("current_coin", config, config_values)

        self.STRATEGY = Config._get_option("strategy", config, config_values)

        self.SELL_TIMEOUT = Config._get_option("sell_timeout", config, config_values)
        self.BUY_TIMEOUT = Config._get_option("buy_timeout", config, config_values)

    @staticmethod
    def _get_option(option_key, config, config_values):
        return (
            config_values.get(option_key)
            or os.environ.get(CONFIG_TO_ENV[option_key])
            or config.get(USER_CFG_SECTION, option_key)
        )

    @staticmethod
    def get_parser():
        # Create parser for config and return it

        parser = ArgumentParser("Binance Trading Bot")
        for option in CONFIG_TO_ENV:
            parser.add_argument(f"--{option}")

        return parser

    def verbose(self):
        # Print config values

        config_values = self.__dict__.copy()
        del config_values["BINANCE_API_KEY"]
        del config_values["BINANCE_API_SECRET_KEY"]

        print("\n".join([f"{k}: {v}" for k, v in config_values.items()]))
