from collections import defaultdict, deque
import math
import random
import sys
import talib
import numpy
import statistics as st
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.expression import and_

from binance_trade_bot.auto_trader import AutoTrader
from binance_trade_bot.database import Pair, Coin, CoinValue


class Strategy(AutoTrader):
    def initialize(self):
	
        if self.config.ACCEPT_LOSSES != True:
            self.logger.error("You need to accept losses by setting accept_losses=true in the user.cfg or setting the enviroment variable ACCEPT_LOSSES to true in order to use this strategy!")
            raise Exception()

        super().initialize()
        self.initialize_current_coin()
        self.rsi_coin = ""
        self.auto_weight = int(self.config.RATIO_ADJUST_WEIGHT)
        self.active_threshold = 0
        self.dir_threshold = 0
        self.Res_70 = 0
        self.Res_50 = 0
        self.Res_30 = 0
        self.tema = 0
        self.rv_tema = 0
        self.slope = 0
        self.rv_slope = 0
        self.from_coin_price = 0
        self.to_coin_price = 0
        self.from_coin_direction = 0
        self.to_coin_direction = 0
        self.reverse_price_history = [0]
        self.rsi_price_history = [0]
        self.panicked = False
        self.jumpable_coins = 0
        self.pre_rsi = 0
        self.rv_pre_rsi = 0
        self.rv_rsi = 0
        self.rsi = self.rsi_calc()
        self.reinit_threshold = self.manager.now().replace(second=0, microsecond=0)
        self.reinit_rsi = self.manager.now().replace(second=0, microsecond=0)
        self.reinit_idle = self.manager.now().replace(second=0, microsecond=0) + timedelta(hours=int(self.config.MAX_IDLE_HOURS))
        self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=int(self.config.RSI_CANDLE_TYPE))
        self.logger.info(f"Ratio adjust weight: {self.config.RATIO_ADJUST_WEIGHT}")
        self.logger.info(f"RSI length: {self.config.RSI_LENGTH}")
        self.logger.info(f"RSI candle type: {self.config.RSI_CANDLE_TYPE}")
    
    def scout(self):
        #check if previous buy order failed. If so, bridge scout for a new coin.
        if self.failed_buy_order:
            self.bridge_scout()
        
        current_coin = self.db.get_current_coin()
        ratio_dict, prices = self._get_ratios(current_coin, self.from_coin_price)
        panic_pair = max(ratio_dict, key=ratio_dict.get)
        
        base_time: datetime = self.manager.now()
        allowed_idle_time = self.reinit_threshold
        allowed_rsi_time = self.reinit_rsi
        allowed_rsi_idle_time = self.reinit_idle
        
        if not self.panicked:
            self.from_coin_price = self.manager.get_buy_price(current_coin + self.config.BRIDGE)

        else:
            self.from_coin_price = self.manager.get_sell_price(current_coin + self.config.BRIDGE)

        if self.from_coin_price is None:
            self.logger.info("Skipping scouting... current coin {} not found".format(current_coin + self.config.BRIDGE))
            return
        
        if base_time >= allowed_idle_time:
            print("")
            self.auto_weight = max(1, self.auto_weight + self.jumpable_coins - 1)
            self.re_initialize_trade_thresholds()
            self.reinit_threshold = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
		
        if base_time >= allowed_rsi_time:
            self.rsi_calc()
            self.reinit_rsi = self.manager.now().replace(second=0, microsecond=0) + timedelta(seconds=1)
		
        """
        Scout for potential jumps from the current coin to another coin
        """
        # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot has
        # stopped. Not logging though to reduce log size.
        print(
            f"{self.manager.now().replace(microsecond=0)} - " ,
            f"Threshold: {round(self.from_coin_direction - self.dir_threshold, 3)}% " if self.dir_threshold != 0 else "",
            f"Bottom: {round(self.active_threshold, 3)} {self.config.BRIDGE} ",
            f"Long position " if not self.panicked else "Short position ",
            f"Current ratio weight: {self.auto_weight} ",
            f"Current coin: {current_coin + self.config.BRIDGE} with RSI: {round(self.rv_rsi, 3)} price direction: {round(self.from_coin_direction, 3)}% ",
            f"bullish " if self.rv_slope >= 0 else "bearish ",
            f"Next coin: {self.rsi_coin} with RSI: {round(self.rsi, 3)} price direction: {round(self.to_coin_direction, 3)}% " if self.rsi else "",
            f"bullish " if self.slope >= 0 and self.rsi else "",
            f"bearish " if self.slope < 0 and self.rsi else "",
            end='\r',
        )
	
        
            
        if self.rsi:
           if self.panicked:
                if self.to_coin_direction >= 0 and (self.rsi > self.pre_rsi <= 30 or self.pre_rsi < self.rsi > 50) or self.rsi < 20:
                        print("")
                        self.auto_weight = int(self.config.RATIO_ADJUST_WEIGHT)
                        self.panicked = False
                        self._jump_to_best_coin(current_coin, self.from_coin_price)
                        self.active_threshold = 0
                        self.dir_threshold = 0
                        self.reinit_idle = self.manager.now().replace(second=0, microsecond=0) + timedelta(hours=int(self.config.MAX_IDLE_HOURS))
                        self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=int(self.config.RSI_CANDLE_TYPE))

           else:
                if self.from_coin_direction <= self.to_coin_direction >= 0 and (self.pre_rsi < self.rsi <= 30 or self.pre_rsi < self.rsi > 50) or self.rsi < 20:
                        print("")
                        self.auto_weight = int(self.config.RATIO_ADJUST_WEIGHT)
                        self.panicked = False
                        self._jump_to_best_coin(current_coin, self.from_coin_price)
                        self.active_threshold = 0
                        self.dir_threshold = 0
                        self.reinit_idle = self.manager.now().replace(second=0, microsecond=0) + timedelta(hours=int(self.config.MAX_IDLE_HOURS))
                        self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=int(self.config.RSI_CANDLE_TYPE))
                        
                 
        if base_time >= self.panic_time and not self.panicked:
            balance = self.manager.get_currency_balance(panic_pair.from_coin.symbol)
            dev = talib.STDDEV(numpy.array(self.reverse_price_history), timeperiod=self.config.RSI_LENGTH, nbdev=1)
            stdev = dev[-1]
            stdev = stdev / self.rv_tema * 100
            self.dir_threshold = (stdev ** 3 / 100 + stdev) * -1

            if self.from_coin_price > self.Res_70 > self.active_threshold:
                self.active_threshold = self.Res_70

            elif self.from_coin_price > self.Res_50 > self.active_threshold:
                self.active_threshold = self.Res_50

            elif self.from_coin_price > self.Res_30 > self.active_threshold:
                self.active_threshold = self.Res_30

            self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(seconds=1)
            
            if self.rv_pre_rsi > self.rv_rsi and self.from_coin_price < self.active_threshold or self.from_coin_direction < self.dir_threshold or self.rv_rsi > 80:
                if self.rv_rsi > 80:
                    print("")
                    self.logger.infor("!!! Target sell !!!")
                
                elif self.from_coin_direction < self.dir_threshold:
                    print("")
                    self.logger.info("!!! Panic sell !!!")
                
                else:
                    print("")
                    self.logger.info("!!! Selling high !!!")

                self.panicked = True
                can_sell = False
                
                if balance and balance * self.from_coin_price > self.manager.get_min_notional(panic_pair.from_coin.symbol, self.config.BRIDGE.symbol):
                    can_sell = True

                if not can_sell:
                    self.logger.info("Not enough balance, changing to panic mode...")

                elif self.manager.sell_alt(panic_pair.from_coin, self.config.BRIDGE, self.from_coin_price) is None:
                    self.logger.info("Couldn't sell, going back to scouting mode...")
                    self.panicked = False

                else:
                    self.active_threshold = max(self.reverse_price_history) * 3
                    self.dir_threshold = 0
                    self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=int(self.config.RSI_CANDLE_TYPE))
                
		
        elif base_time >= self.panic_time and self.panicked:
            balance = self.manager.get_currency_balance(self.config.BRIDGE.symbol)
            dev = talib.STDDEV(numpy.array(self.reverse_price_history), timeperiod=self.config.RSI_LENGTH, nbdev=1)
            stdev = dev[-1]
            stdev = stdev / self.rv_tema * 100
            self.dir_threshold = stdev ** 3 / 100 + stdev

            if self.from_coin_price < self.Res_30 < self.active_threshold:
                self.active_threshold = self.Res_30

            elif self.from_coin_price < self.Res_50 < self.active_threshold:
                self.active_threshold = self.Res_50

            elif self.from_coin_price < self.Res_70 < self.active_threshold:
                self.active_threshold = self.Res_70

            self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(seconds=1)
            
            if self.rv_pre_rsi < self.rv_rsi and self.from_coin_price > self.active_threshold or self.from_coin_direction > self.dir_threshold or self.rv_rsi < 20:
                if self.rv_rsi < 20:
                    print("")
                    self.logger.infor("!!! Target buy !!!")
                
                elif self.from_coin_direction > self.dir_threshold:
                    print("")
                    self.logger.info("!!! FOMO sell !!!")
                
                else:
                    print("")
                    self.logger.info("!!! Buying low !!!")
                        
                self.panicked = False

                if self.manager.buy_alt(panic_pair.from_coin, self.config.BRIDGE, self.from_coin_price) is None:
                    self.logger.info("Couldn't buy, going back to panic mode...")
                    self.panicked = True

                else:
                    self.active_threshold = 0
                    self.dir_threshold = 0
                    self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=int(self.config.RSI_CANDLE_TYPE))
                    

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

                pair.ratio = (pair.ratio *self.auto_weight + from_coin_price / to_coin_price)  / (self.auto_weight + 1)
		
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
        if init_rsi_length > 200:
            init_rsi_length = 200

        init_rsi_delta = (init_rsi_length * 5 ) * rsi_type
			
        #self.logger.info(f"Using last {init_rsi_length} candles to initialize RSI")

        rsi_base_date = self.manager.now().replace(second=0, microsecond=0)
        rsi_start_date = rsi_base_date - timedelta(minutes=init_rsi_delta)
        rsi_end_date = rsi_base_date
        rsi_check_date = rsi_start_date + timedelta(minutes=self.config.RSI_CANDLE_TYPE*2)

        rsi_start_date_str = rsi_start_date.strftime('%Y-%m-%d %H:%M')
        rsi_end_date_str = rsi_end_date.strftime('%Y-%m-%d %H:%M')
        rsi_check_str = rsi_check_date.strftime('%Y-%m-%d %H:%M')
					 
        current_coin = self.db.get_current_coin()
        current_coin_symbol = current_coin.symbol
        current_coin_price = self.manager.get_sell_price(current_coin + self.config.BRIDGE)
		
        ratio_dict, prices = self._get_ratios(current_coin, current_coin_price)
        ratio_dict = {k: v for k, v in ratio_dict.items() if v > 0}
        
        self.jumpable_coins = len(ratio_dict)
	
        if ratio_dict:	
            best_pair = max(ratio_dict, key=ratio_dict.get)
            to_coin_symbol = best_pair.to_coin_id
            check_prices = []
        
            for checks in self.manager.binance_client.get_historical_klines(f"{to_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, rsi_start_date_str, rsi_check_str, limit=init_rsi_length*5):                           
                check_price = float(checks[1])
                check_prices.append(check_price)
                
                
            if self.db.get_coin(to_coin_symbol) == self.rsi_coin and self.rsi_price_history[0] == check_prices[0]:
                self.to_coin_price = self.manager.get_buy_price(self.rsi_coin + self.config.BRIDGE)
                self.rsi_price_history[-1] = self.to_coin_price
            else:     
                self.rsi_coin = self.db.get_coin(to_coin_symbol)
                self.rsi_price_history = []

                for result in self.manager.binance_client.get_historical_klines(f"{to_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, rsi_start_date_str, rsi_end_date_str, limit=init_rsi_length*5):                           
                    rsi_price = float(result[1])
                    self.rsi_price_history.append(rsi_price)
                        
                self.to_coin_price = self.manager.get_buy_price(self.rsi_coin + self.config.BRIDGE)
                self.rsi_price_history.append(self.to_coin_price)

           

            if len(self.rsi_price_history) >= init_rsi_length:
                np_closes = numpy.array(self.rsi_price_history)
                rsi = talib.RSI(np_closes, init_rsi_length)
                tema = talib.TEMA(np_closes, init_rsi_length)
                short_slope = talib.LINEARREG_SLOPE(np_closes, min(init_rsi_length, len(self.rsi_price_history)))
                long_slope = talib.LINEARREG_SLOPE(np_closes, len(self.rsi_price_history))

                self.slope = (short_slope[-1] + long_slope[-1]) / 2
                self.rsi = rsi[-1]
                self.pre_rsi = rsi[-2]
                self.tema = tema[-1]
                self.to_coin_direction = self.to_coin_price / self.tema * 100 - 100
                #self.logger.info(f"Finished ratio init...")

        else:
            self.rsi = 0
            self.pre_rsi = 0 
            self.tema = 0
            self.to_coin_price = 0
            #self.rsi_coin = ""
            self.to_coin_direction = 0
            #self.logger.info(f"Not enough data for RSI calculation. Continue scouting...")

        ExpPer = 2 * init_rsi_length - 1
        K = 2 / (ExpPer + 1)
        AUC = 1
        ADC = 1
        rev_prices = []

        for reverse in self.manager.binance_client.get_historical_klines(f"{current_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, rsi_start_date_str, rsi_check_str, limit=init_rsi_length*5):                           
            rev_price = float(reverse[1])
            rev_prices.append(rev_price)
                
        if not self.reverse_price_history[0] == rev_prices[0]:  
            self.reverse_price_history = [1]        
            for result in self.manager.binance_client.get_historical_klines(f"{current_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, rsi_start_date_str, rsi_end_date_str, limit=init_rsi_length*5):                           
                rsi_price = float(result[1])
                self.reverse_price_history.append(rsi_price)
                
                if self.reverse_price_history[-1] > self.reverse_price_history[-2]:
                    AUC = K * (self.reverse_price_history[-1] - self.reverse_price_history[-2]) + (1 - K) * AUC
                    ADC = (1 -K) * ADC
                else:
                    AUC = (1 - K) * AUC
                    ADC = K * (self.reverse_price_history[-2] - self.reverse_price_history[-1]) + (1 - K) * ADC
        
            del self.reverse_price_history[0]
                
        else:
            self.reverse_price_history[-1] = self.from_coin_price
            prev_close = 1
            for close in self.reverse_price_history:                           
                if close > prev_close:
                    AUC = K * (self.reverse_price_history[-1] - self.reverse_price_history[-2]) + (1 - K) * AUC
                    ADC = (1 -K) * ADC
                    prev_close = close
                else:
                    AUC = (1 - K) * AUC
                    ADC = K * (self.reverse_price_history[-2] - self.reverse_price_history[-1]) + (1 - K) * ADC
                    prev_close = close
                        
            del self.reverse_price_history[0]
        
        Val_70 = (init_rsi_length - 1) * (ADC * 70 / 30 - AUC)
        Val_50 = (init_rsi_length - 1) * (ADC - AUC)
        Val_30 = (init_rsi_length - 1) * (ADC * 30 / 70 - AUC)
        
        if Val_70 >= 0:
            self.Res_70 = self.reverse_price_history[-1] + Val_70
        else:
            self.Res_70 = self.reverse_price_history[-1] + Val_70 * 30 / 70
                           
        self.Res_50 = self.reverse_price_history[-1] + Val_50
                           
        if Val_30 >= 0:
            self.Res_30 = self.reverse_price_history[-1] + Val_30
        else:
            self.Res_30 = self.reverse_price_history[-1] + Val_30 * 70 / 30

        # if self.reverse_price_history[0] == rev_prices[0]:    
        #     self.from_coin_price = self.manager.get_buy_price(current_coin + self.config.BRIDGE)  
        #     self.reverse_price_history[-1] = self.from_coin_price
        
        # else:
        #     self.reverse_price_history = []

        #     for result in self.manager.binance_client.get_historical_klines(f"{current_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, rsi_start_date_str, rsi_end_date_str, limit=init_rsi_length*5):                           
        #         rv_price = float(result[1])
        #         self.reverse_price_history.append(rv_price)

        #     self.from_coin_price = self.manager.get_buy_price(current_coin + self.config.BRIDGE)

        if len(self.reverse_price_history) >= init_rsi_length:
            rv_closes = numpy.array(self.reverse_price_history)
            rv_rsi = talib.RSI(rv_closes, init_rsi_length)
            rv_tema = talib.TEMA(rv_closes, init_rsi_length)
            rv_short_slope = talib.LINEARREG_SLOPE(rv_closes, min(init_rsi_length, len(self.reverse_price_history)))
            rv_long_slope = talib.LINEARREG_SLOPE(rv_closes, len(self.reverse_price_history))

            self.rv_slope = (rv_short_slope[-1] + rv_long_slope[-1]) / 2
            self.rv_rsi = rv_rsi[-1]
            self.rv_pre_rsi = rv_rsi[-2]
            self.rv_tema = rv_tema[-1]
            self.from_coin_direction = self.from_coin_price / self.rv_tema * 100 - 100
            #self.logger.info(f"Finished ratio init...")

