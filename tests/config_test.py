import os
from configparser import NoOptionError
from unittest.mock import mock_open, patch

import pytest

from binance_trade_bot.config import CFG_FL_NAME, Config
from tests.test_data.user_config import API_KEY, BINANCE_TLD, BRIDGE_SYMBOL, DEFAULT_USER_CONFIG, SECRET_KEY
from tests.utils import create_temporary_user_config_file


class TestConfig:
    @staticmethod
    def test_config_open():
        with pytest.raises(NoOptionError):
            with patch("builtins.open", new=mock_open(read_data="")) as user_config_mock:
                Config()
                user_config_mock.assert_called_once_with(CFG_FL_NAME, "r")

    @staticmethod
    def test_config_read_from_file():
        with create_temporary_user_config_file(DEFAULT_USER_CONFIG):
            trade_bot_config = Config()
            assert trade_bot_config.BINANCE_API_KEY == API_KEY
            assert trade_bot_config.BINANCE_API_SECRET_KEY == SECRET_KEY
            assert trade_bot_config.BINANCE_TLD == BINANCE_TLD
            assert trade_bot_config.BRIDGE.symbol == BRIDGE_SYMBOL
            assert trade_bot_config.CURRENT_COIN_SYMBOL == ""
            assert isinstance(trade_bot_config.SUPPORTED_COIN_LIST, list)
            assert len(trade_bot_config.SUPPORTED_COIN_LIST) > 0
            assert trade_bot_config.SCOUT_MULTIPLIER == 5
            assert trade_bot_config.SCOUT_SLEEP_TIME == 5.0
            assert trade_bot_config.SCOUT_HISTORY_PRUNE_TIME == 1.0

    @staticmethod
    def test_config_read_from_env_vars():
        with patch.dict(
            os.environ,
            {
                "API_KEY": API_KEY,
                "API_SECRET_KEY": SECRET_KEY,
                "CURRENT_COIN_SYMBOL": BRIDGE_SYMBOL,
                "TLD": BINANCE_TLD,
                "BRIDGE": BRIDGE_SYMBOL,
                "SUPPORTED_COIN_LIST": "ADA LINK",
                "SCOUT_MULTIPLIER": "3",
                "SCOUT_SLEEP_TIME": "4",
                "HOURS_TO_KEEP_SCOUTING_HISTORY": "2",
            },
            clear=True,
        ):
            trade_bot_config = Config()
            assert trade_bot_config.BINANCE_API_KEY == API_KEY
            assert trade_bot_config.BINANCE_API_SECRET_KEY == SECRET_KEY
            assert trade_bot_config.BINANCE_TLD == BINANCE_TLD
            assert trade_bot_config.BRIDGE.symbol == BRIDGE_SYMBOL
            assert trade_bot_config.CURRENT_COIN_SYMBOL == BRIDGE_SYMBOL
            assert len(trade_bot_config.SUPPORTED_COIN_LIST) == 2
            assert trade_bot_config.SUPPORTED_COIN_LIST == ["ADA", "LINK"]
            assert trade_bot_config.SCOUT_MULTIPLIER == 3
            assert trade_bot_config.SCOUT_SLEEP_TIME == 4
            assert trade_bot_config.SCOUT_HISTORY_PRUNE_TIME == 2
