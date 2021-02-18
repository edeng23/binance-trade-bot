#!python3
from binance.client import Client
from binance.exceptions import BinanceAPIException
import logging
import logging.handlers
import math
import time
import os
import json
import configparser
from logging import Handler, Formatter
import datetime
import requests
import random
import queue

# Config consts
CFG_FL_NAME = 'user.cfg'
USER_CFG_SECTION = 'binance_user_config'

# Init config
config = configparser.ConfigParser()
if not os.path.exists(CFG_FL_NAME):
    print('No configuration file (user.cfg) found! See README.')
    exit()
config.read(CFG_FL_NAME)

# Logger setup
logger = logging.getLogger('crypto_trader_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh = logging.FileHandler('crypto_trading.log')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)

# logging to console
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
logger.addHandler(ch)

# Telegram bot
TELEGRAM_CHAT_ID = config.get(USER_CFG_SECTION, 'botChatID')
TELEGRAM_TOKEN = config.get(USER_CFG_SECTION, 'botToken')
BRIDGE = config.get(USER_CFG_SECTION, 'botToken')

class RequestsHandler(Handler):
    def emit(self, record):
        log_entry = self.format(record)
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': log_entry,
            'parse_mode': 'HTML'
        }
        return requests.post("https://api.telegram.org/bot{token}/sendMessage".format(token=TELEGRAM_TOKEN),data=payload).content

class LogstashFormatter(Formatter):
    def __init__(self):
        super(LogstashFormatter, self).__init__()

    def format(self, record):
        t = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        if isinstance(record.msg, dict):
            message = "<i>{datetime}</i>".format(datetime=t)

            for key in record.msg:
                message = message + ("<pre>\n{title}: <strong>{value}</strong></pre>".format(title=key, value=record.msg[key]))

            return message
        else:
            return "<i>{datetime}</i><pre>\n{message}</pre>".format(message=record.msg, datetime=t)

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

logger.info('Started')

supported_coin_list = []

# Get supported coin list from supported_coin_list file
with open('supported_coin_list') as f:
    supported_coin_list = f.read().upper().splitlines()

# Init config
config = configparser.ConfigParser()
if not os.path.exists(CFG_FL_NAME):
    print('No configuration file (user.cfg) found! See README.')
    exit()
config.read(CFG_FL_NAME)

class CryptoState():
    _coin_backup_file = ".current_coin"
    _table_backup_file = ".current_coin_table"

    def __init__(self):
        if(os.path.isfile(self._coin_backup_file) and os.path.isfile(self._table_backup_file)):
            with open(self._coin_backup_file, "r") as backup_file:
                coin = backup_file.read()
            with open(self._table_backup_file, "r") as backup_file:
                coin_table = json.load(backup_file)
            self.current_coin = coin
            self.coin_table = coin_table
        else:

            current_coin = config.get(USER_CFG_SECTION, 'current_coin')

            if not current_coin:

                current_coin = random.choice(supported_coin_list)

            logger.info("Setting initial coin to {0}".format(current_coin))

            if (not current_coin in supported_coin_list):
                exit(
                    "***\nERROR!\nSince there is no backup file, a proper coin name must be provided at init\n***")
            self.current_coin = current_coin
            with open(self._coin_backup_file, "w") as backup_file:
                backup_file.write(self.current_coin)
            # Dictionary of coin dictionaries.
            # Designated to keep track of the selling point for each coin with respect to all other coins.
            self.coin_table = dict((coin_entry, dict((coin, 0) for coin in supported_coin_list if coin != coin_entry))
                                   for coin_entry in supported_coin_list)

    def __setattr__(self, name, value):
        if name == "current_coin":
            with open(self._coin_backup_file, "w") as backup_file:
                backup_file.write(value)
        self.__dict__[name] = value
        return

g_state = CryptoState()


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

def first(iterable, condition = lambda x: True):
    try:
        return next(x for x in iterable if condition(x))
    except StopIteration:
        return None


def get_all_market_tickers(client):
    '''
    Get ticker price of all coins
    '''
    return client.get_all_tickers()


def get_market_ticker_price(client, ticker_symbol):
    '''
    Get ticker price of a specific coin
    '''
    for ticker in client.get_symbol_ticker():
        if ticker[u'symbol'] == ticker_symbol:
            return float(ticker[u'price'])
    return None


def get_market_ticker_price_from_list(all_tickers, ticker_symbol):
    '''
    Get ticker price of a specific coin
    '''
    ticker = first(all_tickers, condition=lambda x: x[u'symbol'] == ticker_symbol)
    return float(ticker[u'price']) if ticker else None


def get_currency_balance(client, currency_symbol):
    '''
    Get balance of a specific coin
    '''
    for currency_balance in client.get_account()[u'balances']:
        if currency_balance[u'asset'] == currency_symbol:
            return float(currency_balance[u'free'])
    return None


@retry(20)
def buy_alt(client, alt_symbol, crypto_symbol):
    '''
    Buy altcoin
    '''
    ticks = {}
    for filt in client.get_symbol_info(alt_symbol + crypto_symbol)['filters']:
        if filt['filterType'] == 'LOT_SIZE':
            ticks[alt_symbol] = filt['stepSize'].find('1') - 2
            break

    order_quantity = ((math.floor(get_currency_balance(client, crypto_symbol) *
                                  10**ticks[alt_symbol] / get_market_ticker_price(client, alt_symbol+crypto_symbol))/float(10**ticks[alt_symbol])))
    logger.info('BUY QTY {0}'.format(order_quantity))

    # Try to buy until successful
    order = None
    while order is None:
        try:
            order = client.order_limit_buy(
                symbol=alt_symbol + crypto_symbol,
                quantity=order_quantity,
                price=get_market_ticker_price(client, alt_symbol+crypto_symbol)
            )
            logger.info(order)
        except BinanceAPIException as e:
            logger.info(e)
            time.sleep(1)
        except Exception as e:
            logger.info("Unexpected Error: {0}".format(e))

    order_recorded = False
    while not order_recorded:
        try:
            time.sleep(3)
            stat = client.get_order(symbol=alt_symbol + crypto_symbol, orderId=order[u'orderId'])
            order_recorded = True
        except BinanceAPIException as e:
            logger.info(e)
            time.sleep(10)
        except Exception as e:
            logger.info("Unexpected Error: {0}".format(e))
    while stat[u'status'] != 'FILLED':
        try:
            stat = client.get_order(
                symbol=alt_symbol+crypto_symbol, orderId=order[u'orderId'])
            time.sleep(1)
        except BinanceAPIException as e:
            logger.info(e)
            time.sleep(2)
        except Exception as e:
            logger.info("Unexpected Error: {0}".format(e))

    logger.info('Bought {0}'.format(alt_symbol))

    return order


@retry(20)
def sell_alt(client, alt_symbol, crypto_symbol):
    '''
    Sell altcoin
    '''
    ticks = {}
    for filt in client.get_symbol_info(alt_symbol + crypto_symbol)['filters']:
        if filt['filterType'] == 'LOT_SIZE':
            ticks[alt_symbol] = filt['stepSize'].find('1') - 2
            break

    order_quantity = (math.floor(get_currency_balance(client, alt_symbol) *
                                 10**ticks[alt_symbol])/float(10**ticks[alt_symbol]))
    logger.info('Selling {0} of {1}'.format(order_quantity, alt_symbol))

    bal = get_currency_balance(client, alt_symbol)
    logger.info('Balance is {0}'.format(bal))
    order = None
    while order is None:
        order = client.order_market_sell(
            symbol=alt_symbol + crypto_symbol,
            quantity=(order_quantity)
        )

    logger.info('order')
    logger.info(order)

    # Binance server can take some time to save the order
    logger.info("Waiting for Binance")
    time.sleep(5)
    order_recorded = False
    stat = None
    while not order_recorded:
        try:
            time.sleep(3)
            stat = client.get_order(symbol=alt_symbol + crypto_symbol, orderId=order[u'orderId'])
            order_recorded = True
        except BinanceAPIException as e:
            logger.info(e)
            time.sleep(10)
        except Exception as e:
            logger.info("Unexpected Error: {0}".format(e))

    logger.info(stat)
    while stat[u'status'] != 'FILLED':
        logger.info(stat)
        try:
            stat = client.get_order(
                symbol=alt_symbol+crypto_symbol, orderId=order[u'orderId'])
            time.sleep(1)
        except BinanceAPIException as e:
            logger.info(e)
            time.sleep(2)
        except Exception as e:
            logger.info("Unexpected Error: {0}".format(e))

    newbal = get_currency_balance(client, alt_symbol)
    while(newbal >= bal):
        newbal = get_currency_balance(client, alt_symbol)

    logger.info('Sold {0}'.format(alt_symbol))

    return order


def transaction_through_tether(client, source_coin, dest_coin):
    '''
    Jump from the source coin to the destination coin through tether
    '''
    result = None
    while result is None:
        result = sell_alt(client, source_coin, BRIDGE)
    result = None
    while result is None:
        result = buy_alt(client, dest_coin, BRIDGE)
    global g_state
    g_state.current_coin = dest_coin
    update_trade_threshold(client)


def update_trade_threshold(client):
    '''
    Update all the coins with the threshold of buying the current held coin
    '''

    all_tickers = get_all_market_tickers(client)

    global g_state
    
    current_coin_price = get_market_ticker_price_from_list(all_tickers, g_state.current_coin + BRIDGE)

    if current_coin_price is None:
        logger.info("Skipping update... current coin {0} not found".format(g_state.current_coin + BRIDGE))
        return

    for coin_dict in g_state.coin_table.copy():
        coin_dict_price = get_market_ticker_price_from_list(all_tickers, coin_dict + BRIDGE)
        
        if coin_dict_price is None:
            logger.info("Skipping update for coin {0} not found".format(coin_dict + BRIDGE))
            continue

        g_state.coin_table[coin_dict][g_state.current_coin] = coin_dict_price/current_coin_price
    with open(g_state._table_backup_file, "w") as backup_file:
        json.dump(g_state.coin_table, backup_file)


def initialize_trade_thresholds(client):
    '''
    Initialize the buying threshold of all the coins for trading between them
    '''
    
    all_tickers = get_all_market_tickers(client)
    
    global g_state
    for coin_dict in g_state.coin_table.copy():
        coin_dict_price = get_market_ticker_price_from_list(all_tickers, coin_dict + BRIDGE)
        
        if coin_dict_price is None:
            logger.info("Skipping initializing {0}, symbol not found".format(coin_dict + BRIDGE))
            continue

        for coin in supported_coin_list:
            logger.info("Initializing {0} vs {1}".format(coin_dict, coin))
            if coin != coin_dict:
                coin_price = get_market_ticker_price_from_list(all_tickers, coin + BRIDGE)

                if coin_price is None:
                    logger.info("Skipping initializing {0}, symbol not found".format(coin + BRIDGE))
                    continue

                g_state.coin_table[coin_dict][coin] = coin_dict_price / coin_price

    logger.info("Done initializing, generating file")
    with open(g_state._table_backup_file, "w") as backup_file:
        json.dump(g_state.coin_table, backup_file)


def scout(client, transaction_fee=0.001, multiplier=5):
    '''
    Scout for potential jumps from the current coin to another coin
    '''

    all_tickers = get_all_market_tickers(client)

    global g_state
    
    current_coin_price = get_market_ticker_price_from_list(all_tickers, g_state.current_coin + BRIDGE)
    
    if current_coin_price is None:
        logger.info("Skipping scouting... current coin {0} not found".format(g_state.current_coin + BRIDGE))
        return

    for optional_coin in [coin for coin in g_state.coin_table[g_state.current_coin].copy() if coin != g_state.current_coin]:
        optional_coin_price =  get_market_ticker_price_from_list(all_tickers, optional_coin + BRIDGE)

        if optional_coin_price is None:
            logger.info("Skipping scouting... optional coin {0} not found".format(optional_coin + BRIDGE))
            continue

        # Obtain (current coin)/(optional coin)
        coin_opt_coin_ratio = current_coin_price / \
           optional_coin_price

        if (coin_opt_coin_ratio - transaction_fee * multiplier * coin_opt_coin_ratio) > g_state.coin_table[g_state.current_coin][optional_coin]:
            logger.info('Will be jumping from {0} to {1}'.format(
                g_state.current_coin, optional_coin))
            transaction_through_tether(
                client, g_state.current_coin, optional_coin)
            break


def main():
    api_key = config.get(USER_CFG_SECTION, 'api_key')
    api_secret_key = config.get(USER_CFG_SECTION, 'api_secret_key')

    client = Client(api_key, api_secret_key)

    global g_state
    if not (os.path.isfile(g_state._table_backup_file)):
        initialize_trade_thresholds(client)
        if config.get(USER_CFG_SECTION, 'current_coin') == '':
            logger.info("Purchasing {0} to begin trading".format(g_state.current_coin))
            buy_alt(client, g_state.current_coin, BRIDGE)
            logger.info("Ready to start trading")

    while True:
        try:
            time.sleep(5)
            scout(client)
        except Exception as e:
            logger.info('Error while scouting...\n{}\n'.format(e))


if __name__ == "__main__":
    main()
