import os
from contextlib import contextmanager

from binance_trade_bot.config import CFG_FL_NAME


@contextmanager
def create_temporary_user_config_file(content=""):
    with open(CFG_FL_NAME, "w") as f:
        f.write(content)

    try:
        yield CFG_FL_NAME
    finally:
        if os.path.exists(CFG_FL_NAME):
            os.remove(CFG_FL_NAME)
