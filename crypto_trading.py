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
    db_session, create_database, get_pair, log_scout, CoinValue, prune_scout_history, prune_value_history, send_update, set_bridge, get_alt_step, set_alt_step, set_scout_executed, \
    get_previous_sell_trade
from models import Coin, Pair, ScoutHistory
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


def transaction_through_bridge(client: BinanceAPIManager, pair: Pair, all_tickers):
    '''
    Jump from the source coin to the destination coin through bridge coin
    '''
    if client.sell_alt(pair.from_coin, BRIDGE, all_tickers) is None:
        logger.info("Couldn't sell, going back to scouting mode...")
        return None
    # This isn't pretty, but at the moment we don't have implemented logic to escape from a bridge coin... This'll do for now
    result = None
    while result is None:
        result = client.buy_alt(pair.to_coin, BRIDGE, all_tickers)

    set_current_coin(pair.to_coin)


def transaction_to_coin(client: BinanceAPIManager, to_coin: Coin, all_tickers):
    '''
    Jump from BRIDGE coin to the destination coin
    '''
    result = None
    while result is None:
        result = client.buy_alt(to_coin, BRIDGE, all_tickers)

    set_current_coin(to_coin)


def initialize_current_coin(client: BinanceAPIManager):
    '''
    Decide what is the current coin, and set it up in the DB.
    '''
    if get_current_coin() is None:
        current_coin_symbol = config.get(USER_CFG_SECTION, 'current_coin')
        if not current_coin_symbol:
            current_coin_symbol = random.choice(supported_coin_list)

        logger.info("Setting initial coin to {0}".format(current_coin_symbol))

        if current_coin_symbol not in supported_coin_list:
            exit("***\nERROR!\nSince there is no backup file, a proper coin name must be provided at init\n***")
        set_current_coin(current_coin_symbol)

        # if we don't have a configuration, we selected a coin at random... Buy it so we can start trading.
        if config.get(USER_CFG_SECTION, 'current_coin') == '':
            current_coin = get_current_coin()
            logger.info("Purchasing {0} to begin trading".format(current_coin))
            all_tickers = client.get_all_market_tickers()
            client.buy_alt(current_coin, BRIDGE, all_tickers)
            logger.info("Ready to start trading")



def initialize_step_sizes(client: BinanceAPIManager, bridge: Coin):
    '''
    Initialize the step sizes of all the coins for trading with the bridge coin
    '''

    session: Session
    with db_session() as session:
        # For all the enabled coins, update the coin tickSize
        for coin in session.query(Coin).filter(Coin.enabled == True).all():
            tick_size = get_alt_step(coin, bridge)
            if tick_size is None:
                set_alt_step(coin, bridge, client.get_alt_tick(coin.symbol, bridge.symbol))


def scout_loop(client: BinanceAPIManager, transaction_fee=0.001, multiplier=5):
    '''
    Outer scout loop, check if we currently have alt or bridge
    '''
    current_coin = get_current_coin()
    if (current_coin.symbol == BRIDGE.symbol):
        scout_bridge(client, BRIDGE, transaction_fee, multiplier)
    else:
        scout_alt(client, current_coin, transaction_fee, multiplier)


def scout_alt(client: BinanceAPIManager, current_coin: Coin, transaction_fee=0.001, multiplier=5):
    '''
    Scout for potential jumps from the current coin to another coin
    '''

    current_coin_balance = client.get_currency_balance(current_coin.symbol)
    all_tickers = client.get_all_market_tickers()
    current_coin_price = get_market_ticker_price_from_list(all_tickers, current_coin + BRIDGE)

    if current_coin_price is None:
        logger.info("Skipping scouting... current coin {0} not found".format(current_coin + BRIDGE))
        return

    possible_bridge_amount = (current_coin_balance * current_coin_price) - ((current_coin_balance * current_coin_price) * transaction_fee * multiplier)

    # Display on the console, the current coin+Bridge,
    # so users can see *some* activity and not thinking the bot has stopped.
    logger.log("Scouting. Current coin: {0} price: {1} {2}: {3}"
                .format(current_coin + BRIDGE, current_coin_price, BRIDGE, possible_bridge_amount), "info", False)

    ratio_dict: Dict[Pair, float, ScoutHistory] = {}

    for pair in get_pairs_from(current_coin):
        if not pair.to_coin.enabled:
            continue
        optional_coin_price = get_market_ticker_price_from_list(all_tickers, pair.to_coin + BRIDGE)

        if optional_coin_price is None:
            logger.info("Skipping scouting... optional coin {0} not found".format(pair.to_coin + BRIDGE))
            continue

        # Obtain (current coin)/(optional coin)
        coin_opt_coin_ratio = current_coin_price / optional_coin_price

        # Skipping... if possible target amount is lower than expected target amount.
        possible_target_amount = (possible_bridge_amount / optional_coin_price) - ((possible_bridge_amount / optional_coin_price) * transaction_fee * multiplier)

        skip_ratio = False
        previous_sell_trade = get_previous_sell_trade(pair.to_coin)
        if previous_sell_trade is not None:
            expected_target_amount = previous_sell_trade.alt_trade_amount
            delta_percentage = (possible_target_amount - expected_target_amount) / expected_target_amount * 100
            if expected_target_amount > possible_target_amount:
                skip_ratio = True
                logger.info("{0: >10} \t\t expected {1: >20f} \t\t actual {2: >20f} \t\t diff {3: >20f}%"
                            .format(pair.from_coin_id + pair.to_coin_id,
                                    expected_target_amount, possible_target_amount, delta_percentage))
            else:
                logger.info("{0: >10} \t\t !!!!!!!! {1: >20f} \t\t actual {2: >20f} \t\t diff {3: >20f}%"
                            .format(pair.from_coin_id + pair.to_coin_id,
                                    expected_target_amount, possible_target_amount, delta_percentage))

            if not skip_ratio:
                # save ratio so we can pick the best option, not necessarily the first
                ls = log_scout(pair, current_coin_price, optional_coin_price)
                ratio_dict[pair] = []
                ratio_dict[pair].append(delta_percentage)
                ratio_dict[pair].append(ls)


    # if we have any viable options, pick the one with the biggest expected target amount
    if ratio_dict:
        best_pair = max(ratio_dict.items(), key=lambda x : x[1][0])
        logger.info('Will be jumping from {0} to {1}'.format(
            current_coin, best_pair[0].to_coin_id))
        set_scout_executed(best_pair[1][1])
        transaction_through_bridge(
            client, best_pair[0], all_tickers)


def scout_bridge(client: BinanceAPIManager, current_coin: Coin, transaction_fee=0.001, multiplier=5):
    '''
    Scout for potential jumps from the bridge coin to another coin
    '''

    bridge_balance = client.get_currency_balance(current_coin.symbol)
    all_tickers = client.get_all_market_tickers()
    # current_coin_price = get_market_ticker_price_from_list(all_tickers, current_coin + BRIDGE)

    # if current_coin_price is None:
    #     logger.info("Skipping scouting... current coin {0} not found".format(current_coin + BRIDGE))
    #     return

    possible_bridge_amount = bridge_balance

    # Display on the console, the current coin+Bridge,
    # so users can see *some* activity and not thinking the bot has stopped.
    logger.log("Scouting. Current coin: {0}: {1}"
                .format(current_coin, possible_bridge_amount), "info", False)

    ratio_dict: Dict[Coin, float, ScoutHistory] = {}

    session: Session
    with db_session() as session:
        # For all the enabled coins, update the coin tickSize
        for coin in session.query(Coin).filter(Coin.enabled == True).all():
            optional_coin_price = get_market_ticker_price_from_list(all_tickers, coin + BRIDGE)

            if optional_coin_price is None:
                logger.info("Skipping scouting... optional coin {0} not found".format(coin + BRIDGE))
                continue

            # Skipping... if possible target amount is lower than expected target amount.
            possible_target_amount = (possible_bridge_amount / optional_coin_price) - ((possible_bridge_amount / optional_coin_price) * transaction_fee * multiplier)

            skip_ratio = False
            previous_sell_trade = get_previous_sell_trade(coin)
            if previous_sell_trade is not None:
                expected_target_amount = previous_sell_trade.alt_trade_amount
                delta_percentage = (possible_target_amount - expected_target_amount) / expected_target_amount * 100
                if expected_target_amount > possible_target_amount:
                    skip_ratio = True
                    logger.info("{0: >10} \t\t expected {1: >20f} \t\t actual {2: >20f} \t\t diff {3: >20f}%"
                                .format(BRIDGE + coin,
                                        expected_target_amount, possible_target_amount, delta_percentage))
                else:
                    logger.info("{0: >10} \t\t !!!!!!!! {1: >20f} \t\t actual {2: >20f} \t\t diff {3: >20f}%"
                                .format(BRIDGE + coin,
                                        expected_target_amount, possible_target_amount, delta_percentage))


                if not skip_ratio:
                    # save ratio so we can pick the best option, not necessarily the first
#                    ls = log_scout(pair, current_coin_price, optional_coin_price)
                    ratio_dict[coin] = []
                    ratio_dict[coin].append(delta_percentage)
                    ratio_dict[coin].append(ls)


        # if we have any viable options, pick the one with the biggest expected target amount
        if ratio_dict:
            best_coin = max(ratio_dict.items(), key=lambda x : x[1][0])
            logger.info('Will be jumping from {0} to {1}'.format(
                current_coin, best_coin[0]))
#            set_scout_executed(best_pair[1][1])
            transaction_to_coin(
                client, best_coin[0], all_tickers)


def update_values(client: BinanceAPIManager):
    '''
    Log current value state of all altcoin balances against BTC and USDT in DB.
    '''
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
    '''
    For migrating from old dotfile format to SQL db. This method should be removed in the future.
    '''
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

    set_bridge(BRIDGE)

    migrate_old_state()

    initialize_step_sizes(client, BRIDGE)

    initialize_current_coin(client)
    
    schedule = SafeScheduler(logger)
    schedule.every(SCOUT_SLEEP_TIME).seconds.do(scout_loop,
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
