from datetime import datetime
from typing import Dict

from sqlalchemy.orm import Session

from .binance_api_manager import BinanceAPIManager
from .config import Config
from .database import Database, LogScout
from .logger import Logger
from .models import Coin, CoinValue, Pair


class AutoTrader:
    def __init__(self, binance_manager: BinanceAPIManager, database: Database, logger: Logger, config: Config):
        self.manager = binance_manager
        self.db = database
        self.logger = logger
        self.config = config

    def initialize(self):
        self.initialize_trade_thresholds()

    def transaction_through_bridge(self, pair: Pair):
        """
        Jump from the source coin to the destination coin through bridge coin
        """

        can_sell = False
        balance = self.manager.get_currency_balance(pair.from_coin.symbol)
        from_coin_price = self.manager.get_ticker_price(pair.from_coin + self.config.BRIDGE)

        if balance and balance * from_coin_price > self.manager.get_min_notional(
            pair.from_coin.symbol, self.config.BRIDGE.symbol
        ):
            can_sell = True
        else:
            self.logger.info("Skipping sell")

        if can_sell and self.manager.sell_alt(pair.from_coin, self.config.BRIDGE) is None:
            self.logger.info("Couldn't sell, going back to scouting mode...")
            return None

        result = self.manager.buy_alt(pair.to_coin, self.config.BRIDGE)
        if result is not None:
            # TODO: Do I need to change this?
            self.db.set_current_coin(pair.to_coin)
            price = result.price
            if abs(price) < 1e-15:
                price = result.cumulative_filled_quantity / result.cumulative_quote_qty

            self.update_trade_threshold(pair.to_coin, price)
            return result

        self.logger.info("Couldn't buy, going back to scouting mode...")
        return None

    def update_trade_threshold(self, coin: Coin, coin_price: float):
        """
        Update all the coins with the threshold of buying the current held coin
        """

        if coin_price is None:
            self.logger.info("Skipping update... current coin {} not found".format(coin + self.config.BRIDGE))
            return

        session: Session
        with self.db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.to_coin == coin):
                from_coin_price = self.manager.get_ticker_price(pair.from_coin + self.config.BRIDGE)

                if from_coin_price is None:
                    self.logger.info(
                        "Skipping update for coin {} not found".format(pair.from_coin + self.config.BRIDGE)
                    )
                    continue

                pair.ratio = from_coin_price / coin_price

    def initialize_trade_thresholds(self):
        """
        Initialize the buying threshold of all the coins for trading between them
        """
        session: Session
        with self.db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.ratio.is_(None)).all():
                if not pair.from_coin.enabled or not pair.to_coin.enabled:
                    continue
                self.logger.info(f"Initializing {pair.from_coin} vs {pair.to_coin}")

                from_coin_price = self.manager.get_ticker_price(pair.from_coin + self.config.BRIDGE)
                if from_coin_price is None:
                    self.logger.info(
                        "Skipping initializing {}, symbol not found".format(pair.from_coin + self.config.BRIDGE)
                    )
                    continue

                to_coin_price = self.manager.get_ticker_price(pair.to_coin + self.config.BRIDGE)
                if to_coin_price is None:
                    self.logger.info(
                        "Skipping initializing {}, symbol not found".format(pair.to_coin + self.config.BRIDGE)
                    )
                    continue

                pair.ratio = from_coin_price / to_coin_price

    def scout(self):
        """
        Scout for potential jumps from the current coin to another coin
        """
        raise NotImplementedError()

    def _get_ratios(self, coin: Coin, coin_price):
        """
        Given a coin, get the current price ratio for every other enabled coin
        """
        ratio_dict: Dict[Pair, float] = {}

        scout_logs = []
        for pair in self.db.get_pairs_from(coin):
            optional_coin_price = self.manager.get_ticker_price(pair.to_coin + self.config.BRIDGE)

            if optional_coin_price is None:
                self.logger.info(
                    "Skipping scouting... optional coin {} not found".format(pair.to_coin + self.config.BRIDGE)
                )
                continue

            scout_logs.append(LogScout(pair, pair.ratio, coin_price, optional_coin_price))

            # Obtain (current coin)/(optional coin)
            coin_opt_coin_ratio = coin_price / optional_coin_price

            transaction_fee = self.manager.get_fee(pair.from_coin, self.config.BRIDGE, True) + self.manager.get_fee(
                pair.to_coin, self.config.BRIDGE, False
            )

            ratio_dict[pair] = (
                coin_opt_coin_ratio - transaction_fee * self.config.SCOUT_MULTIPLIER * coin_opt_coin_ratio
            ) - pair.ratio
        self.db.batch_log_scout(scout_logs)
        return ratio_dict

    def _jump_to_best_coin(self, coin: Coin, coin_price: float, excluded_coins: None ):
        """
        Given a coin, search for a coin to jump to
        """
        ratio_dict = self._get_ratios(coin, coin_price)

        # keep only ratios bigger than zero
        ratio_dict = {k: v for k, v in ratio_dict.items() if v > 0}

        # if we have any viable options, pick the one with the biggest ratio
        if ratio_dict:
            coin_options = sorted(ratio_dict, key=ratio_dict.get, reverse=True)

            for coin_option in coin_options:
                can_trade_this_coin = True
                print(f"--- Coin option to trade: {coin_option}")

                # Do not allow us to trade with another ALT that is excluded
                for excluded_coin in excluded_coins:
                    if excluded_coin.symbol == coin_option.to_coin_id:
                        can_trade_this_coin = False

                if can_trade_this_coin:
                    self.logger.info(f"Will be jumping from {coin} to {coin_option.to_coin_id}")
                    self.transaction_through_bridge(coin_option)
                else:
                    self.logger.info(f"--- Skipping trade for {coin}... new coin {coin_option.to_coin_id} is excluded")

    def _sell_coin_for_profit(self, coin: Coin, coin_price: float):
        latest_coin_trade = self.db.find_latest_coin_trade(coin.symbol)
        last_total_purchased_price = latest_coin_trade.crypto_trade_amount
        total_value_of_coin_now = coin_price * latest_coin_trade.crypto_starting_balance

        current_coin_percentage_increase = ( (100.0 / last_total_purchased_price ) * total_value_of_coin_now ) - 100

        # TODO: Do not hardcode
        if current_coin_percentage_increase > 7.5:
            self.logger.info(f"Profit clause met {coin} - increased {current_coin_percentage_increase}%!")
            if self.manager.sell_alt(coin, self.config.BRIDGE) is None:
                self.logger.info("Couldn't sell, going back to scouting mode...")
                return None

    def bridge_scout(self, excluded_coins: None):
        """
        If we have any bridge coin leftover, buy a coin with it that we won't immediately trade out of
        """
        bridge_balance = self.manager.get_currency_balance(self.config.BRIDGE.symbol)

        for coin in self.db.get_coins():
            current_coin_price = self.manager.get_ticker_price(coin + self.config.BRIDGE)

            can_trade_this_coin = True

            if current_coin_price is None:
                continue

            # Do not allow us to buy an excluded ALT with bridge coin
            for excluded_coin in excluded_coins:
               if excluded_coin.symbol == coin.symbol:
                   can_trade_this_coin = False

            ratio_dict = self._get_ratios(coin, current_coin_price)
            if not any(v > 0 for v in ratio_dict.values()):
                # There will only be one coin where all the ratios are negative. When we find it, buy it if we can
                if bridge_balance > self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol):
                    if can_trade_this_coin:
                        self.logger.info(f"Will be purchasing {coin} using bridge coin")
                        self.manager.buy_alt(coin, self.config.BRIDGE)
                        return coin
                    else:
                        self.logger.info(f"--- Skipping bridge scouting {coin}... optional coin {excluded_coin.symbol} is excluded")

        return None

    def update_values(self):
        """
        Log current value state of all altcoin balances against BTC and USDT in DB.
        """
        now = datetime.now()

        coins = self.db.get_coins(False)
        cv_batch = []
        for coin in coins:
            balance = self.manager.get_currency_balance(coin.symbol)
            if balance == 0:
                continue
            usd_value = self.manager.get_ticker_price(coin + "USDT")
            btc_value = self.manager.get_ticker_price(coin + "BTC")
            cv = CoinValue(coin, balance, usd_value, btc_value, datetime=now)
            cv_batch.append(cv)
        self.db.batch_update_coin_values(cv_batch)
