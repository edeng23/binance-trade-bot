import os
import time
from configparser import NoOptionError
from contextlib import contextmanager
from unittest.mock import patch, mock_open

import pytest

from binance_trade_bot.config import Config, USER_CFG_SECTION
from binance_trade_bot.models import Coin
from tests.test_data.user_config import DEFAULT_USER_CONFIG, API_KEY, SECRET_KEY, BRIDGE_SYMBOL, BINANCE_TLD


class TestConfig:

    @contextmanager
    def create_user_config_file(self, content=''):
        file_path = "user.cfg"
        with open(file_path, 'w') as f:
            f.write(content)
        try:
            yield file_path
            os.remove(file_path)
        except Exception:
            pass
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    def test_config_open(self):
        with pytest.raises(NoOptionError):
            with patch('builtins.open', new=mock_open(read_data="")) as user_config_mock:
                Config()
                user_config_mock.assert_called_once_with('user.cfg', 'r')

    def test_config_read(self):
        with self.create_user_config_file(DEFAULT_USER_CONFIG):
            trade_bot_config = Config()
            assert trade_bot_config.BINANCE_API_KEY == API_KEY
            assert trade_bot_config.BINANCE_API_SECRET_KEY == SECRET_KEY
            assert trade_bot_config.BINANCE_TLD == BINANCE_TLD
            assert trade_bot_config.BRIDGE.symbol == BRIDGE_SYMBOL
            assert trade_bot_config.CURRENT_COIN_SYMBOL == ""
            assert type(trade_bot_config.SUPPORTED_COIN_LIST) == list
            assert len(trade_bot_config.SUPPORTED_COIN_LIST) > 0
            assert trade_bot_config.SCOUT_MULTIPLIER == 5
            assert trade_bot_config.SCOUT_SLEEP_TIME == 5.0
            assert trade_bot_config.SCOUT_HISTORY_PRUNE_TIME == 1.0
