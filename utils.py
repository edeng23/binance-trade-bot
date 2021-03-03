def first(iterable, condition=lambda x: True):
    return next((x for x in iterable if condition(x)), None)


def get_market_ticker_price_from_list(all_tickers, ticker_symbol):
    '''
    Get ticker price of a specific coin
    '''
    ticker = first(all_tickers, condition=lambda x: x[u'symbol'] == ticker_symbol)
    return float(ticker[u'price']) if ticker else None
