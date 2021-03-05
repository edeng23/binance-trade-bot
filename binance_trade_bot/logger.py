import logging
import logging.handlers

from .notifications import NotificationHandler

LOG_PATH = "logs/crypto_trading.log"


class Logger:

    Logger = None
    NotificationHandler = None

    def __init__(self):
        # Logger setup
        self.Logger = logging.getLogger("crypto_trader_logger")
        self.Logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        fh = logging.FileHandler(LOG_PATH)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.Logger.addHandler(fh)

        # logging to console
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        self.Logger.addHandler(ch)

        # notification handler
        self.NotificationHandler = NotificationHandler()

    def log(self, message, level="info", notification=True):

        if "info" == level:
            self.Logger.info(message)
        elif "warning" == level:
            self.Logger.warning(message)
        elif "error" == level:
            self.Logger.error(message)
        elif "debug" == level:
            self.Logger.debug(message)

        if notification and self.NotificationHandler.enabled:
            self.NotificationHandler.send_notification(message)

    def info(self, message):
        self.log(message, "info")

    def warning(self, message):
        self.log(message, "warning")

    def error(self, message):
        self.log(message, "error")

    def debug(self, message):
        self.log(message, "debug")
