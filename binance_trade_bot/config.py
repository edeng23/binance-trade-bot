import configparser
import os

from .models import Coin

# Config consts
CFG_FL_NAME = "user.cfg"
USER_CFG_SECTION = "binance_user_config"

# Init config
config = configparser.ConfigParser()
if not os.path.exists(CFG_FL_NAME):
    print("No configuration file (user.cfg) found! See README.")
    exit()
config.read(CFG_FL_NAME)

# Telegram bot
TELEGRAM_CHAT_ID = config.get(USER_CFG_SECTION, "botChatID")
TELEGRAM_TOKEN = config.get(USER_CFG_SECTION, "botToken")

# Bridge coin
BRIDGE_SYMBOL = config.get(USER_CFG_SECTION, "bridge")
BRIDGE = Coin(BRIDGE_SYMBOL, False)

# Prune settings
SCOUT_HISTORY_PRUNE_TIME = float(
    config.get(USER_CFG_SECTION, "hourToKeepScoutHistory", fallback="1")
)

# Setup binance
BINANCE_API_KEY = config.get(USER_CFG_SECTION, "api_key")
BINANCE_API_SECRET_KEY = config.get(USER_CFG_SECTION, "api_secret_key")
BINANCE_TLD = (
    config.get(USER_CFG_SECTION, "tld") or "com"
)  # Default Top-level domain is 'com'

# Starting coin
STARTING_COIN = config.get(USER_CFG_SECTION, "current_coin")
