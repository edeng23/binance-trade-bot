from binance_trade_bot.utils import get_market_ticker_price_from_list


class TestUtils:
    ETC_BTC = {"symbol": "ETHBTC", "price": "0.07946600"}

    LTC_BTC_PRICE = 4.00000200
    LTC_BTC_SYMBOL = "LTCBTC"
    LTC_BTC = {"symbol": LTC_BTC_SYMBOL, "price": str(LTC_BTC_PRICE)}

    def test_get_market_price_empty_tickers_list(self):
        price = get_market_ticker_price_from_list([], self.LTC_BTC_SYMBOL)
        assert price is None

    def test_get_market_price_ticker_not_found(self):
        price = get_market_ticker_price_from_list([self.ETC_BTC], self.LTC_BTC_SYMBOL)
        assert price is None

    def test_get_market_price_ltc_btc(self):
        price = get_market_ticker_price_from_list([self.LTC_BTC, self.ETC_BTC], self.LTC_BTC_SYMBOL)
        assert price == self.LTC_BTC_PRICE

    def test_get_market_price_duplicate_symbols(self):
        duplicated_btc_ltc = {"symbol": self.LTC_BTC_SYMBOL, "price": "0.07946600"}
        price = get_market_ticker_price_from_list([self.LTC_BTC, duplicated_btc_ltc], self.LTC_BTC_SYMBOL)
        assert price == self.LTC_BTC_PRICE
