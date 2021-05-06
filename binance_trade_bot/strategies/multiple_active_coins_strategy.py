from datetime import datetime

from binance_trade_bot.auto_trader import AutoTrader


class Strategy(AutoTrader):
    """
    Scout for potential jumps from the current coin to another coin
    """
    def scout(self):
        # Fetches price of all coins from Binance API
        all_tickers = self.manager.get_all_market_tickers()

        # Fetches all enabled coins from coins table and LOOPS through each
        for coin in self.db.get_coins():
            # Fetches balance of this coin from Binance API
            current_coin_balance = self.manager.get_currency_balance(coin.symbol)

            # Gets the price of this coin from previously fetched price list via Binance API
            coin_price = all_tickers.get_price(coin + self.config.BRIDGE)

            # This is just in case you have a coin in your DB that doesn't exist on Binance
            if coin_price is None:
                self.logger.info("Skipping scouting... current coin {} not found".format(coin + self.config.BRIDGE))
                continue

            # Find out the minimal amount of this coin you can sell back to USDT
            min_notional = self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol)

            # Only continue if this coin has a balance that can be traded
            # For most coins continue will be hit, skipping the rest of this block
            # For coins you own that can be traded, the ticker will be active and jump_to_best_coin will be attempted
            if coin_price * current_coin_balance < min_notional:
                continue

            # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot
            # has stopped. Not logging though to reduce log size.
            self.logger.info(f"Scouting for best trades. Current ticker: {coin + self.config.BRIDGE} ", False)

            self._jump_to_best_coin(coin, coin_price, all_tickers)

        active_coins_count = len(self.db.get_active_coins())
        if active_coins_count < int(self.config.DESIRED_ACTIVE_COIN_COUNT):
            self.bridge_scout()
