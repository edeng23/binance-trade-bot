#!python3
import configparser
import datetime
import json
import logging.handlers
import os
import queue
import random
import time
from logging import Handler, Formatter
from typing import List

import requests
from sqlalchemy.orm import Session

from binance_api_manager import BinanceApiManager
from database import (
    set_coins,
    set_current_coin,
    get_current_coin,
    get_pairs_from,
    db_session,
    create_database,
    get_pair,
    log_scout,
    CoinValue,
    prune_scout_history,
    prune_value_history,
)
from models import Coin, Pair
from scheduler import SafeScheduler

# Config consts
CFG_FL_NAME = "user.cfg"
USER_CFG_SECTION = "binance_user_config"

# Init config
config = configparser.ConfigParser()
if not os.path.exists(CFG_FL_NAME):
    print("No configuration file (user.cfg) found! See README.")
    exit()
config.read(CFG_FL_NAME)

# Logger setup
logger = logging.getLogger("crypto_trader_logger")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
fh = logging.FileHandler("crypto_trading.log")
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)

# logging to console
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
logger.addHandler(ch)

# Telegram bot
TELEGRAM_CHAT_ID = config.get(USER_CFG_SECTION, "botChatID")
TELEGRAM_TOKEN = config.get(USER_CFG_SECTION, "botToken")
BRIDGE_SYMBOL = config.get(USER_CFG_SECTION, "bridge")
BRIDGE = Coin(BRIDGE_SYMBOL, False)

# Prune settings
SCOUT_HISTORY_PRUNE_TIME = float(
    config.get(USER_CFG_SECTION, "hourToKeepScoutHistory", fallback="1")
)

# Setup binance
api_key = config.get(USER_CFG_SECTION, "api_key")
api_secret_key = config.get(USER_CFG_SECTION, "api_secret_key")
tld = config.get(USER_CFG_SECTION, "tld") or "com"  # Default Top-level domain is 'com'

binance_manager = BinanceApiManager(api_key, api_secret_key, tld, logger)


class RequestsHandler(Handler):
    def emit(self, record):
        log_entry = self.format(record)
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": log_entry, "parse_mode": "HTML"}
        return requests.post(
            "https://api.telegram.org/bot{token}/sendMessage".format(
                token=TELEGRAM_TOKEN
            ),
            data=payload,
        ).content


class LogstashFormatter(Formatter):
    def __init__(self):
        super(LogstashFormatter, self).__init__()

    def format(self, record):
        t = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        if isinstance(record.msg, dict):
            message = "<i>{datetime}</i>".format(datetime=t)

            for key in record.msg:
                message = message + (
                    "<pre>\n{title}: <strong>{value}</strong></pre>".format(
                        title=key, value=record.msg[key]
                    )
                )

            return message
        else:
            return "<i>{datetime}</i><pre>\n{message}</pre>".format(
                message=record.msg, datetime=t
            )


# logging to Telegram if token exists
if TELEGRAM_TOKEN:
    que = queue.Queue(-1)  # no limit on size
    queue_handler = logging.handlers.QueueHandler(que)
    th = RequestsHandler()
    listener = logging.handlers.QueueListener(que, th)
    formatter = LogstashFormatter()
    th.setFormatter(formatter)
    logger.addHandler(queue_handler)
    listener.start()

logger.info("Started")

supported_coin_list = []

# Get supported coin list from supported_coin_list file
with open("supported_coin_list") as f:
    supported_coin_list = f.read().upper().splitlines()

# Init config
config = configparser.ConfigParser()
if not os.path.exists(CFG_FL_NAME):
    print("No configuration file (user.cfg) found! See README.")
    exit()
config.read(CFG_FL_NAME)


def retry(howmany):
    def tryIt(func):
        def f(*args, **kwargs):
            time.sleep(1)
            attempts = 0
            while attempts < howmany:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print("Failed to Buy/Sell. Trying Again.")
                    if attempts == 0:
                        logger.info(e)
                        attempts += 1

        return f

    return tryIt


def first(iterable, condition=lambda x: True):
    try:
        return next(x for x in iterable if condition(x))
    except StopIteration:
        return None


def get_market_ticker_price_from_list(all_tickers, ticker_symbol):
    """
    Get ticker price of a specific coin
    """
    ticker = first(all_tickers, condition=lambda x: x["symbol"] == ticker_symbol)
    return float(ticker["price"]) if ticker else None


def transaction_through_tether(pair: Pair):
    """
    Jump from the source coin to the destination coin through tether
    """
    result = None
    while result is None:
        result = binance_manager.sell_alt(pair.from_coin, BRIDGE)
    result = None
    while result is None:
        result = binance_manager.buy_alt(pair.to_coin, BRIDGE)

    set_current_coin(pair.to_coin)
    update_trade_threshold()


def update_trade_threshold():
    """
    Update all the coins with the threshold of buying the current held coin
    """

    all_tickers = binance_manager.get_all_market_tickers()

    current_coin = get_current_coin()

    current_coin_price = get_market_ticker_price_from_list(
        all_tickers, current_coin + BRIDGE
    )

    if current_coin_price is None:
        logger.info(
            "Skipping update... current coin {0} not found".format(
                current_coin + BRIDGE
            )
        )
        return

    session: Session
    with db_session() as session:
        for pair in session.query(Pair).filter(Pair.to_coin == current_coin):
            from_coin_price = get_market_ticker_price_from_list(
                all_tickers, pair.from_coin + BRIDGE
            )

            if from_coin_price is None:
                logger.info(
                    "Skipping update for coin {0} not found".format(
                        pair.from_coin + BRIDGE
                    )
                )
                continue

            pair.ratio = from_coin_price / current_coin_price


def initialize_trade_thresholds():
    """
    Initialize the buying threshold of all the coins for trading between them
    """

    all_tickers = binance_manager.get_all_market_tickers()

    session: Session
    with db_session() as session:
        for pair in session.query(Pair).filter(Pair.ratio == None).all():
            if not pair.from_coin.enabled or not pair.to_coin.enabled:
                continue
            logger.info("Initializing {0} vs {1}".format(pair.from_coin, pair.to_coin))

            from_coin_price = get_market_ticker_price_from_list(
                all_tickers, pair.from_coin + BRIDGE
            )
            if from_coin_price is None:
                logger.info(
                    "Skipping initializing {0}, symbol not found".format(
                        pair.from_coin + BRIDGE
                    )
                )
                continue

            to_coin_price = get_market_ticker_price_from_list(
                all_tickers, pair.to_coin + BRIDGE
            )
            if to_coin_price is None:
                logger.info(
                    "Skipping initializing {0}, symbol not found".format(
                        pair.to_coin + BRIDGE
                    )
                )
                continue

            pair.ratio = from_coin_price / to_coin_price


def scout(transaction_fee=0.001, multiplier=5):
    """
    Scout for potential jumps from the current coin to another coin
    """

    all_tickers = binance_manager.get_all_market_tickers()

    current_coin = get_current_coin()

    current_coin_price = get_market_ticker_price_from_list(
        all_tickers, current_coin + BRIDGE
    )

    if current_coin_price is None:
        logger.info(
            "Skipping scouting... current coin {0} not found".format(
                current_coin + BRIDGE
            )
        )
        return

    for pair in get_pairs_from(current_coin):
        if not pair.to_coin.enabled:
            continue
        optional_coin_price = get_market_ticker_price_from_list(
            all_tickers, pair.to_coin + BRIDGE
        )

        if optional_coin_price is None:
            logger.info(
                "Skipping scouting... optional coin {0} not found".format(
                    pair.to_coin + BRIDGE
                )
            )
            continue

        log_scout(pair, pair.ratio, current_coin_price, optional_coin_price)

        # Obtain (current coin)/(optional coin)
        coin_opt_coin_ratio = current_coin_price / optional_coin_price

        if (
            coin_opt_coin_ratio - transaction_fee * multiplier * coin_opt_coin_ratio
        ) > pair.ratio:
            logger.info(
                "Will be jumping from {0} to {1}".format(current_coin, pair.to_coin)
            )
            transaction_through_tether(pair)
            break


def update_values():
    all_ticker_values = binance_manager.get_all_market_tickers()

    now = datetime.datetime.now()

    session: Session
    with db_session() as session:
        coins: List[Coin] = session.query(Coin).all()
        for coin in coins:
            balance = binance_manager.get_currency_balance(coin.symbol)
            if balance == 0:
                continue
            usd_value = get_market_ticker_price_from_list(
                all_ticker_values, coin + "USDT"
            )
            btc_value = get_market_ticker_price_from_list(
                all_ticker_values, coin + "BTC"
            )
            session.add(CoinValue(coin, balance, usd_value, btc_value, datetime=now))


def migrate_old_state():
    if os.path.isfile(".current_coin"):
        with open(".current_coin", "r") as f:
            coin = f.read().strip()
            logger.info(f".current_coin file found, loading current coin {coin}")
            set_current_coin(coin)
        os.rename(".current_coin", ".current_coin.old")
        logger.info(
            f".current_coin renamed to .current_coin.old - You can now delete this file"
        )

    if os.path.isfile(".current_coin_table"):
        with open(".current_coin_table", "r") as f:
            logger.info(f".current_coin_table file found, loading into database")
            table: dict = json.load(f)
            session: Session
            with db_session() as session:
                for from_coin, to_coin_dict in table.items():
                    for to_coin, ratio in to_coin_dict.items():
                        if from_coin == to_coin:
                            continue
                        pair = session.merge(get_pair(from_coin, to_coin))
                        pair.ratio = ratio
                        session.add(pair)

        os.rename(".current_coin_table", ".current_coin_table.old")
        logger.info(
            f".current_coin_table renamed to .current_coin_table.old - You can now delete this file"
        )


def main():
    if not os.path.isfile("data/crypto_trading.db"):
        logger.info("Creating database schema")
        create_database()

    set_coins(supported_coin_list)

    migrate_old_state()

    initialize_trade_thresholds()

    if get_current_coin() is None:
        current_coin_symbol = config.get(USER_CFG_SECTION, "current_coin")
        if not current_coin_symbol:
            current_coin_symbol = random.choice(supported_coin_list)

        logger.info("Setting initial coin to {0}".format(current_coin_symbol))

        if current_coin_symbol not in supported_coin_list:
            exit(
                "***\nERROR!\nSince there is no backup file, a proper coin name must be provided at init\n***"
            )
        set_current_coin(current_coin_symbol)

        if config.get(USER_CFG_SECTION, "current_coin") == "":
            current_coin = get_current_coin()
            logger.info("Purchasing {0} to begin trading".format(current_coin))
            binance_manager.buy_alt(current_coin, BRIDGE)
            logger.info("Ready to start trading")

    schedule = SafeScheduler(logger)
    schedule.every(5).seconds.do(scout).tag("scouting")
    schedule.every(1).minutes.do(update_values).tag("updating value history")
    schedule.every(1).minutes.do(
        prune_scout_history, hours=SCOUT_HISTORY_PRUNE_TIME
    ).tag("pruning scout history")
    schedule.every(1).hours.do(prune_value_history).tag("pruning value history")

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
