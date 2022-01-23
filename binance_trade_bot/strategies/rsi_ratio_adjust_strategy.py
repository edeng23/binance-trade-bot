from collections import defaultdict
import random
import sys
import talib
import numpy
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.expression import and_

from binance_trade_bot.auto_trader import AutoTrader
from binance_trade_bot.database import Pair, Coin, CoinValue


class Strategy(AutoTrader):
    def initialize(self):
        #self.logger.info(f"CAUTION: The ratio_adjust strategy is still work in progress and can lead to losses! Use this strategy only if you know what you are doing, did alot of backtests and can live with possible losses.")

        if self.config.ACCEPT_LOSSES != True:
            self.logger.error("You need accept losses by setting accept_losses=true in the user.cfg or setting the enviroment variable ACCEPT_LOSSES to true in order to use this strategy!")
            raise Exception()

        super().initialize()
        self.initialize_current_coin()
        self.rsi_coin = ""
        self.rsi = self.rsi_calc()
        self.reinit_threshold = self.manager.now().replace(second=0, microsecond=0)
        self.reinit_rsi = self.manager.now().replace(second=0, microsecond=0)
        self.logger.info(f"Ratio adjust weight: {self.config.RATIO_ADJUST_WEIGHT}")
        self.logger.info(f"RSI length: {self.config.RSI_LENGTH}")
        self.logger.info(f"RSI candle type: {self.config.RSI_CANDLE_TYPE}")
    
    def scout(self):
        #check if previous buy order failed. If so, bridge scout for a new coin.
        if self.failed_buy_order:
            self.bridge_scout()
        
        base_time: datetime = self.manager.now()
        allowed_idle_time = self.reinit_threshold
        allowed_rsi_time = self.reinit_rsi
        if base_time >= allowed_idle_time:
            self.re_initialize_trade_thresholds()
            self.reinit_threshold = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
		
        if base_time >= allowed_rsi_time:
            self.rsi_calc()
            self.reinit_rsi = self.manager.now().replace(second=0, microsecond=0) + timedelta(seconds=1)
		
        """
        Scout for potential jumps from the current coin to another coin
        """
        current_coin = self.db.get_current_coin()
        # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot has
        # stopped. Not logging though to reduce log size.
        print(
            f"{self.manager.now()} - CONSOLE - INFO - I am scouting the best trades. ",
            f"Current coin: {current_coin + self.config.BRIDGE} ",
            f"Next best coin is: {self.rsi_coin} with RSI: {self.rsi} ",
            end='\r',
        )
        self.rsi_coin = ""
	
        current_coin_price = self.manager.get_sell_price(current_coin + self.config.BRIDGE)

        if current_coin_price is None:
            self.logger.info("Skipping scouting... current coin {} not found".format(current_coin + self.config.BRIDGE))
            return
            
        if self.rsi:
           if self.rsi > 50 or self.rsi <= 30:
              self._jump_to_best_coin(current_coin, current_coin_price)
	

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
                self.manager.buy_alt(
                    current_coin, self.config.BRIDGE, self.manager.get_buy_price(current_coin + self.config.BRIDGE)
                )
                self.logger.info("Ready to start trading")
            else:
                current_balance = self.manager.get_currency_balance(current_coin_symbol)
                sell_price = self.manager.get_sell_price(current_coin_symbol + self.config.BRIDGE.symbol)
                if current_balance is not None and current_balance * sell_price < self.manager.get_min_notional(current_coin_symbol, self.config.BRIDGE.symbol):
                    self.logger.info(f"Purchasing {current_coin_symbol} to begin trading")
                    current_coin = self.db.get_current_coin()
                    self.manager.buy_alt(
                        current_coin, self.config.BRIDGE, self.manager.get_buy_price(current_coin + self.config.BRIDGE)
                    )
                    self.logger.info("Ready to start trading")

    def re_initialize_trade_thresholds(self):
        """
        Re-initialize all the thresholds ( hard reset - as deleting db )
        """
        #updates all ratios
        #print('************INITIALIZING RATIOS**********')
        session: Session
        with self.db.db_session() as session:
            c1 = aliased(Coin)
            c2 = aliased(Coin)
            for pair in session.query(Pair).all():
                if not pair.from_coin.enabled or not pair.to_coin.enabled:
                    continue
                #self.logger.debug(f"Initializing {pair.from_coin} vs {pair.to_coin}", False)

                from_coin_price = self.manager.get_sell_price(pair.from_coin + self.config.BRIDGE)
                if from_coin_price is None:
                    # self.logger.debug(
                    #     "Skipping initializing {}, symbol not found".format(pair.from_coin + self.config.BRIDGE),
                    #     False
                    # )
                    continue

                to_coin_price = self.manager.get_buy_price(pair.to_coin + self.config.BRIDGE)
                if to_coin_price is None:
                    # self.logger.debug(
                    #     "Skipping initializing {}, symbol not found".format(pair.to_coin + self.config.BRIDGE),
                    #     False
                    # )
                    continue

                pair.ratio = (pair.ratio *self.config.RATIO_ADJUST_WEIGHT + from_coin_price / to_coin_price)  / (self.config.RATIO_ADJUST_WEIGHT + 1)
		
    def initialize_trade_thresholds(self):
        """
        Initialize the buying threshold of all the coins for trading between them
        """
        session: Session
        with self.db.db_session() as session:
            pairs = session.query(Pair).filter(Pair.ratio.is_(None)).all()
            grouped_pairs = defaultdict(list)
            for pair in pairs:
                if pair.from_coin.enabled and pair.to_coin.enabled:
                    grouped_pairs[pair.from_coin.symbol].append(pair)

            price_history = {}

            init_weight = self.config.RATIO_ADJUST_WEIGHT
            
            #Binance api allows retrieving max 1000 candles
            if init_weight > 500:
                init_weight = 500

            self.logger.info(f"Using last {init_weight} candles to initialize ratios")

            base_date = self.manager.now().replace(second=0, microsecond=0)
            start_date = base_date - timedelta(minutes=init_weight*2)
            end_date = base_date - timedelta(minutes=1)

            start_date_str = start_date.strftime('%Y-%m-%d %H:%M')
            end_date_str = end_date.strftime('%Y-%m-%d %H:%M')

            self.logger.info(f"Starting ratio init: Start Date: {start_date}, End Date {end_date}")
            for from_coin_symbol, group in grouped_pairs.items():

                if from_coin_symbol not in price_history.keys():
                    price_history[from_coin_symbol] = []
                    for result in  self.manager.binance_client.get_historical_klines(f"{from_coin_symbol}{self.config.BRIDGE_SYMBOL}", "1m", start_date_str, end_date_str, limit=init_weight*2):
                        price = float(result[1])
                        price_history[from_coin_symbol].append(price)

                for pair in group:                  
                    to_coin_symbol = pair.to_coin.symbol
                    if to_coin_symbol not in price_history.keys():
                        price_history[to_coin_symbol] = []
                        for result in self.manager.binance_client.get_historical_klines(f"{to_coin_symbol}{self.config.BRIDGE_SYMBOL}", "1m", start_date_str, end_date_str, limit=init_weight*2):                           
                           price = float(result[1])
                           price_history[to_coin_symbol].append(price)

                    if len(price_history[from_coin_symbol]) != init_weight*2:
                        self.logger.info(len(price_history[from_coin_symbol]))
                        self.logger.info(f"Skip initialization. Could not fetch last {init_weight * 2} prices for {from_coin_symbol}")
                        continue
                    if len(price_history[to_coin_symbol]) != init_weight*2:
                        self.logger.info(f"Skip initialization. Could not fetch last {init_weight * 2} prices for {to_coin_symbol}")
                        continue
                    
                    sma_ratio = 0.0
                    for i in range(init_weight):
                        sma_ratio += price_history[from_coin_symbol][i] / price_history[to_coin_symbol][i]
                    sma_ratio = sma_ratio / init_weight

                    cumulative_ratio = sma_ratio
                    for i in range(init_weight, init_weight * 2):
                        cumulative_ratio = (cumulative_ratio * init_weight + price_history[from_coin_symbol][i] / price_history[to_coin_symbol][i]) / (init_weight + 1)

                    pair.ratio = cumulative_ratio

            self.logger.info(f"Finished ratio init...")

	
    def rsi_calc(self):
        """
        Calculate the RSI for the next best coin.
        """
		
        init_rsi_length = self.config.RSI_LENGTH
        rsi_type = self.config.RSI_CANDLE_TYPE
        rsi_string = str(self.config.RSI_CANDLE_TYPE) + 'm'
                        
        #Binance api allows retrieving max 1000 candles
        if init_rsi_length > 250:
           init_rsi_length = 250

        init_rsi_delta = (init_rsi_length * 4 ) * rsi_type
			
        #self.logger.info(f"Using last {init_rsi_length} candles to initialize RSI")

        rsi_base_date = self.manager.now().replace(second=0, microsecond=0)
        rsi_start_date = rsi_base_date - timedelta(minutes=init_rsi_delta)
        rsi_end_date = rsi_base_date - timedelta(minutes=1)

        rsi_start_date_str = rsi_start_date.strftime('%Y-%m-%d %H:%M')
        rsi_end_date_str = rsi_end_date.strftime('%Y-%m-%d %H:%M')
					 
        current_coin = self.db.get_current_coin()
        current_coin_price = self.manager.get_buy_price(current_coin + self.config.BRIDGE)
		
        ratio_dict, prices = self._get_ratios(current_coin, current_coin_price)
        ratio_dict = {k: v for k, v in ratio_dict.items() if v > 0}
	
        if ratio_dict:	
           best_pair = max(ratio_dict, key=ratio_dict.get)
           to_coin_symbol = best_pair.to_coin_id
           self.rsi_coin = self.db.get_coin(to_coin_symbol)
		
           rsi_price_history = []

        #self.logger.info(f"Starting RSI init: Start Date: {rsi_start_date}, End Date {rsi_end_date}")

           for result in self.manager.binance_client.get_historical_klines(f"{to_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, rsi_start_date_str, rsi_end_date_str, limit=init_rsi_length):                           
              rsi_price = float(result[1])
              rsi_price_history.append(rsi_price)

           next_coin_price = self.manager.get_buy_price(self.rsi_coin + self.config.BRIDGE)
           rsi_price_history.append(next_coin_price)

           if len(rsi_price_history) >= init_rsi_length:
              np_closes = numpy.array(rsi_price_history)
              rsi = talib.RSI(np_closes, init_rsi_length)
              self.rsi = rsi[-1]
              #self.logger.info(f"Finished ratio init...")

        else:
           self.rsi = ""
           #self.logger.info(f"Not enough data for RSI calculation. Continue scouting...")
