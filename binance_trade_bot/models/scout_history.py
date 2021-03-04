from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship

from .base import Base
from .pair import Pair


class ScoutHistory(Base):
    __tablename__ = "scout_history"

    id = Column(Integer, primary_key=True)
    
    pair_id = Column(String, ForeignKey('pairs.id'))
    pair = relationship("Pair")

    current_coin_price = Column(Float)
    other_coin_price = Column(Float)

    datetime = Column(DateTime)

    executed = Column(Boolean)

    def __init__(self, pair: Pair, current_coin_price: float, other_coin_price: float, executed=False):
        self.pair = pair
        self.current_coin_price = current_coin_price
        self.other_coin_price = other_coin_price
        self.datetime = datetime.utcnow()
        self.executed = executed

    def info(self):
        return {
                "from_coin": self.pair.from_coin.info(),
                "to_coin": self.pair.to_coin.info(),
                "current_coin_price": self.current_coin_price,
                "other_coin_price": self.other_coin_price,
                "datetime": self.datetime.isoformat(),
            }
