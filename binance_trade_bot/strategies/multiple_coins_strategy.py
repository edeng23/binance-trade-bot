from binance_trade_bot.auto_trader import AutoTrader


class Strategy(AutoTrader):
    def scout(self):
        """
        Scout for potential jumps from the current coin to another coin
        """
        all_tickers = self.manager.get_all_market_tickers()

        for coin in self.db.get_coins():
            current_coin_balance = self.manager.get_currency_balance(coin.symbol)
            coin_price = all_tickers.get_price(coin + self.config.BRIDGE)

            if coin_price is None:
                self.logger.info("Skipping scouting... current coin {} not found".format(coin + self.config.BRIDGE))
                continue

            if coin_price * current_coin_balance < self.manager.get_min_notional(
                coin.symbol, self.config.BRIDGE.symbol
            ):
                continue

            # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot
            # has stopped. Not logging though to reduce log size.
            self.logger.info(f"Scouting for best trades. Current ticker: {coin + self.config.BRIDGE} ", False)

            self._jump_to_best_coin(coin, coin_price, all_tickers)

        self.bridge_scout()
