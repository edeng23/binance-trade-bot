import random
import sys
from datetime import datetime

from binance.exceptions import BinanceAPIException
from numpy import format_float_positional

from binance_trade_bot.auto_trader import AutoTrader


class Strategy(AutoTrader):
    def initialize(self):
        super().initialize()
        self.initialize_current_coin()

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

        current_coin_price = all_tickers.get_price(current_coin + self.config.BRIDGE)

        if current_coin_price is None:
            self.logger.info("Skipping scouting... current coin {} not found".format(current_coin + self.config.BRIDGE))
            return

        jump = self._jump_to_best_coin(current_coin, current_coin_price, all_tickers)

        if not jump:
            boost_balance = self.manager.get_currency_balance(self.config.BOOST_SYMBOL)
            if boost_balance > 15:
                order = self.db.get_last_order(current_coin, self.config.BRIDGE, 0, "COMPLETE")
                price = order.crypto_trade_amount / order.alt_trade_amount

                if order is not None and ((current_coin_price - price) / current_coin_price) * 100 > 5:
                    order_quantity = self.manager.buy_quantity(
                        current_coin.symbol, self.config.BOOST_SYMBOL, boost_balance
                    )
                    order_quantity = format_float_positional(order_quantity, trim="-")

                    boost_order_buy = None
                    while boost_order_buy is None:
                        try:
                            boost_order_buy = self.manager.binance_client.order_market_buy(
                                symbol=current_coin.symbol + self.config.BOOST_SYMBOL, quantity=order_quantity
                            )
                            self.logger.info(boost_order_buy)
                        except BinanceAPIException as e:
                            self.logger.info(e)

                    self.logger.info(f"Boosting .... Bought {order_quantity} {current_coin.symbol}")

                    # sell at last order price
                    boost_order_sell = None
                    while boost_order_sell is None:
                        try:
                            boost_order_sell = self.manager.binance_client.order_limit_sell(
                                symbol=current_coin.symbol + self.config.BOOST_SYMBOL,
                                quantity=order_quantity,
                                price=price,
                            )
                            self.logger.info(boost_order_sell)
                        except BinanceAPIException as e:
                            self.logger.info(e)

                    self.logger.info(f"Boosting .... Selling {order_quantity} {current_coin.symbol}")

    def bridge_scout(self):
        current_coin = self.db.get_current_coin()
        if self.manager.get_currency_balance(current_coin.symbol) > self.manager.get_min_notional(
            current_coin.symbol, self.config.BRIDGE.symbol
        ):
            # Only scout if we don't have enough of the current coin
            return
        new_coin = super().bridge_scout()
        if new_coin is not None:
            self.db.set_current_coin(new_coin)

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
