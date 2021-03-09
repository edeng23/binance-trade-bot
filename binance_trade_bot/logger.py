import logging

from .notifications import NotificationHandler

LOG_PATH = "logs/crypto_trading.log"


class Logger:

    logger = None
    notification_handler = None

    def __init__(self):
        # Logger setup
        self.logger = logging.getLogger("crypto_trader_logger")
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler = logging.FileHandler(LOG_PATH)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # logging to console
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # notification handler
        self.notification_handler = NotificationHandler()

    def log(self, message, level="info", notification=True):

        if level == "info":
            self.logger.info(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "debug":
            self.logger.debug(message)

        if notification and self.notification_handler.enabled:
            self.notification_handler.send_notification(message)

    def info(self, message):
        self.log(message, "info")

    def warning(self, message):
        self.log(message, "warning")

    def error(self, message):
        self.log(message, "error")

    def debug(self, message):
        self.log(message, "debug")
