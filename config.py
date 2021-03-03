# Config consts
import configparser
import os

from models import Coin

CFG_FL_NAME = 'user.cfg'
USER_CFG_SECTION = 'binance_user_config'


class Config:
    def __init__(self):
        # Init config
        config = configparser.ConfigParser()
        config['DEFAULT'] = {
            'scout_transaction_fee': '0.001',
            'scout_multiplier': '5',
            'scout_sleep_time': '5',
            'tld': 'com'
        }

        if not os.path.exists(CFG_FL_NAME):
            print('No configuration file (user.cfg) found! See README.')
            exit()
        config.read(CFG_FL_NAME)

        self.BRIDGE_SYMBOL = config.get(USER_CFG_SECTION, 'bridge')
        self.BRIDGE = Coin(self.BRIDGE_SYMBOL, False)

        # Prune settings
        self.SCOUT_HISTORY_PRUNE_TIME = float(config.get(USER_CFG_SECTION, 'hourToKeepScoutHistory', fallback="1"))

        # Get config for scout
        self.SCOUT_TRANSACTION_FEE = float(config.get(USER_CFG_SECTION, 'scout_transaction_fee'))
        self.SCOUT_MULTIPLIER = float(config.get(USER_CFG_SECTION, 'scout_multiplier'))
        self.SCOUT_SLEEP_TIME = int(config.get(USER_CFG_SECTION, 'scout_sleep_time'))

        # Get config for binance
        self.BINANCE_API_KEY = config.get(USER_CFG_SECTION, 'api_key')
        self.BINANCE_API_SECRET_KEY = config.get(USER_CFG_SECTION, 'api_secret_key')
        self.BINANCE_TLD = config.get(USER_CFG_SECTION, 'tld')

        self.SUPPORTED_COIN_LIST = []

        # Get supported coin list from supported_coin_list file
        with open('supported_coin_list') as f:
            self.SUPPORTED_COIN_LIST = f.read().upper().strip().splitlines()
            self.SUPPORTED_COIN_LIST = list(filter(None, self.SUPPORTED_COIN_LIST))

        self.CURRENT_COIN_SYMBOL = config.get(USER_CFG_SECTION, 'current_coin')
