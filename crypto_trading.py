#!python3
import time

from auto_trader import AutoTrader
from binance_api_manager import BinanceAPIManager
from config import Config
from database import Database
from logger import Logger
from scheduler import SafeScheduler


def get_current_ratios(client: BinanceAPIManager):
    all_tickers = client.get_all_market_tickers()

    current_coin = get_current_coin()

    current_coin_price = get_market_ticker_price_from_list(all_tickers, current_coin + BRIDGE)

    if current_coin_price is None:
        logger.info("Skipping scouting... current coin {0} not found".format(current_coin + BRIDGE))
        return

    heartbeat_msg = ""

    for pair in get_pairs_from(current_coin):
        if not pair.to_coin.enabled:
            continue
        optional_coin_price = get_market_ticker_price_from_list(all_tickers, pair.to_coin + BRIDGE)

        if optional_coin_price is None:
            logger.info("Skipping scouting... optional coin {0} not found".format(pair.to_coin + BRIDGE))
            continue

        # Obtain (current coin)/(optional coin)
        coin_opt_coin_ratio = current_coin_price / optional_coin_price

        current_value = (
            coin_opt_coin_ratio
            - SCOUT_TRANSACTION_FEE
            * SCOUT_MULTIPLIER
            * coin_opt_coin_ratio
        )
        difference = (current_value - pair.ratio) / pair.ratio * 100

        heartbeat_msg += f"{current_coin.symbol:<5} to {pair.to_coin.symbol:<5}. Diff: {round(difference, 2):>6.2f}%\n"

    return heartbeat_msg

def get_heartbeat_message(client: BinanceAPIManager):
    # Format variables for the message
    current_coin = get_current_coin().symbol
    heartbeat_data = {
        "current_coin": current_coin,
        "balance": client.get_currency_balance(current_coin),
        "ratios": get_current_ratios(client=client)
    }

    logger.info(HEARTBEAT_MESSAGE.format(**heartbeat_data))

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
    if HEARTBEAT_DURATION > 0:
        schedule.every(HEARTBEAT_DURATION).seconds.do(get_heartbeat_message, client=client).tag("heartbeat")

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
