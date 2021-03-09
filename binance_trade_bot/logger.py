import logging
import logging.handlers

from .notifications import NotificationHandler

class Logger:

    Logger = None
    NotificationHandler = None

    def __init__(self, loggingService = "crypto_trading"):
        # Logger setup
        self.Logger = logging.getLogger(f"{loggingService}_logger")
        self.Logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        # default is "logs/crypto_trading.log"
        fh = logging.FileHandler(f"logs/{loggingService}.log")
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

    def info(self, message, notification=True):
        self.log(message, "info", notification)

    def warning(self, message, notification=True):
        self.log(message, "warning", notification)

    def error(self, message, notification=True):
        self.log(message, "error", notification)

    def debug(self, message, notification=True):
        self.log(message, "debug", notification)
