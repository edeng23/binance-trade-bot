from datetime import datetime

from binance_trade_bot.auto_trader import AutoTrader

self.elon_bot = ElonBot(config, binance_manager, false)

def elon_bot(self)
        """
        Check Elons tweets to see if he's done anything crazy related to crypto
        """
        if self.elon_bot is not None
          self.elon_bot.run()
          self.update_values()



class Strategy(AutoTrader):
    def initialize(self):
        super().initialize()
        elon_bot = ElonBot(config, false)
        if elon_bot is None
            raise Exception("Trying to run ElonBot with bad config, skipping")

    def scout(self):
        """
        Scout for potential tweets from Elons twiter
        """
        ticker = elon_bot.has_crypto_tweet()
        if ticker is None:
          self.logger.info("No crypto tweet found, going back to scouting")
          return None

        # have_coin = False

        # # last coin bought
        # current_coin = self.db.get_current_coin()
        # current_coin_symbol = ""

        # if current_coin is not None:
        #     current_coin_symbol = current_coin.symbol

        # for coin in self.db.get_coins():
        #     current_coin_balance = self.manager.get_currency_balance(coin.symbol)
        #     coin_price = all_tickers.get_price(coin + self.config.BRIDGE)

        #     if coin_price is None:
        #         self.logger.info("Skipping scouting... current coin {} not found".format(coin + self.config.BRIDGE))
        #         continue

        #     min_notional = self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol)

        #     if coin.symbol != current_coin_symbol and coin_price * current_coin_balance < min_notional:
        #         continue

        #     have_coin = True

        #     # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot
        #     # has stopped. Not logging though to reduce log size.
        #     print(
        #         f"{datetime.now()} - CONSOLE - INFO - I am scouting the best trades. "
        #         f"Current coin: {current_coin + self.config.BRIDGE} ",
        #         end="\r",
        #     )

        # if not have_coin:
        #     self.bridge_scout()
        # self.logger.info("")

        coin = Coin(ticker)
        #elon_bot.trade(coin)

        pair = self.db.get_pair(ticker, self.config.BRIDGE)
          if pair is None
            pair = self.db.get_pair(self.config.BRIDGE, ticker)
            if pair is None
              self.logger.error("Could not find pair between {} and {}".format(ticker, self.config.BRIDGE))
              return None        
        if self.transaction_through_bridge(pair, self.manager.get_all_market_tickers()) is None
          return None

        self.logger.info('Waiting {} seconds for before sell'.format(elon_bot.auto_sell_delay))
        time.sleep(self.auto_sell_delay)

        if self.transaction_through_bridge(pair, self.manager.get_all_market_tickers()) is None
          return None
