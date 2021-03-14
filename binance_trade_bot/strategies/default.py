import random
import sys
from datetime import datetime
from typing import Dict

from binance_trade_bot.auto_trader import AutoTrader
from binance_trade_bot.models import Pair
from binance_trade_bot.utils import get_market_ticker_price_from_list


class DefaultStrategy(AutoTrader):
    # __name__ = "default"

    def initialise(self):
        super().initialise()
        self.initialize_current_coin()

    def transaction_through_bridge(self, pair: Pair, all_tickers):
        result = super().transaction_through_bridge(pair, all_tickers)

        self.db.set_current_coin(pair.to_coin)
        self.update_trade_threshold(pair.to_coin, float(result["price"]), all_tickers)

    def scout(self):
        """
        Scout for potential jumps from the current coin to another coin
        """
        all_tickers = self.manager.get_all_market_tickers()

        current_coin = self.db.get_current_coin()
        # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot has
        # stopped. Not logging though to reduce log size.
        print(
            str(datetime.now())
            + " - CONSOLE - INFO - I am scouting the best trades. Current coin: {} ".format(
                current_coin + self.config.BRIDGE
            ),
            end="\r",
        )

        current_coin_price = get_market_ticker_price_from_list(all_tickers, current_coin + self.config.BRIDGE)

        if current_coin_price is None:
            self.logger.info("Skipping scouting... current coin {} not found".format(current_coin + self.config.BRIDGE))
            return

        ratio_dict: Dict[Pair, float] = {}

        for pair in self.db.get_pairs_from(current_coin):
            if not pair.to_coin.enabled:
                continue
            optional_coin_price = get_market_ticker_price_from_list(all_tickers, pair.to_coin + self.config.BRIDGE)

            if optional_coin_price is None:
                self.logger.info(
                    "Skipping scouting... optional coin {} not found".format(pair.to_coin + self.config.BRIDGE)
                )
                continue

            self.db.log_scout(pair, pair.ratio, current_coin_price, optional_coin_price)

            # Obtain (current coin)/(optional coin)
            coin_opt_coin_ratio = current_coin_price / optional_coin_price

            transaction_fee = self.manager.get_fee(pair.from_coin, self.config.BRIDGE, True) + self.manager.get_fee(
                pair.to_coin, self.config.BRIDGE, False
            )

            # save ratio so we can pick the best option, not necessarily the first
            ratio_dict[pair] = (
                coin_opt_coin_ratio - transaction_fee * self.config.SCOUT_MULTIPLIER * coin_opt_coin_ratio
            ) - pair.ratio

        # keep only ratios bigger than zero
        ratio_dict = {k: v for k, v in ratio_dict.items() if v > 0}

        # if we have any viable options, pick the one with the biggest ratio
        if ratio_dict:
            best_pair = max(ratio_dict, key=ratio_dict.get)
            self.logger.info(f"Will be jumping from {current_coin} to {best_pair.to_coin_id}")
            self.transaction_through_bridge(best_pair, all_tickers)

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
