from logging import Logger

from sqlalchemy.orm import Session

import config
import database as db
from binance_api_manager import BinanceApiManager
from models import Pair
from utils import get_market_ticker_price_from_list


class AutoTrader:
    def __init__(self, binance_manager: BinanceApiManager, logger: Logger):
        self.logger = logger
        self.binance_manager = binance_manager

    def transaction_through_tether(self, pair: Pair):
        """
        Jump from the source coin to the destination coin through tether
        """
        result = self.binance_manager.sell_alt(pair.from_coin, config.BRIDGE)
        if result is None:
            self.logger.info("Selling failed, cancelling transaction")
        result = self.binance_manager.buy_alt(pair.to_coin, config.BRIDGE)
        if result is None:
            self.logger.info("Buying failed, cancelling transaction")

        db.set_current_coin(pair.to_coin)
        self.update_trade_threshold()

    def update_trade_threshold(self):
        """
        Update all the coins with the threshold of buying the current held coin
        """

        all_tickers = self.binance_manager.get_all_market_tickers()

        current_coin = db.get_current_coin()

        current_coin_price = get_market_ticker_price_from_list(
            all_tickers, current_coin + config.BRIDGE
        )

        if current_coin_price is None:
            self.logger.info(
                f"Skipping update... current coin {current_coin + config.BRIDGE} not found"
            )
            return

        session: Session
        with db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.to_coin == current_coin):
                from_coin_price = get_market_ticker_price_from_list(
                    all_tickers, pair.from_coin + config.BRIDGE
                )

                if from_coin_price is None:
                    self.logger.info(
                        f"Skipping update for coin {pair.from_coin + config.BRIDGE} not found"
                    )
                    continue

                pair.ratio = from_coin_price / current_coin_price

    def initialize_trade_thresholds(self):
        """
        Initialize the buying threshold of all the coins for trading between them
        """

        all_tickers = self.binance_manager.get_all_market_tickers()

        session: Session
        with db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.ratio == None).all():
                if not pair.from_coin.enabled or not pair.to_coin.enabled:
                    continue
                self.logger.info(f"Initializing {pair.from_coin} vs {pair.to_coin}")

                from_coin_price = get_market_ticker_price_from_list(
                    all_tickers, pair.from_coin + config.BRIDGE
                )
                if from_coin_price is None:
                    self.logger.info(
                        f"Skipping initializing {pair.from_coin + config.BRIDGE}, symbol not found"
                    )
                    continue

                to_coin_price = get_market_ticker_price_from_list(
                    all_tickers, pair.to_coin + config.BRIDGE
                )
                if to_coin_price is None:
                    self.logger.info(
                        f"Skipping initializing {pair.to_coin + config.BRIDGE}, symbol not found"
                    )
                    continue

                pair.ratio = from_coin_price / to_coin_price

    def scout(self, transaction_fee=0.001, multiplier=5):
        """
        Scout for potential jumps from the current coin to another coin
        """

        all_tickers = self.binance_manager.get_all_market_tickers()

        current_coin = db.get_current_coin()

        current_coin_price = get_market_ticker_price_from_list(
            all_tickers, current_coin + config.BRIDGE
        )

        if current_coin_price is None:
            self.logger.info(
                f"Skipping scouting... current coin {current_coin + config.BRIDGE} not found"
            )
            return

        for pair in db.get_pairs_from(current_coin):
            if not pair.to_coin.enabled:
                continue
            optional_coin_price = get_market_ticker_price_from_list(
                all_tickers, pair.to_coin + config.BRIDGE
            )

            if optional_coin_price is None:
                self.logger.info(
                    f"Skipping scouting... optional coin {pair.to_coin + config.BRIDGE} not found"
                )
                continue

            db.log_scout(pair, pair.ratio, current_coin_price, optional_coin_price)

            # Obtain (current coin)/(optional coin)
            coin_opt_coin_ratio = current_coin_price / optional_coin_price

            if (
                coin_opt_coin_ratio - transaction_fee * multiplier * coin_opt_coin_ratio
            ) > pair.ratio:
                self.logger.info(
                    f"Will be jumping from {current_coin} to {pair.to_coin}"
                )
                self.transaction_through_tether(pair)
                break
