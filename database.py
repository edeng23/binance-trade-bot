from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Union, Optional

from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker, scoped_session, Session

from models import *

engine = create_engine("sqlite:///data/crypto_trading.db")

SessionMaker = sessionmaker(bind=engine)
SessionMaker()


@contextmanager
def db_session():
    """
    Creates a context with an open SQLAlchemy session.
    """
    session: Session = scoped_session(SessionMaker)
    yield session
    session.commit()
    session.close()


def set_coins(symbols: List[str]):
    session: Session

    # Add coins to the database and set them as enabled or not
    with db_session() as session:
        # For all the coins in the database, if the symbol no longer appears
        # in the config file, set the coin as disabled
        coins: List[Coin] = session.query(Coin).all()
        for coin in coins:
            if coin.symbol not in symbols:
                coin.enabled = False

        # For all the symbols in the config file, add them to the database
        # if they don't exist
        for symbol in symbols:
            coin = next((coin for coin in coins if coin.symbol == symbol), None)
            if coin is None:
                session.add(Coin(symbol))
            else:
                coin.enabled = True

    # For all the combinations of coins in the database, add a pair to the database
    with db_session() as session:
        coins: List[Coin] = session.query(Coin).all()
        for from_coin in coins:
            for to_coin in coins:
                if from_coin != to_coin:
                    pair = session.query(Pair).filter(
                        and_(Pair.from_coin == from_coin, Pair.to_coin == to_coin)).first()
                    if pair is None:
                        session.add(Pair(from_coin, to_coin))


def get_coin(coin: Union[Coin, str]) -> Coin:
    if type(coin) == Coin:
        return coin
    session: Session
    with db_session() as session:
        coin = session.query(Coin).get(coin)
        session.expunge(coin)
        return coin


def set_current_coin(coin: Union[Coin, str]):
    coin = get_coin(coin)
    session: Session
    with db_session() as session:
        if type(coin) == Coin:
            coin = session.merge(coin)
        session.add(CurrentCoin(coin))


def get_current_coin() -> Optional[Coin]:
    session: Session
    with db_session() as session:
        current_coin = session.query(CurrentCoin).order_by(CurrentCoin.datetime.desc()).first()
        if current_coin is None:
            return None
        coin = current_coin.coin
        session.expunge(coin)
        return coin


def get_pair(from_coin: Union[Coin, str], to_coin: Union[Coin, str]):
    from_coin = get_coin(from_coin)
    to_coin = get_coin(to_coin)
    session: Session
    with db_session() as session:
        pair: Pair = session.query(Pair).filter(
            and_(Pair.from_coin == from_coin, Pair.to_coin == to_coin)).first()
        session.expunge(pair)
        return pair


def get_pairs_from(from_coin: Union[Coin, str]):
    from_coin = get_coin(from_coin)
    session: Session
    with db_session() as session:
        pairs: List[pair] = session.query(Pair).filter(Pair.from_coin == from_coin)
        return pairs


def log_scout(pair: Pair, target_ratio: float, current_coin_price: float, other_coin_price: float):
    session: Session
    with db_session() as session:
        pair = session.merge(pair)
        sh = ScoutHistory(pair, target_ratio, current_coin_price, other_coin_price)
        session.add(sh)


def prune_scout_history(hours: float):
    time_diff = datetime.now() - timedelta(hours=hours)
    session: Session
    with db_session() as session:
        session.query(ScoutHistory).filter(ScoutHistory.datetime < time_diff).delete()


class TradeLog:
    def __init__(self, from_coin: Coin, to_coin: Coin, selling: bool):
        session: Session
        with db_session() as session:
            from_coin = session.merge(from_coin)
            to_coin = session.merge(to_coin)
            self.trade = Trade(from_coin, to_coin, selling)
            session.add(self.trade)

    def set_ordered(self, alt_starting_balance, crypto_starting_balance, alt_trade_amount):
        session: Session
        with db_session() as session:
            trade: Trade = session.merge(self.trade)
            trade.alt_starting_balance = alt_starting_balance
            trade.alt_trade_amount = alt_trade_amount
            trade.crypto_starting_balance = crypto_starting_balance
            trade.state = TradeState.ORDERED

    def set_complete(self, crypto_trade_amount):
        session: Session
        with db_session() as session:
            trade: Trade = session.merge(self.trade)
            trade.crypto_trade_amount = crypto_trade_amount
            trade.state = TradeState.COMPLETE


def create_database():
    Base.metadata.create_all(engine)


if __name__ == '__main__':
    create_database()
