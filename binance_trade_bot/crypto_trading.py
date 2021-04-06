#!python3
import time

from .auto_trader import AutoTrader
from .binance_api_manager import BinanceAPIManager
from .config import Config
from .database import Database
from .logger import Logger
from .scheduler import SafeScheduler


def main():
    logger = Logger()
    logger.info('Starting')

    config = Config()
    db = Database(logger, config)
    manager = BinanceAPIManager(config, db, logger)
    trader = AutoTrader(manager, db, logger, config)

    logger.info("Creating database schema if it doesn't already exist")
    db.create_database()

    db.set_coins(config.SUPPORTED_COIN_LIST)
    db.migrate_old_state()

    trader.initialize_trade_thresholds()
    trader.initialize_current_coin()
    
    schedule = SafeScheduler(logger)
    schedule.every(config.SCOUT_SLEEP_TIME).seconds.do(trader.scout).tag("scouting")
    schedule.every(1).minutes.do(trader.update_values).tag("updating value history")
    schedule.every(1).minutes.do(db.prune_scout_history).tag("pruning scout history")
    schedule.every(1).hours.do(db.prune_value_history).tag("pruning value history")

    while True:
        schedule.run_pending()
        time.sleep(1)
