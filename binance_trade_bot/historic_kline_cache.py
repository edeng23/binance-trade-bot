from datetime import datetime, timedelta, timezone
import io
from binance.client import Client
from binance.exceptions import BinanceAPIException
import requests
import xmltodict
import zipfile

from pebble import ProcessPool
from concurrent.futures import TimeoutError
from diskcache import Cache

from .logger import Logger

cache = Cache("data", size_limit=int(1e12))

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

class HistoricKlineCache:
    def __init__(self, client: Client, logger: Logger):
        self.logger = logger
        self.client = client

    def __del__(self):
        cache.close()

    def get_historical_klines(self, ticker_symbol: str, start_date: datetime, end_date):
        data = []
        current_date = start_date
        while current_date <= end_date:
            price = self.get_historical_ticker_price(ticker_symbol, current_date)
            if price is not None:
                data.append(price)
            
            current_date = current_date + timedelta(minutes=1)

        return data        

    def get_historical_ticker_price(self, ticker_symbol: str, date: datetime):
        """
        Get historic ticker price of a specific coin
        """
        target_date = date.replace(second=0, microsecond=0).strftime("%d %b %Y %H:%M:%S")
        key = f"{ticker_symbol} - {target_date}"
        val = cache.get(key, None)
        if val == "Missing":
            return None
        if val is None:
            end_date = date.replace(second=0, microsecond=0) + timedelta(minutes=1000)
            if end_date > datetime.now().replace(tzinfo=timezone.utc):
                end_date = datetime.now().replace(tzinfo=timezone.utc)
            end_date_str = end_date.strftime("%d %b %Y %H:%M:%S")
            self.logger.info(f"Fetching prices for {ticker_symbol} between {date} and {end_date_str}", False)

            last_day = datetime.now().replace(tzinfo=timezone.utc) - timedelta(days=1)
            if date >= last_day or end_date >= last_day:
                try:
                    data = self.client.get_historical_klines(ticker_symbol,  "1m", target_date, end_date_str, limit=1000)
                    for kline in data:
                        kl_date = datetime.utcfromtimestamp(kline[0] / 1000)
                        kl_datestr = kl_date.strftime("%d %b %Y %H:%M:%S")
                        kl_price = float(kline[1])
                        cache[f"{ticker_symbol} - {kl_datestr}"] = kl_price
                except BinanceAPIException as e:
                    if e.code == -1121: # invalid symbol
                        self.get_historical_klines_from_api(ticker_symbol, "1m", target_date, end_date_str, limit=1000)
                    else:
                        raise e
            else:
                self.get_historical_klines_from_api(ticker_symbol, "1m", target_date, end_date_str, limit=1000)
            val = cache.get(key, None)
            if val == None:
                cache.set(key, "Missing")
                current_date = date + timedelta(minutes=1)
                while current_date <= end_date:
                    current_date_str = current_date.strftime("%d %b %Y %H:%M:%S")
                    current_key = f"{ticker_symbol} - {current_date_str}"
                    current_val = cache.get(current_key, None)
                    if current_val == None:
                        cache.set(current_key, "Missing")
                    current_date = current_date + timedelta(minutes=1)
            if val == "Missing":
                val = None
        return val

    def get_historical_klines_from_api(self, ticker_symbol='ETCUSDT', interval='1m', target_date=None, end_date=None, limit=None,
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
            return self.get_historical_klines_from_api(ticker_symbol, interval, target_date, end_date, limit, frame='monthly')

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