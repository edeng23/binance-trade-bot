from binance_trade_bot.auto_trader import AutoTrader


class Strategy(AutoTrader):
    def scout(self):
        """
        Scout for potential jumps from the current coin to another coin
        """
        all_tickers = self.manager.get_all_market_tickers()
        have_coin = False

        # last coin bought
        current_coin = self.db.get_current_coin()
        current_coin_symbol = ""

        if current_coin is not None:
            current_coin_symbol = current_coin.symbol

        for coin in self.db.get_coins():
            current_coin_balance = self.manager.get_currency_balance(coin.symbol)
            coin_price = all_tickers.get_price(coin + self.config.BRIDGE)

            if coin_price is None:
                self.logger.info("Skipping scouting... current coin {} not found".format(coin + self.config.BRIDGE))
                continue

            min_notional = self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol)

            if coin.symbol != current_coin_symbol and coin_price * current_coin_balance < min_notional:
                continue

            have_coin = True

            # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot
            # has stopped. Not logging though to reduce log size.
            self.logger.info(f"Scouting for best trades. Current ticker: {coin + self.config.BRIDGE} ", False)

            self._jump_to_best_coin(coin, coin_price, all_tickers)

        if not have_coin:
            self.bridge_scout()
