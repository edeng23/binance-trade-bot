def get_market_ticker_price_from_list(all_tickers, ticker_symbol):
    """
    Get ticker price of a specific coin
    """
    ticker = next(
        (ticker for ticker in all_tickers if ticker["symbol"] == ticker_symbol), None
    )
    return float(ticker["price"]) if ticker else None
