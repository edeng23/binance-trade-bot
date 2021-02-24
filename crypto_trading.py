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

import database as db
from binance_api_manager import BinanceApiManager
from config import Config
from models import Coin, Pair
from scheduler import SafeScheduler


def create_logger():
    _logger = logging.getLogger("crypto_trader_logger")
    _logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    fh = logging.FileHandler("crypto_trading.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    _logger.addHandler(fh)

    # logging to console
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    _logger.addHandler(ch)

    # logging to Telegram if token exists
    if Config.TELEGRAM_TOKEN:
        que = queue.Queue(-1)  # no limit on size
        queue_handler = logging.handlers.QueueHandler(que)
        th = RequestsHandler()
        listener = logging.handlers.QueueListener(que, th)
        formatter = LogstashFormatter()
        th.setFormatter(formatter)
        _logger.addHandler(queue_handler)
        listener.start()

    return _logger


class RequestsHandler(Handler):
    def emit(self, record):
        log_entry = self.format(record)
        payload = {
            "chat_id": Config.TELEGRAM_CHAT_ID,
            "text": log_entry,
            "parse_mode": "HTML",
        }
        return requests.post(
            f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage",
            data=payload,
        ).content


class LogstashFormatter(Formatter):
    def __init__(self):
        super(LogstashFormatter, self).__init__()

    def format(self, record):
        t = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        if isinstance(record.msg, dict):
            message = f"<i>{t}</i>"

            for key in record.msg:
                message = message + (
                    f"<pre>\n{key}: <strong>{record.msg[key]}</strong></pre>"
                )

            return message
        else:
            return f"<i>{t}</i><pre>\n{record.msg}</pre>"


# Get supported coin list from supported_coin_list file
with open("supported_coin_list") as f:
    supported_coin_list = f.read().upper().splitlines()

# Init config
config = configparser.ConfigParser()
if not os.path.exists(Config.CFG_FL_NAME):
    print("No configuration file (user.cfg) found! See README.")
    exit()
config.read(Config.CFG_FL_NAME)


def get_market_ticker_price_from_list(all_tickers, ticker_symbol):
    """
    Get ticker price of a specific coin
    """
    ticker = next(
        (ticker for ticker in all_tickers if ticker["symbol"] == ticker_symbol), None
    )
    return float(ticker["price"]) if ticker else None


def transaction_through_tether(pair: Pair):
    """
    Jump from the source coin to the destination coin through tether
    """
    result = binance_manager.sell_alt(pair.from_coin, Config.BRIDGE)
    if result is None:
        logger.info("Selling failed, cancelling transaction")
    result = binance_manager.buy_alt(pair.to_coin, Config.BRIDGE)
    if result is None:
        logger.info("Buying failed, cancelling transaction")

    db.set_current_coin(pair.to_coin)
    update_trade_threshold()


def update_trade_threshold():
    """
    Update all the coins with the threshold of buying the current held coin
    """

    all_tickers = binance_manager.get_all_market_tickers()

    current_coin = db.get_current_coin()

    current_coin_price = get_market_ticker_price_from_list(
        all_tickers, current_coin + Config.BRIDGE
    )

    if current_coin_price is None:
        logger.info(
            f"Skipping update... current coin {current_coin + Config.BRIDGE} not found"
        )
        return

    session: Session
    with db.db_session() as session:
        for pair in session.query(Pair).filter(Pair.to_coin == current_coin):
            from_coin_price = get_market_ticker_price_from_list(
                all_tickers, pair.from_coin + Config.BRIDGE
            )

            if from_coin_price is None:
                logger.info(
                    f"Skipping update for coin {pair.from_coin + Config.BRIDGE} not found"
                )
                continue

            pair.ratio = from_coin_price / current_coin_price


def initialize_trade_thresholds():
    """
    Initialize the buying threshold of all the coins for trading between them
    """

    all_tickers = binance_manager.get_all_market_tickers()

    session: Session
    with db.db_session() as session:
        for pair in session.query(Pair).filter(Pair.ratio == None).all():
            if not pair.from_coin.enabled or not pair.to_coin.enabled:
                continue
            logger.info(f"Initializing {pair.from_coin} vs {pair.to_coin}")

            from_coin_price = get_market_ticker_price_from_list(
                all_tickers, pair.from_coin + Config.BRIDGE
            )
            if from_coin_price is None:
                logger.info(
                    f"Skipping initializing {pair.from_coin + Config.BRIDGE}, symbol not found"
                )
                continue

            to_coin_price = get_market_ticker_price_from_list(
                all_tickers, pair.to_coin + Config.BRIDGE
            )
            if to_coin_price is None:
                logger.info(
                    f"Skipping initializing {pair.to_coin + Config.BRIDGE}, symbol not found"
                )
                continue

            pair.ratio = from_coin_price / to_coin_price


def scout(transaction_fee=0.001, multiplier=5):
    """
    Scout for potential jumps from the current coin to another coin
    """

    all_tickers = binance_manager.get_all_market_tickers()

    current_coin = db.get_current_coin()

    current_coin_price = get_market_ticker_price_from_list(
        all_tickers, current_coin + Config.BRIDGE
    )

    if current_coin_price is None:
        logger.info(
            f"Skipping scouting... current coin {current_coin + Config.BRIDGE} not found"
        )
        return

    for pair in db.get_pairs_from(current_coin):
        if not pair.to_coin.enabled:
            continue
        optional_coin_price = get_market_ticker_price_from_list(
            all_tickers, pair.to_coin + Config.BRIDGE
        )

        if optional_coin_price is None:
            logger.info(
                f"Skipping scouting... optional coin {pair.to_coin + Config.BRIDGE} not found"
            )
            continue

        db.log_scout(pair, pair.ratio, current_coin_price, optional_coin_price)

        # Obtain (current coin)/(optional coin)
        coin_opt_coin_ratio = current_coin_price / optional_coin_price

        if (
            coin_opt_coin_ratio - transaction_fee * multiplier * coin_opt_coin_ratio
        ) > pair.ratio:
            logger.info(f"Will be jumping from {current_coin} to {pair.to_coin}")
            transaction_through_tether(pair)
            break


def update_values():
    all_ticker_values = binance_manager.get_all_market_tickers()

    now = datetime.datetime.now()

    session: Session
    with db.db_session() as session:
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
            session.add(db.CoinValue(coin, balance, usd_value, btc_value, datetime=now))


def migrate_old_state():
    if os.path.isfile(".current_coin"):
        with open(".current_coin", "r") as f:
            coin = f.read().strip()
            logger.info(f".current_coin file found, loading current coin {coin}")
            db.set_current_coin(coin)
        os.rename(".current_coin", ".current_coin.old")
        logger.info(
            ".current_coin renamed to .current_coin.old - You can now delete this file"
        )

    if os.path.isfile(".current_coin_table"):
        with open(".current_coin_table", "r") as f:
            logger.info(".current_coin_table file found, loading into database")
            table: dict = json.load(f)
            session: Session
            with db.db_session() as session:
                for from_coin, to_coin_dict in table.items():
                    for to_coin, ratio in to_coin_dict.items():
                        if from_coin == to_coin:
                            continue
                        pair = session.merge(db.get_pair(from_coin, to_coin))
                        pair.ratio = ratio
                        session.add(pair)

        os.rename(".current_coin_table", ".current_coin_table.old")
        logger.info(
            ".current_coin_table renamed to .current_coin_table.old - You can now delete this file"
        )


def main():
    if not os.path.isfile("data/crypto_trading.db"):
        logger.info("Creating database schema")
        db.create_database()

    db.set_coins(supported_coin_list)

    migrate_old_state()

    initialize_trade_thresholds()

    if db.get_current_coin() is None:
        current_coin_symbol = config.get(Config.USER_CFG_SECTION, "current_coin")
        if not current_coin_symbol:
            current_coin_symbol = random.choice(supported_coin_list)

        logger.info(f"Setting initial coin to {current_coin_symbol}")

        if current_coin_symbol not in supported_coin_list:
            exit(
                "***\nERROR!\nSince there is no backup file, a proper coin name must be provided at init\n***"
            )
        db.set_current_coin(current_coin_symbol)

        if config.get(Config.USER_CFG_SECTION, "current_coin") == "":
            current_coin = db.get_current_coin()
            logger.info(f"Purchasing {current_coin} to begin trading")
            binance_manager.buy_alt(current_coin, Config.BRIDGE)
            logger.info("Ready to start trading")

    schedule = SafeScheduler(logger)
    schedule.every(5).seconds.do(scout).tag("scouting")
    schedule.every(1).minutes.do(update_values).tag("updating value history")
    schedule.every(1).minutes.do(
        db.prune_scout_history, hours=Config.SCOUT_HISTORY_PRUNE_TIME
    ).tag("pruning scout history")
    schedule.every(1).hours.do(db.prune_value_history).tag("pruning value history")

    while True:
        schedule.run_pending()
        time.sleep(1)


logger = create_logger()

binance_manager = BinanceApiManager(
    Config.BINANCE_API_KEY, Config.BINANCE_API_SECRET_KEY, Config.BINANCE_TLD, logger
)

logger.info("Started")

if __name__ == "__main__":

    main()
