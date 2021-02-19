from sqlalchemy import Column, String, ForeignKey, Float
from sqlalchemy.orm import relationship

from .coin import Coin
from .base import Base


class Pair(Base):
    __tablename__ = "pairs"

    from_coin_id = Column(String, ForeignKey('coins.symbol'), primary_key=True)
    from_coin = relationship("Coin", foreign_keys=[from_coin_id])

    to_coin_id = Column(String, ForeignKey('coins.symbol'), primary_key=True)
    to_coin = relationship("Coin", foreign_keys=[to_coin_id])

    ratio = Column(Float)

    def __init__(self, from_coin: Coin, to_coin: Coin, ratio=None):
        self.from_coin = from_coin
        self.to_coin = to_coin
        self.ratio = ratio
