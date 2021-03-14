import random
import sys
from datetime import datetime

from binance_trade_bot.auto_trader import AutoTrader
from binance_trade_bot.models import Pair
from binance_trade_bot.utils import get_market_ticker_price_from_list


class Strategy(AutoTrader):
    def initialize(self):
        super().initialize()
        self.initialize_current_coin()

    def transaction_through_bridge(self, pair: Pair, all_tickers):
        super().transaction_through_bridge(pair, all_tickers)

        self.db.set_current_coin(pair.to_coin)

    def scout(self):
        """
        Scout for potential jumps from the current coin to another coin
        """
        all_tickers = self.manager.get_all_market_tickers()

        current_coin = self.db.get_current_coin()
        # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot has
        # stopped. Not logging though to reduce log size.
        print(
            f"{datetime.now()} - CONSOLE - INFO - I am scouting the best trades. "
            f"Current coin: {current_coin + self.config.BRIDGE} ",
            end="\r",
        )

        current_coin_price = get_market_ticker_price_from_list(all_tickers, current_coin + self.config.BRIDGE)

        if current_coin_price is None:
            self.logger.info("Skipping scouting... current coin {} not found".format(current_coin + self.config.BRIDGE))
            return

        self._jump_to_best_coin(current_coin, current_coin_price, all_tickers)

    def initialize_current_coin(self):
        """
        Decide what is the current coin, and set it up in the DB.
        """
        if self.db.get_current_coin() is None:
            current_coin_symbol = self.config.CURRENT_COIN_SYMBOL
            if not current_coin_symbol:
                current_coin_symbol = random.choice(self.config.SUPPORTED_COIN_LIST)

            self.logger.info(f"Setting initial coin to {current_coin_symbol}")

            if current_coin_symbol not in self.config.SUPPORTED_COIN_LIST:
                sys.exit("***\nERROR!\nSince there is no backup file, a proper coin name must be provided at init\n***")
            self.db.set_current_coin(current_coin_symbol)

            # if we don't have a configuration, we selected a coin at random... Buy it so we can start trading.
            if self.config.CURRENT_COIN_SYMBOL == "":
                current_coin = self.db.get_current_coin()
                self.logger.info(f"Purchasing {current_coin} to begin trading")
                all_tickers = self.manager.get_all_market_tickers()
                self.manager.buy_alt(current_coin, self.config.BRIDGE, all_tickers)
                self.logger.info("Ready to start trading")
