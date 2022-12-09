from collections import defaultdict, deque
from colorama import Fore, Style
import math
import random
import sys
import talib
import numpy
import decimal
import statistics as st
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.expression import and_

from binance_trade_bot.auto_trader import AutoTrader
from binance_trade_bot.database import Pair, Coin, CoinValue


class Strategy(AutoTrader):
    def initialize(self):
      
        super().initialize()
        self.initialize_current_coin()
        self.rsi_coin = ""
        self.d = 3
        self.v = 3
        self.jumps = int(self.config.JUMPS_PER_DAY)
        self.win = int(self.config.TARGET_WIN)
        self.active_threshold = 0
        self.dir_threshold = 0
        self.Res_high = 0
        self.Res_mid = 0
        self.Res_low = 0
        self.Res_float = 0
        self.tema = 1
        self.rv_tema = 1
        self.vector = []
        self.volume = []
        self.volume_sma = []
        self.from_coin_price = 0
        self.to_coin_price = 0
        self.from_coin_direction = 0
        self.to_coin_direction = 0
        self.reverse_price_history = [0]
        self.rsi_price_history = [0]
        self.panicked = self.check_panic()
        self.pre_rsi = 0
        self.rv_pre_rsi = 0
        self.rv_rsi = 0
        self.best_pair = ""
        self.rsi = self.rsi_calc()
        self.reinit_threshold = self.manager.now().replace(second=0, microsecond=0)
        self.reinit_rsi = self.manager.now().replace(second=0, microsecond=0)
        self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
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
        
        if self.panicked:
            self.from_coin_price = self.manager.get_buy_price(current_coin + self.config.BRIDGE)

        else:
            self.from_coin_price = self.manager.get_sell_price(current_coin + self.config.BRIDGE)
        
        if self.from_coin_price is None:
            self.logger.info("Skipping scouting... current coin {} not found".format(current_coin + self.config.BRIDGE))
            return
        
        if base_time >= allowed_idle_time:
            print("")
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
            f"{self.manager.now().strftime('%Y-%m-%d %H:%M:%S')} - " ,
            f"{Fore.CYAN}Long{Style.RESET_ALL} " if not self.panicked else f"{Fore.CYAN}Short{Style.RESET_ALL} ",
            f"Threshold: {Fore.CYAN}{round(self.from_coin_direction - self.dir_threshold, 3)}%{Style.RESET_ALL} " if self.dir_threshold != 0 else f"",
            f"Bottom: {Fore.CYAN}{round(self.active_threshold, self.d)}{Style.RESET_ALL} " if not self.panicked else f"Top: {Fore.CYAN}{round(self.active_threshold, self.d)}{Style.RESET_ALL} ",
            f"Current coin: {Fore.CYAN}{current_coin}{Style.RESET_ALL} with RSI: {Fore.CYAN}{round(self.rv_rsi, 1)}{Style.RESET_ALL} price direction: {Fore.CYAN}{round(self.from_coin_direction, 1)}%{Style.RESET_ALL} ",
            f"rel. Volume: {Fore.CYAN}{round(self.volume[-1]/self.volume_sma, 2)}{Style.RESET_ALL} ",
            f"L: {Fore.MAGENTA}{round(self.Res_low, self.d)}{Style.RESET_ALL} M: {Fore.MAGENTA}{round(self.Res_mid, self.d)}{Style.RESET_ALL} H: {Fore.MAGENTA}{round(self.Res_high, self.d)}{Style.RESET_ALL} C: {Fore.MAGENTA}{round(self.Res_float, self.d)}{Style.RESET_ALL} ",
            f"Next coin: {Fore.YELLOW}{self.rsi_coin}{Style.RESET_ALL} with RSI: {Fore.YELLOW}{round(self.rsi, 1)}{Style.RESET_ALL} price direction: {Fore.YELLOW}{round(self.to_coin_direction, 1)}%{Style.RESET_ALL} " if self.rsi else f"",
            end='\r',
        )
	
        
            
        if self.rsi:
            if self.panicked:
                if self.to_coin_direction >= 0 and (self.rsi > self.pre_rsi <= 30 or self.pre_rsi < self.rsi > 50) or self.rsi < 20:
                    print("")
                    self.logger.info(f"Will be jumping from {self.rsi_coin} to {self.best_pair.to_coin_id}")
                    self.panicked = False
                    self.transaction_through_bridge(self.best_pair, round(max(self.from_coin_price, self.rv_tema), self.d), round(min(self.to_coin_price, self.tema), self.v))
                    self.active_threshold = 0
                    self.dir_threshold = 0
                    self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=1)

            else:
                if self.from_coin_direction <= self.to_coin_direction >= 0 and (self.pre_rsi < self.rsi <= 30 or 50 <= self.pre_rsi < self.rsi) or self.rsi < 20:
                    print("")
                    self.panicked = False
                    self.transaction_through_bridge(self.best_pair, round(max(self.from_coin_price, self.rv_tema, self.active_threshold), self.d), round(min(self.to_coin_price, self.tema), self.v))
                    self.active_threshold = 0
                    self.dir_threshold = 0
                    self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
                                
        if base_time >= self.panic_time and not self.panicked:
            balance = self.manager.get_currency_balance(panic_pair.from_coin.symbol)
            balance_in_bridge = max(balance * self.from_coin_price, 1) * 2
            m = min((1+self.win/balance_in_bridge)**(1/self.jumps)+0.001, 2**(1/self.jumps)+0.001)
            n = min(len(self.reverse_price_history), int(self.config.RSI_LENGTH))
            stdev = st.stdev(numpy.array(self.reverse_price_history[-n:]))
            self.dir_threshold = stdev / self.rv_tema * -50

            if self.from_coin_price > self.Res_high > self.active_threshold:
                self.active_threshold = self.Res_high * m

            if self.from_coin_price > self.Res_mid > self.active_threshold:
                self.active_threshold = self.Res_mid * m

            if self.from_coin_price > self.Res_low > self.active_threshold:
                self.active_threshold = self.Res_low * m

            self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(seconds=1)
            
            if self.rv_pre_rsi > self.rv_rsi and (self.from_coin_direction < 0 and self.from_coin_price < self.active_threshold or self.volume[-1] / self.volume_sma >= 1.5) or self.from_coin_direction < self.dir_threshold or self.rv_rsi > 80 or max(self.vector[:-2]) <= self.vector[-1]:
                if self.rsi:
                    print("")
                    self.logger.info(f"{self.rsi_coin} exhausted, jumping to {self.best_pair.to_coin_id}")
                    self.panicked = False
                    self.transaction_through_bridge(self.best_pair, round(max(self.from_coin_price, self.rv_tema), self.d), round(min(self.to_coin_price, self.tema), self.v))
                    self.active_threshold = 0
                    self.dir_threshold = 0
                    self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
                
                elif self.rv_rsi > 80 or max(self.vector[:-2]) <= self.vector[-1]:
                    print("")
                    self.logger.info("!!! Target sell !!!")
                
                elif (self.from_coin_direction < self.dir_threshold and self.rv_rsi < 50) or (self.volume[-1] / self.volume_sma >= 1.5 and self.vector[-1] < 0):
                    print("")
                    self.logger.info("!!! Panic sell !!!")
                    self.active_threshold = self.rv_tema
                    self.from_coin_price = round(self.rv_tema, self.d)
                
                else:
                    print("")
                    self.logger.info("!!! Selling high !!!")
                    self.from_coin_price = round(max(self.rv_tema, self.active_threshold), self.d)
                
                if not self.rsi:
                    self.panicked = True
                    can_sell = False
                    if balance and balance * self.from_coin_price > self.manager.get_min_notional(panic_pair.from_coin.symbol, self.config.BRIDGE.symbol):
                        can_sell = True

                    if not can_sell:
                        self.logger.info("Not enough balance, changing to panic mode...")

                    elif self.manager.sell_alt(panic_pair.from_coin, self.config.BRIDGE, self.from_coin_price) is None:
                        self.logger.info("Couldn't sell, going back to scouting mode...")
                        self.panicked = False
                        self.active_threshold = 0

                    else:
                        self.active_threshold = max(self.reverse_price_history) * 3
                        self.dir_threshold = 0
                        self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(minutes=int(self.config.RSI_CANDLE_TYPE))
                
		
        elif base_time >= self.panic_time and self.panicked:
            balance = self.manager.get_currency_balance(self.config.BRIDGE.symbol) * 2
            m = max(2 - (1+self.win/balance)**(1/self.jumps)-0.001, 2 - 2**(1/self.jumps)-0.001)
            n = min(len(self.reverse_price_history), int(self.config.RSI_LENGTH))
            stdev = st.stdev(numpy.array(self.reverse_price_history[-n:]))#, timeperiod=self.config.RSI_LENGTH, nbdev=1)
            self.dir_threshold = stdev / self.rv_tema * 50

            if self.from_coin_price < self.Res_low < self.active_threshold:
                self.active_threshold = self.Res_low * m

            if self.from_coin_price < self.Res_mid < self.active_threshold:
                self.active_threshold = self.Res_mid * m

            if self.from_coin_price < self.Res_high < self.active_threshold:
                self.active_threshold = self.Res_high * m

            self.panic_time = self.manager.now().replace(second=0, microsecond=0) + timedelta(seconds=1)
            
            if 30 > self.rv_pre_rsi < self.rv_rsi and (self.from_coin_direction > 0 and self.from_coin_price > self.active_threshold or self.volume[-1] / self.volume_sma >= 1.5) or self.from_coin_direction > self.dir_threshold or self.rv_rsi < 20 or min(self.vector[:-2]) >= self.vector[-1]:
                if self.rv_rsi < 20 or min(self.vector[:-2]) >= self.vector[-1]:
                    print("")
                    self.logger.info("!!! Target buy !!!")
                
                elif (self.from_coin_direction > self.dir_threshold and self.rv_rsi > 50) or (self.volume[-1] / self.volume_sma >= 1.5 and self.vector[-1] > 0):
                    print("")
                    self.logger.info("!!! FOMO buy !!!")
                    self.active_threshold = self.rv_tema
                    self.from_coin_price = round(self.rv_tema, self.d)
                
                else:
                    print("")
                    self.logger.info("!!! Buying low !!!")
                    self.from_coin_price = round(min(self.rv_tema, self.active_threshold), self.d)
                        
                self.panicked = False

                if self.manager.buy_alt(panic_pair.from_coin, self.config.BRIDGE, self.from_coin_price) is None:
                    self.logger.info("Couldn't buy, going back to panic mode...")
                    self.panicked = True
                    self.active_threshold = max(self.reverse_price_history) * 3

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

    
    def rsi_calc(self):
        """
        Calculate the RSI for the next best coin.
        """
		
        init_rsi_length = int(self.config.RSI_LENGTH)
        rsi_type = self.config.RSI_CANDLE_TYPE
        rsi_string = str(self.config.RSI_CANDLE_TYPE) + 'm'
                        
        #Binance api allows retrieving max 1000 candles
        if init_rsi_length > 20:
            init_rsi_length = 20

        init_rsi_delta = (init_rsi_length * 50 ) * rsi_type
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
        
        self.d = abs(decimal.Decimal(str(self.reverse_price_history[-1])).as_tuple().exponent)
        self.v = abs(decimal.Decimal(str(self.rsi_price_history[-1])).as_tuple().exponent)
        
        for i in range(1, len(self.reverse_price_history)-1):
            di = abs(decimal.Decimal(str(self.reverse_price_history[i])).as_tuple().exponent)
            if di > self.d:
                self.d = di
                
        for k in range(1, len(self.rsi_price_history)-1):
            vi = abs(decimal.Decimal(str(self.rsi_price_history[i])).as_tuple().exponent)
            if vi > self.v:
                self.v = vi
        

        if ratio_dict:	
            self.best_pair = max(ratio_dict, key=ratio_dict.get)
            to_coin_symbol = self.best_pair.to_coin_id
            check_prices = []
        
            for checks in self.manager.binance_client.get_historical_klines(f"{to_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, rsi_start_date_str, rsi_check_str, limit=1000):                           
                check_price = float(checks[4])
                check_prices.append(check_price)
                
                
            if self.db.get_coin(to_coin_symbol) == self.rsi_coin and self.rsi_price_history[0] == check_prices[0]:
                self.to_coin_price = self.manager.get_buy_price(self.rsi_coin + self.config.BRIDGE)
                self.rsi_price_history[-1] = self.to_coin_price
            else:     
                self.rsi_coin = self.db.get_coin(to_coin_symbol)
                self.rsi_price_history = []

                for result in self.manager.binance_client.get_historical_klines(f"{to_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, rsi_start_date_str, rsi_end_date_str, limit=1000):                           
                    rsi_price = float(result[4])
                    self.rsi_price_history.append(rsi_price)
                        
                self.to_coin_price = self.manager.get_buy_price(self.rsi_coin + self.config.BRIDGE)
                self.rsi_price_history.append(self.to_coin_price)

           

            if len(self.rsi_price_history) >= init_rsi_length:
                np_closes = numpy.array(self.rsi_price_history)
                rsi = talib.RSI(np_closes, init_rsi_length)
                tema = talib.TEMA(np_closes, init_rsi_length)

                self.rsi = rsi[-1]
                self.pre_rsi = rsi[-2]
                self.tema = tema[-1]
                self.to_coin_direction = self.to_coin_price / self.tema * 100 - 100

        else:
            self.rsi = 0
            self.pre_rsi = 0 
            self.tema = 1
            self.to_coin_price = 0
            self.best_pair = ""
            self.to_coin_direction = 0

        ExpPer = 2 * init_rsi_length - 1
        K = 2 / (ExpPer + 1)
        AUC = 1
        ADC = 1
        rev_prices = []

        for reverse in self.manager.binance_client.get_historical_klines(f"{current_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, rsi_start_date_str, rsi_check_str, limit=1):                           
            rev_price = float(reverse[4])
            rev_prices.append(rev_price)
                
        if not self.reverse_price_history[0] == rev_prices[0]:  
            self.reverse_price_history = []
            for result in self.manager.binance_client.get_historical_klines(f"{current_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, rsi_start_date_str, rsi_end_date_str, limit=init_rsi_length*5):                           
                rsi_price = float(result[4])
                volume = float(result[5])
                vector = (rsi_price - float(result[1])) * volume
                self.reverse_price_history.append(rsi_price)
                self.volume.append(volume)
                self.vector.append(vector)
		
                
        else:
            
            for result in self.manager.binance_client.get_historical_klines(f"{current_coin_symbol}{self.config.BRIDGE_SYMBOL}", rsi_string, limit=1):
                close = float(result[4])
                volume = float(result[5])
                vector = (close - float(result[1])) * volume
                self.volume[-1] = volume
                self.reverse_price_history[-1] = close
                self.vector[-1] = vector
        
        if len(self.reverse_price_history) >= init_rsi_length:
            rv_closes = numpy.array(self.reverse_price_history)
            rv_rsi = talib.RSI(rv_closes, init_rsi_length)
            rv_tema = talib.TEMA(rv_closes, init_rsi_length)
        
            volume = numpy.array(self.volume)
            volume_sma = talib.SMA(volume, init_rsi_length)

            self.rv_rsi = rv_rsi[-1]
            self.rv_pre_rsi = rv_rsi[-2]
            self.rv_tema = rv_tema[-1]
            self.from_coin_direction = self.from_coin_price / self.rv_tema * 100 - 100
                
            self.volume_sma = volume_sma[-1]

        prev_close = self.reverse_price_history[0]
        for close in self.reverse_price_history[1:]:                           
            if close > prev_close:
                AUC = K * (close - prev_close) + (1 - K) * AUC
                ADC = (1 - K) * ADC
                        
            else:
                AUC = (1 - K) * AUC
                ADC = K * (prev_close - close) + (1 - K) * ADC
            prev_close = close
       
        Val_high = (init_rsi_length - 1) * (ADC * 70/30 - AUC)
        Val_mid = (init_rsi_length - 1) * (ADC - AUC)
        Val_low = (init_rsi_length - 1) * (ADC * 30/70 - AUC)
        Val_float = (init_rsi_length - 1) * (ADC * self.rv_rsi / (100 - self.rv_rsi) - AUC)
        
        if Val_high >= 0:
            self.Res_high = self.reverse_price_history[-1] + Val_high
        else:
            self.Res_high = self.reverse_price_history[-1] + (Val_high * 30/70)
                           
        self.Res_mid = self.reverse_price_history[-1] + Val_mid
                           
        if Val_low >= 0:
            self.Res_low = self.reverse_price_history[-1] + Val_low
        else:
            self.Res_low = self.reverse_price_history[-1] + (Val_low * 70/30)

        if Val_float >= 0:
            self.Res_float = self.reverse_price_history[-1] + Val_float
        else:
            self.Res_float = self.reverse_price_history[-1] + (Val_float * (100/self.rv_rsi - 1))
        
    def check_panic(self):
        bridge = self.config.BRIDGE.symbol.upper()
        accepted_bridge = {'USDT', 'BUSD', 'USD', 'AUD', 'BIDR', 'BRL', 'EUR', 'GBP', 'RUB', 'TRY', 'DAI', 'UAH', 'ZAR', 'VAI', 'IDRT', 'NGN', 'PLN', 'BNB', 'BTC', 'ETH', 'XRP', 'TRX', 'DOGE', 'DOT'}
        if self.manager.get_currency_balance(bridge) >= 10 and bridge in accepted_bridge:
            self.logger.info("Running in panic mode")
            return True
        else:
            return False
                
                
