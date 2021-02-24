#!python3
import datetime
import logging.handlers
import os
import queue
import random
import time
from logging import Handler, Formatter
from typing import List

import requests
from sqlalchemy.orm import Session

from . import config
from . import database as db
from .auto_trader import AutoTrader
from .binance_api_manager import BinanceApiManager
from .models import Coin
from .scheduler import SafeScheduler
from .utils import get_market_ticker_price_from_list


def create_logger():
    _logger = logging.getLogger("crypto_trader_logger")
    _logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
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
    if config.TELEGRAM_TOKEN:
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
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": log_entry,
            "parse_mode": "HTML",
        }
        return requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage",
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


def update_values(binance_manager: BinanceApiManager):
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


def main():
    logger = create_logger()

    logger.info("Starting")
    binance_manager = BinanceApiManager(
        config.BINANCE_API_KEY,
        config.BINANCE_API_SECRET_KEY,
        config.BINANCE_TLD,
        logger,
    )

    if not os.path.isfile("data/crypto_trading.db"):
        logger.info("Creating database schema")
        db.create_database()

    # Get supported coin list from supported_coin_list file
    with open("supported_coin_list") as f:
        supported_coin_list = f.read().upper().splitlines()

    db.set_coins(supported_coin_list)

    db.migrate_old_state(logger)

    auto_trader = AutoTrader(binance_manager, logger)

    auto_trader.initialize_trade_thresholds()

    if db.get_current_coin() is None:
        starting_coin_symbol = config.STARTING_COIN
        if not starting_coin_symbol:
            starting_coin_symbol = random.choice(supported_coin_list)

        logger.info(f"Setting initial coin to {starting_coin_symbol}")

        if starting_coin_symbol not in supported_coin_list:
            exit(
                "***\nERROR!\nSince there is no backup file, a proper coin name must be provided at init\n***"
            )
        db.set_current_coin(starting_coin_symbol)

        if config.STARTING_COIN == "":
            current_coin = db.get_current_coin()
            logger.info(f"Purchasing {current_coin} to begin trading")
            binance_manager.buy_alt(current_coin, config.BRIDGE)
            logger.info("Ready to start trading")

    logger.info("Started")
    schedule = SafeScheduler(logger)
    schedule.every(5).seconds.do(auto_trader.scout).tag("scouting")
    schedule.every(1).minutes.do(update_values, binance_manager=binance_manager).tag(
        "updating value history"
    )
    schedule.every(1).minutes.do(
        db.prune_scout_history, hours=config.SCOUT_HISTORY_PRUNE_TIME
    ).tag("pruning scout history")
    schedule.every(1).hours.do(db.prune_value_history).tag("pruning value history")

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
