import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship

from .base import Base
from .coin import Coin


class CoinValue(Base):
    __tablename__ = "coin_value"

    id = Column(Integer, primary_key=True)

    coin_id = Column(String, ForeignKey('coins.symbol'))
    coin = relationship("Coin")

    balance = Column(Float)
    usd_price = Column(Float)
    btc_price = Column(Float)

    datetime = Column(DateTime, default=datetime.datetime.utcnow)

    def __init__(self, coin: Coin, balance: float, usd_price: float, btc_price: float):
        self.coin = coin
        self.balance = balance
        self.usd_price = usd_price
        self.btc_price = btc_price

    @hybrid_property
    def usd_value(self):
        if self.usd_price is None:
            return None
        return self.balance * self.usd_price

    @usd_value.expression
    def usd_value(cls):
        return cls.balance * cls.usd_price

    @hybrid_property
    def btc_value(self):
        if self.btc_price is None:
            return None
        return self.balance * self.btc_price

    @btc_value.expression
    def btc_value(cls):
        return cls.balance * cls.btc_price
