from collections import defaultdict
from datetime import datetime, timedelta
from traceback import format_exc
from typing import Dict
from sqlalchemy.orm.session import Session
import io
import requests
import xmltodict
import zipfile

from pebble import ProcessPool
from concurrent.futures import TimeoutError
from diskcache import Cache

from .binance_api_manager import BinanceAPIManager
from .binance_stream_manager import BinanceOrder
from .config import Config
from .database import Database
from .logger import Logger
from .models import Coin, Pair, Trade, TradeState
from .strategies import get_strategy

cache = Cache("data", size_limit=int(1e11))


def download(link):
    r = requests.get(link, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0',
        'Accept-Language': 'en-US,en;q=0.5', 'Origin': 'https://data.binance.vision',
        'Referer': 'https://data.binance.vision/'})
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        f = z.infolist()[0]
        return z.open(f).read()


def mergecsv(f):
    res = []
    for result in f.decode().split('\n'):
        result = result.rstrip().split(',')
        if len(result) >= 1 and result[0] != '':
            res.append([float(x) for x in result])
    return res


def addtocache(link):
    f = download(link)
    lines = mergecsv(f)
    ticker_symbol = link.split('klines/')[-1].split('/')[0]
    dates = []
    for result in lines:
        date = datetime.utcfromtimestamp(result[0] / 1000)
        datestr = date.strftime("%d %b %Y %H:%M:%S")
        dates.append(date)
        price = float(result[1])
        cache[f"{ticker_symbol} - {datestr}"] = price

    if len(dates) > 2:
        dateDiff =  dates[1] - dates[0]

        lastDate = dates[-1]
        date = dates[0]
        while date <= lastDate:
            datestr = date.strftime("%d %b %Y %H:%M:%S")
            price = cache.get(f"{ticker_symbol} - {datestr}", None)
            if price is None:
                cache[f"{ticker_symbol} - {datestr}"] = "Missing"
            date += dateDiff

    return link


class MockBinanceManager(BinanceAPIManager):
    def __init__(
            self,
            config: Config,
            db: Database,
            logger: Logger,
            start_date: datetime = None,
            start_balances: Dict[str, float] = None,
    ):
        super().__init__(config, db, logger)
        self.config = config
        self.datetime = start_date or datetime(2021, 1, 1)
        self.balances = start_balances or {config.BRIDGE.symbol: 100}
        self.ignored_symbols = ["BTTBTC"]
        self.trades = 0
        self.paid_fees = {}

    def now(self):
        return self.datetime

    def setup_websockets(self):
        pass  # No websockets are needed for backtesting

    def increment(self, interval=1):
        self.datetime += timedelta(minutes=interval)

    def get_fee(self, origin_coin: Coin, target_coin: Coin, selling: bool):
        if self.config.TRADE_FEE != "auto":
            return float(self.config.TRADE_FEE)
            
        return 0.001

    def get_historical_klines(self, ticker_symbol='ETCUSDT', interval='1m', target_date=None, end_date=None, limit=None,
                              frame='daily'):
        fromdate = datetime.strptime(target_date, "%d %b %Y %H:%M:%S")  # - timedelta(days=1)
        r = requests.get(
            f'https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/spot/{frame}/klines/{ticker_symbol}/{interval}/',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0',
                     'Accept-Language': 'en-US,en;q=0.5', 'Origin': 'https://data.binance.vision',
                     'Referer': 'https://data.binance.vision/'})
        if 'ListBucketResult' not in r.content.decode():    return []
        data = xmltodict.parse(r.content)
        if 'Contents' not in data['ListBucketResult']:    return []
        links = []
        for i in data['ListBucketResult']['Contents']:
            if 'CHECKSUM' in i['Key']:    continue
            filedate = i['Key'].split(interval)[-1].split('.')[0]
            if frame == 'daily':
                filedate = datetime.strptime(filedate, "-%Y-%m-%d")
            else:
                filedate = datetime.strptime(filedate, "-%Y-%m")
            if filedate.date().month == fromdate.date().month and filedate.date().year == fromdate.date().year:
                links.append('https://data.binance.vision/' + i['Key'])
        if len(links) == 0 and frame == 'daily':
            return self.get_historical_klines(ticker_symbol, interval, target_date, end_date, limit, frame='monthly')

        while len(links) >= 1:
            with ProcessPool() as pool:
                future = pool.map(addtocache, links, timeout=30)

                iterator = future.result()

                while True:
                    try:
                        result = next(iterator)
                        links.remove(result)
                    except StopIteration:
                        break
                    except TimeoutError as error:
                        self.logger.info(f"Download of prices for {ticker_symbol} between {target_date} and {end_date} took longer than {error.args[1]} seconds. Retrying")
                    except ConnectionError as error:
                        self.logger.info(f"Download of prices for {ticker_symbol} between {target_date} and {end_date} failed. Retrying")

    def get_buy_price(self, ticker_symbol: str):
        return self.get_ticker_price(ticker_symbol)

    def get_sell_price(self, ticker_symbol: str):
        return self.get_ticker_price(ticker_symbol)

    def get_ticker_price(self, ticker_symbol: str):
        """
        Get ticker price of a specific coin
        """
        target_date = self.datetime.strftime("%d %b %Y %H:%M:%S")
        key = f"{ticker_symbol} - {target_date}"
        val = cache.get(key, None)
        if val == "Missing":
            return None
        if val is None and self.ignored_symbols.count(ticker_symbol) == 0:
            end_date = self.datetime + timedelta(minutes=1000)
            if end_date > datetime.now():
                end_date = datetime.now()
            end_date_str = end_date.strftime("%d %b %Y %H:%M:%S")
            self.logger.info(f"Fetching prices for {ticker_symbol} between {self.datetime} and {end_date_str}")
            self.get_historical_klines(ticker_symbol, "1m", target_date, end_date_str, limit=1000)
            val = cache.get(key, None)
            if val == None:
                cache.set(key, "Missing")
                current_date = self.datetime + timedelta(minutes=1)
                while current_date <= end_date:
                    current_date_str = current_date.strftime("%d %b %Y %H:%M:%S")
                    current_key = f"{ticker_symbol} - {current_date_str}"
                    current_val = cache.get(current_key, None)
                    if current_val == None:
                        cache.set(current_key, "Missing")
                    current_date = current_date + timedelta(minutes=1)
        return val

    def get_currency_balance(self, currency_symbol: str, force=False):
        """
        Get balance of a specific coin
        """
        return self.balances.get(currency_symbol, 0)

    def buy_alt(self, origin_coin: Coin, target_coin: Coin, buy_price: float):
        origin_symbol = origin_coin.symbol
        target_symbol = target_coin.symbol

        target_balance = self.get_currency_balance(target_symbol)
        from_coin_price = self.get_ticker_price(origin_symbol + target_symbol)

        order_quantity = self._buy_quantity(origin_symbol, target_symbol, target_balance, from_coin_price)
        target_quantity = order_quantity * from_coin_price
        fee = order_quantity * self.get_fee(origin_coin, target_coin, False)
        self.balances[target_symbol] -= target_quantity
        self.balances[origin_symbol] = self.balances.get(origin_symbol, 0) + order_quantity - fee
        if origin_symbol not in self.paid_fees.keys():
            self.paid_fees[origin_symbol] = 0
        self.paid_fees[origin_symbol] += fee
        self.logger.info(
            f"Bought {origin_symbol}, balance now: {self.balances[origin_symbol]} - bridge: "
            f"{self.balances[target_symbol]}"
        )

        event = defaultdict(
            lambda: None,
            order_price=from_coin_price,
            cumulative_quote_asset_transacted_quantity=0.0,
            cumulative_filled_quantity=0.0,
        )

        session: Session
        with self.db.db_session() as session:
            from_coin = session.merge(origin_coin)
            to_coin = session.merge(target_coin)
            trade = Trade(from_coin, to_coin, False)
            trade.datetime = self.datetime
            trade.state = TradeState.COMPLETE
            session.add(trade)
            # Flush so that SQLAlchemy fills in the id column
            session.flush()
            self.db.send_update(trade)

        self.trades += 1
        return BinanceOrder(event)

    def sell_alt(self, origin_coin: Coin, target_coin: Coin, sell_price: float):
        origin_symbol = origin_coin.symbol
        target_symbol = target_coin.symbol

        origin_balance = self.get_currency_balance(origin_symbol)
        from_coin_price = self.get_ticker_price(origin_symbol + target_symbol)

        order_quantity = self._sell_quantity(origin_symbol, target_symbol, origin_balance)
        target_quantity = order_quantity * from_coin_price

        fee = target_quantity * self.get_fee(origin_coin, target_coin, True)
        self.balances[target_symbol] = self.balances.get(target_symbol, 0) + target_quantity - fee
        if target_symbol not in self.paid_fees.keys():
            self.paid_fees[target_symbol] = 0
        self.paid_fees[target_symbol] += fee
        self.balances[origin_symbol] -= order_quantity
        self.logger.info(
            f"Sold {origin_symbol}, balance now: {self.balances[origin_symbol]} - bridge: "
            f"{self.balances[target_symbol]}"
        )
        
        self.trades += 1
        return {"price": from_coin_price}

    def collate_coins(self, target_symbol: str):      
        return self.collate(target_symbol, self.balances)

    def collate_fees(self, target_symbol: str):        
        return self.collate(target_symbol, self.paid_fees)

    def collate(self, target_symbol: str, balances: dict):
        total = 0
        for coin, balance in balances.items():
            if coin == target_symbol:
                total += balance
                continue
            if coin == self.config.BRIDGE.symbol:
                price = self.get_ticker_price(target_symbol + coin)
                if price is None:
                    continue
                total += balance / price
            else:
                price = self.get_ticker_price(coin + target_symbol)
                if price is None:
                    continue
                total += price * balance
        return total 

class MockDatabase(Database):
    def __init__(self, logger: Logger, config: Config):
        super().__init__(logger, config, "sqlite:///", True)

    def log_scout(self, pair: Pair, target_ratio: float, current_coin_price: float, other_coin_price: float):
        pass


def backtest(
        start_date: datetime = None,
        end_date: datetime = None,
        interval=1,
        yield_interval=100,
        start_balances: Dict[str, float] = None,
        starting_coin: str = None,
        config: Config = None,
):
    """

    :param config: Configuration object to use
    :param start_date: Date to  backtest from
    :param end_date: Date to backtest up to
    :param interval: Number of virtual minutes between each scout
    :param yield_interval: After how many intervals should the manager be yielded
    :param start_balances: A dictionary of initial coin values. Default: {BRIDGE: 100}
    :param starting_coin: The coin to start on. Default: first coin in coin list

    :return: The final coin balances
    """
    config = config or Config()
    logger = Logger("backtesting", enable_notifications=False)

    end_date = end_date or datetime.today()

    db = MockDatabase(logger, config)
    db.create_database()
    db.set_coins(config.SUPPORTED_COIN_LIST)
    manager = MockBinanceManager(config, db, logger, start_date, start_balances)

    starting_coin = db.get_coin(starting_coin or config.SUPPORTED_COIN_LIST[0])
    if manager.get_currency_balance(starting_coin.symbol) == 0:
        manager.buy_alt(starting_coin, config.BRIDGE, 0.0)  # doesn't matter mocking manager don't look at fixed price
    db.set_current_coin(starting_coin)

    strategy = get_strategy(config.STRATEGY)
    if strategy is None:
        logger.error("Invalid strategy name")
        return manager
    trader = strategy(manager, db, logger, config)
    trader.initialize()

    yield manager

    n = 1
    try:
        while manager.datetime < end_date:
            try:
                trader.scout()
            except Exception:  # pylint: disable=broad-except
                logger.warning(format_exc())
            manager.increment(interval)
            if n % yield_interval == 0:
                yield manager
            n += 1
    except KeyboardInterrupt:
        pass
    cache.close()
    return manager
