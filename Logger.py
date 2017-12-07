import logging
import os

LOG_LEVEL = os.environ.get("LOG_LEVEL") or "WARNING"


class CustomLogger(logging.Logger):
    FORMAT = '%(asctime)s [%(levelname)s] [%(filename)s(%(lineno)d)] %(message)s'
    def __init__(self, name):
        log_level_dict = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        level = log_level_dict.get(LOG_LEVEL) or logging.WARNING
        super(CustomLogger, self).__init__(name, level)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(self.FORMAT))
        self.addHandler(handler)
        return


if __name__ == "__main__":
    logging.setLoggerClass(CustomLogger)
    logger = logging.getLogger(__name__)

    logger.debug("debug")
    logger.info("info")
    logger.warn("warn")
    logger.error("error")
