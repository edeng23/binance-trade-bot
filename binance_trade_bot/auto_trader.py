import random
from datetime import datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from .binance_api_manager import BinanceAPIManager
from .config import Config
from .database import Database
from .logger import Logger
from .models import Pair, Coin, CoinValue
from .utils import get_market_ticker_price_from_list


class AutoTrader:
    def __init__(self, binance_manager: BinanceAPIManager, database: Database, logger: Logger, config: Config):
        self.manager = binance_manager
        self.db = database
        self.logger = logger
        self.config = config

    def transaction_through_bridge(self, pair: Pair, all_tickers):
        '''
        Jump from the source coin to the destination coin through bridge coin
        '''
        if self.manager.sell_alt(pair.from_coin, self.config.BRIDGE, all_tickers) is None:
            self.logger.info("Couldn't sell, going back to scouting mode...")
            return None
        # This isn't pretty, but at the moment we don't have implemented logic to escape from a bridge coin... This'll do for now
        result = None
        while result is None:
            result = self.manager.buy_alt(pair.to_coin, self.config.BRIDGE, all_tickers)

    def transaction_to_coin(self, to_coin: Coin, all_tickers):
        '''
        Jump from BRIDGE coin to the destination coin
        '''
        result = None
        while result is None:
            result = self.manager.buy_alt(to_coin, self.config.BRIDGE, all_tickers)

    def initialize_trade_thresholds(self):
        '''
        Initialize the buying threshold of all the coins for trading between them
        '''
        all_tickers = self.manager.get_all_market_tickers()

        current_coin = self.db.get_current_coin()
        current_coin_balance = self.manager.get_currency_balance(current_coin.symbol)
        current_coin_price = get_market_ticker_price_from_list(all_tickers, current_coin + self.config.BRIDGE)

        previous_sell_trade = self.db.get_previous_sell_trade(current_coin)
        if previous_sell_trade is None:
            possible_bridge_amount = (current_coin_balance * current_coin_price) - ((current_coin_balance * current_coin_price) * self.config.SCOUT_TRANSACTION_FEE * self.config.SCOUT_MULTIPLIER)
            trade_log = self.db.start_trade_log(current_coin, self.config.BRIDGE, True)
            trade_log.set_initialized(current_coin_balance, possible_bridge_amount)

        for pair in self.db.get_pairs_from(current_coin):
            if not pair.to_coin.enabled:
                continue
            print("Initializing {0} vs {1}".format(current_coin, pair.to_coin))

            from_coin_price = get_market_ticker_price_from_list(all_tickers, pair.from_coin + self.config.BRIDGE)
            if from_coin_price is None:
                self.logger.info("Skipping initializing {0}, symbol not found".format(pair.from_coin + self.config.BRIDGE))
                continue

            to_coin_price = get_market_ticker_price_from_list(all_tickers, pair.to_coin + self.config.BRIDGE)
            if to_coin_price is None:
                self.logger.info("Skipping initializing {0}, symbol not found".format(pair.to_coin + self.config.BRIDGE))
                continue

            previous_sell_trade = self.db.get_previous_sell_trade(pair.to_coin)
            if previous_sell_trade is None:
                possible_bridge_amount = (current_coin_balance * current_coin_price) - ((current_coin_balance * current_coin_price) * self.config.SCOUT_TRANSACTION_FEE * self.config.SCOUT_MULTIPLIER)
                possible_to_amount = (possible_bridge_amount / to_coin_price) - ((possible_bridge_amount / to_coin_price) * self.config.SCOUT_TRANSACTION_FEE * self.config.SCOUT_MULTIPLIER)

                trade_log = self.db.start_trade_log(pair.to_coin, self.config.BRIDGE, True)
                trade_log.set_initialized(current_coin_balance, possible_bridge_amount)

    def initialize_current_coin(self):
        '''
        Decide what is the current coin, and set it up in the DB.
        '''
        current_coin_symbol = self.config.CURRENT_COIN_SYMBOL
        if not current_coin_symbol:
            exit("***\nERROR!\nCurrent coin not set in user.cfg\n***")

        if current_coin_symbol not in self.config.SUPPORTED_COIN_LIST:
            exit("***\nERROR!\nCurrent coin not listed in supported coin list defined in user.cfg\n***")

        current_coin_balance = self.manager.get_currency_balance(current_coin_symbol)
        if not current_coin_balance:
            exit("***\nERROR!\nBinance account not holding any balance for current coin set in user.cfg\n***")


    def initialize_step_sizes(self):
        '''
        Initialize the step sizes of all the coins for trading with the bridge coin
        '''
        session: Session
        with self.db.db_session() as session:
            # For all the enabled coins, update the coin tickSize
            for coin in session.query(Coin).filter(Coin.enabled == True).all():
                tick_size = self.db.get_alt_step(coin, self.config.BRIDGE)
                if tick_size is None:
                    self.db.set_alt_step(coin, self.config.BRIDGE, self.manager.get_alt_tick(coin.symbol, self.config.BRIDGE.symbol))

    def scout_loop(self):
        '''
        Outer scout loop, check if we currently have alt or bridge
        '''
        current_coin = self.db.get_current_coin()
        if (current_coin.symbol == self.config.BRIDGE.symbol):
            self.scout_bridge()
        else:
            self.scout_alt()

    def scout_alt(self):
        '''
        Scout for potential jumps from the current coin to another coin
        '''
    
        current_coin = self.db.get_current_coin()
        # Display on the console, the current coin+Bridge, so users can see *some* activity and not thinkg the bot has stopped. Not logging though to reduce log size.
        print(str(
            datetime.now()) + " - CONSOLE - INFO - I am scouting the best trades. Current coin: {0} ".format(
            current_coin + self.config.BRIDGE), end='\r')

        current_coin_balance = self.manager.get_currency_balance(current_coin.symbol)
        all_tickers = self.manager.get_all_market_tickers()
        current_coin_price = get_market_ticker_price_from_list(all_tickers, current_coin + self.config.BRIDGE)

        if current_coin_price is None:
            self.logger.info("Skipping scouting... current coin {0} not found".format(current_coin + self.config.BRIDGE))
            return

        possible_bridge_amount = (current_coin_balance * current_coin_price) - ((current_coin_balance * current_coin_price) * self.config.SCOUT_TRANSACTION_FEE * self.config.SCOUT_MULTIPLIER)

        # Display on the console, the current coin+Bridge,
        # so users can see *some* activity and not thinking the bot has stopped.
        self.logger.log("Scouting. Current coin: {0} price: {1} {2}: {3}"
                    .format(current_coin + self.config.BRIDGE, current_coin_price, self.config.BRIDGE, possible_bridge_amount), "info", False)

        ratio_dict: Dict[Pair, float, ScoutHistory] = {}

        for pair in self.db.get_pairs_from(current_coin):
            if not pair.to_coin.enabled:
                continue
            optional_coin_price = get_market_ticker_price_from_list(all_tickers, pair.to_coin + self.config.BRIDGE)

            if optional_coin_price is None:
                self.logger.info("Skipping scouting... optional coin {0} not found".format(pair.to_coin + self.config.BRIDGE))
                continue

            # Obtain (current coin)/(optional coin)
            coin_opt_coin_ratio = current_coin_price / optional_coin_price

            # Skipping... if possible target amount is lower than expected target amount.
            possible_target_amount = (possible_bridge_amount / optional_coin_price) - ((possible_bridge_amount / optional_coin_price) * self.config.SCOUT_TRANSACTION_FEE * self.config.SCOUT_MULTIPLIER)

            skip_ratio = False
            previous_sell_trade = self.db.get_previous_sell_trade(pair.to_coin)

            if previous_sell_trade is not None:
                expected_target_amount = previous_sell_trade.alt_trade_amount
                delta_percentage = (possible_target_amount - expected_target_amount) / expected_target_amount * 100
                if expected_target_amount > possible_target_amount:
                    skip_ratio = True
                    self.logger.info("{0: >10} \t\t expected {1: >20f} \t\t actual {2: >20f} \t\t diff {3: >20f}%"
                                .format(pair.from_coin_id + pair.to_coin_id,
                                        expected_target_amount, possible_target_amount, delta_percentage))
                else:
                    self.logger.info("{0: >10} \t\t !!!!!!!! {1: >20f} \t\t actual {2: >20f} \t\t diff {3: >20f}%"
                                .format(pair.from_coin_id + pair.to_coin_id,
                                        expected_target_amount, possible_target_amount, delta_percentage))

                if not skip_ratio:
                # save ratio so we can pick the best option, not necessarily the first
                    ls = self.db.log_scout(pair, current_coin_price, optional_coin_price)
                    ratio_dict[pair] = []
                    ratio_dict[pair].append(delta_percentage)
                    ratio_dict[pair].append(ls)

        # keep only ratios bigger than zero
        ratio_dict = {k: v for k, v in ratio_dict.items() if v[0] > 0}

        # if we have any viable options, pick the one with the biggest ratio
        if ratio_dict:
            best_pair = max(ratio_dict.items(), key=lambda x : x[1][0])
            self.logger.info('Will be jumping from {0} to {1}'.format(
                current_coin, best_pair[0].to_coin_id))
            self.set_scout_executed(best_pair[1][1])
            self.transaction_through_bridge(
                best_pair[0], all_tickers)

    def scout_bridge(self):
        '''
        Scout for potential jumps from the bridge coin to another coin
        '''

        bridge_balance = self.manager.get_currency_balance(self.config.BRIDGE+'')
        all_tickers = self.manager.get_all_market_tickers()
        # current_coin_price = get_market_ticker_price_from_list(all_tickers, current_coin + BRIDGE)

        # if current_coin_price is None:
        #     logger.info("Skipping scouting... current coin {0} not found".format(current_coin + BRIDGE))
        #     return

        possible_bridge_amount = bridge_balance

        # Display on the console, the current coin+Bridge,
        # so users can see *some* activity and not thinking the bot has stopped.
        self.logger.log("Scouting. Current coin: {0}: {1}"
                    .format(self.config.BRIDGE, possible_bridge_amount), "info", False)

        ratio_dict: Dict[Coin, float, ScoutHistory] = {}

        session: Session
        with self.db.db_session() as session:
            # For all the enabled coins, update the coin tickSize
            for coin in session.query(Coin).filter(Coin.enabled == True).all():
                optional_coin_price = get_market_ticker_price_from_list(all_tickers, coin + self.config.BRIDGE)

                if optional_coin_price is None:
                    logger.info("Skipping scouting... optional coin {0} not found".format(coin + self.config.BRIDGE))
                    continue

                # Skipping... if possible target amount is lower than expected target amount.
                possible_target_amount = (possible_bridge_amount / optional_coin_price) - ((possible_bridge_amount / optional_coin_price) * self.config.SCOUT_TRANSACTION_FEE * self.config.SCOUT_MULTIPLIER)

                skip_ratio = False
                previous_sell_trade = self.db.get_previous_sell_trade(coin)
                if previous_sell_trade is not None:
                    expected_target_amount = previous_sell_trade.alt_trade_amount
                    delta_percentage = (possible_target_amount - expected_target_amount) / expected_target_amount * 100
                    if expected_target_amount > possible_target_amount:
                        skip_ratio = True
                        self.logger.info("{0: >10} \t\t expected {1: >20f} \t\t actual {2: >20f} \t\t diff {3: >20f}%"
                                    .format(self.config.BRIDGE + coin,
                                            expected_target_amount, possible_target_amount, delta_percentage))
                    else:
                        self.logger.info("{0: >10} \t\t !!!!!!!! {1: >20f} \t\t actual {2: >20f} \t\t diff {3: >20f}%"
                                    .format(self.config.BRIDGE + coin,
                                            expected_target_amount, possible_target_amount, delta_percentage))


                    if not skip_ratio:
                        # save ratio so we can pick the best option, not necessarily the first
    #                    ls = log_scout(pair, current_coin_price, optional_coin_price)
                        ratio_dict[coin] = []
                        ratio_dict[coin].append(delta_percentage)
#                        ratio_dict[coin].append(ls)


            # if we have any viable options, pick the one with the biggest expected target amount
            if ratio_dict:
                best_coin = max(ratio_dict.items(), key=lambda x : x[1][0])
                self.logger.info('Will be jumping from {0} to {1}'.format(
                    self.config.BRIDGE, best_coin[0]))
    #            set_scout_executed(best_pair[1][1])
                self.transaction_to_coin(
                    best_coin[0], all_tickers)

    def update_values(self):
        '''
        Log current value state of all altcoin balances against BTC and USDT in DB.
        '''
        all_ticker_values = self.manager.get_all_market_tickers()

        now = datetime.now()

        session: Session
        with self.db.db_session() as session:
            coins: List[Coin] = session.query(Coin).all()
            for coin in coins:
                balance = self.manager.get_currency_balance(coin.symbol)
                if balance == 0:
                    continue
                usd_value = get_market_ticker_price_from_list(all_ticker_values, coin + "USDT")
                btc_value = get_market_ticker_price_from_list(all_ticker_values, coin + "BTC")
                cv = CoinValue(coin, balance, usd_value, btc_value, datetime=now)
                session.add(cv)
                self.db.send_update(cv)
