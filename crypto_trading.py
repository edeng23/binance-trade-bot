#!python3
import configparser
import datetime
import json
import os
import random
import time
from typing import List, Dict

from binance_api_manager import BinanceAPIManager
from sqlalchemy.orm import Session

from database import set_coins, set_current_coin, get_current_coin, get_pairs_from, \
    db_session, create_database, get_pair, log_scout, CoinValue, prune_scout_history, prune_value_history, send_update
from models import Coin, Pair
from scheduler import SafeScheduler
from logger import Logger

# Config consts
CFG_FL_NAME = 'user.cfg'
USER_CFG_SECTION = 'binance_user_config'

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

BRIDGE_SYMBOL = config.get(USER_CFG_SECTION, 'bridge')
BRIDGE = Coin(BRIDGE_SYMBOL, False)

# Prune settings
SCOUT_HISTORY_PRUNE_TIME = float(config.get(USER_CFG_SECTION, 'hourToKeepScoutHistory', fallback="1"))

# Get config for scout
SCOUT_TRANSACTION_FEE = float(config.get(USER_CFG_SECTION, 'scout_transaction_fee'))
SCOUT_MULTIPLIER = float(config.get(USER_CFG_SECTION, 'scout_multiplier'))
SCOUT_SLEEP_TIME = int(config.get(USER_CFG_SECTION, 'scout_sleep_time'))

logger = Logger()
logger.info('Started')

supported_coin_list = []

# Get supported coin list from supported_coin_list file
with open('supported_coin_list') as f:
    supported_coin_list = f.read().upper().strip().splitlines()
    supported_coin_list = list(filter(None, supported_coin_list))

def first(iterable, condition=lambda x: True):
    try:
        return next(x for x in iterable if condition(x))
    except StopIteration:
        return None

def get_market_ticker_price_from_list(all_tickers, ticker_symbol):
    '''
    Get ticker price of a specific coin
    '''
    ticker = first(all_tickers, condition=lambda x: x[u'symbol'] == ticker_symbol)
    return float(ticker[u'price']) if ticker else None

def transaction_through_tether(client: BinanceAPIManager, pair: Pair, all_tickers):
    '''
    Jump from the source coin to the destination coin through tether
    '''
    if client.sell_alt(pair.from_coin, BRIDGE) is None:
        logger.info("Couldn't sell, going back to scouting mode...")
        return None
    # This isn't pretty, but at the moment we don't have implemented logic to escape from a bridge coin... This'll do for now
    result = None
    while result is None:
        result = client.buy_alt(pair.to_coin, BRIDGE, all_tickers)

    set_current_coin(pair.to_coin)
    update_trade_threshold(client, float(result[u'price']), all_tickers)


def update_trade_threshold(client: BinanceAPIManager, current_coin_price:float, all_tickers):
    '''
    Update all the coins with the threshold of buying the current held coin
    '''

    current_coin = get_current_coin()

    if current_coin_price is None:
        logger.info("Skipping update... current coin {0} not found".format(current_coin + BRIDGE))
        return

    session: Session
    with db_session() as session:
        for pair in session.query(Pair).filter(Pair.to_coin == current_coin):
            from_coin_price = get_market_ticker_price_from_list(all_tickers, pair.from_coin + BRIDGE)

            if from_coin_price is None:
                logger.info("Skipping update for coin {0} not found".format(pair.from_coin + BRIDGE))
                continue

            pair.ratio = from_coin_price / current_coin_price


def initialize_trade_thresholds(client: BinanceAPIManager):
    '''
    Initialize the buying threshold of all the coins for trading between them
    '''

    all_tickers = client.get_all_market_tickers()

    session: Session
    with db_session() as session:
        for pair in session.query(Pair).filter(Pair.ratio == None).all():
            if not pair.from_coin.enabled or not pair.to_coin.enabled:
                continue
            logger.info("Initializing {0} vs {1}".format(pair.from_coin, pair.to_coin))

            from_coin_price = get_market_ticker_price_from_list(all_tickers, pair.from_coin + BRIDGE)
            if from_coin_price is None:
                logger.info("Skipping initializing {0}, symbol not found".format(pair.from_coin + BRIDGE))
                continue

            to_coin_price = get_market_ticker_price_from_list(all_tickers, pair.to_coin + BRIDGE)
            if to_coin_price is None:
                logger.info("Skipping initializing {0}, symbol not found".format(pair.to_coin + BRIDGE))
                continue

            pair.ratio = from_coin_price / to_coin_price


def scout(client: BinanceAPIManager, transaction_fee=0.001, multiplier=5):
    '''
    Scout for potential jumps from the current coin to another coin
    '''

    all_tickers = client.get_all_market_tickers()

    current_coin = get_current_coin()
    #Display on the console, the current coin+Bridge, so users can see *some* activity and not thinkg the bot has stopped. Not logging though to reduce log size.
    print( str( datetime.datetime.now() ) + " - CONSOLE - INFO - I am scouting the best trades. Current coin: {0} ".format( current_coin + BRIDGE ) , end='\r')

    current_coin_price = get_market_ticker_price_from_list(all_tickers, current_coin + BRIDGE)

    if current_coin_price is None:
        logger.info("Skipping scouting... current coin {0} not found".format(current_coin + BRIDGE))
        return

    ratio_dict: Dict[Pair, float] = {}

    for pair in get_pairs_from(current_coin):
        if not pair.to_coin.enabled:
            continue
        optional_coin_price = get_market_ticker_price_from_list(all_tickers, pair.to_coin + BRIDGE)

        if optional_coin_price is None:
            logger.info("Skipping scouting... optional coin {0} not found".format(pair.to_coin + BRIDGE))
            continue

        log_scout(pair, pair.ratio, current_coin_price, optional_coin_price)

        # Obtain (current coin)/(optional coin)
        coin_opt_coin_ratio = current_coin_price / optional_coin_price

        # save ratio so we can pick the best option, not necessarily the first
        ratio_dict[pair] = (coin_opt_coin_ratio - transaction_fee * multiplier * coin_opt_coin_ratio) - pair.ratio

    # keep only ratios bigger than zero
    ratio_dict = {k: v for k, v in ratio_dict.items() if v > 0}

    # if we have any viable options, pick the one with the biggest ratio
    if ratio_dict:
        best_pair = max(ratio_dict, key=ratio_dict.get)
        logger.info('Will be jumping from {0} to {1}'.format(
            current_coin, best_pair.to_coin_id))
        transaction_through_tether(
            client, best_pair, all_tickers)


def update_values(client: BinanceAPIManager):
    all_ticker_values = client.get_all_market_tickers()

    now = datetime.datetime.now()

    session: Session
    with db_session() as session:
        coins: List[Coin] = session.query(Coin).all()
        for coin in coins:
            balance = client.get_currency_balance(coin.symbol)
            if balance == 0:
                continue
            usd_value = get_market_ticker_price_from_list(all_ticker_values, coin + "USDT")
            btc_value = get_market_ticker_price_from_list(all_ticker_values, coin + "BTC")
            cv = CoinValue(coin, balance, usd_value, btc_value, datetime=now)
            session.add(cv)
            send_update(cv)


def migrate_old_state():
    if os.path.isfile('.current_coin'):
        with open('.current_coin', 'r') as f:
            coin = f.read().strip()
            logger.info(f".current_coin file found, loading current coin {coin}")
            set_current_coin(coin)
        os.rename('.current_coin', '.current_coin.old')
        logger.info(f".current_coin renamed to .current_coin.old - You can now delete this file")

    if os.path.isfile('.current_coin_table'):
        with open('.current_coin_table', 'r') as f:
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

        os.rename('.current_coin_table', '.current_coin_table.old')
        logger.info(f".current_coin_table renamed to .current_coin_table.old - You can now delete this file")


def main():
    api_key = config.get(USER_CFG_SECTION, 'api_key')
    api_secret_key = config.get(USER_CFG_SECTION, 'api_secret_key')
    tld = config.get(USER_CFG_SECTION, 'tld')

    client = BinanceAPIManager(api_key, api_secret_key, tld, logger)

    logger.info("Creating database schema if it doesn't already exist")
    create_database()

    set_coins(supported_coin_list)

    migrate_old_state()

    initialize_trade_thresholds(client)

    if get_current_coin() is None:
        current_coin_symbol = config.get(USER_CFG_SECTION, 'current_coin')
        if not current_coin_symbol:
            current_coin_symbol = random.choice(supported_coin_list)

        logger.info("Setting initial coin to {0}".format(current_coin_symbol))

        if current_coin_symbol not in supported_coin_list:
            exit("***\nERROR!\nSince there is no backup file, a proper coin name must be provided at init\n***")
        set_current_coin(current_coin_symbol)

        if config.get(USER_CFG_SECTION, 'current_coin') == '':
            current_coin = get_current_coin()
            logger.info("Purchasing {0} to begin trading".format(current_coin))
            all_tickers = client.get_all_market_tickers()
            client.buy_alt(current_coin, BRIDGE, all_tickers)
            logger.info("Ready to start trading")

    schedule = SafeScheduler(logger)
    schedule.every(SCOUT_SLEEP_TIME).seconds.do(scout,
                                                client=client,
                                                transaction_fee=SCOUT_TRANSACTION_FEE,
                                                multiplier=SCOUT_MULTIPLIER).tag("scouting")
    schedule.every(1).minutes.do(update_values, client=client).tag("updating value history")
    schedule.every(1).minutes.do(prune_scout_history, hours=SCOUT_HISTORY_PRUNE_TIME).tag("pruning scout history")
    schedule.every(1).hours.do(prune_value_history).tag("pruning value history")

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
