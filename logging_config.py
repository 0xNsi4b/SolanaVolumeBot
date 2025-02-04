import logging
import logging.config

def setup_logging():
    def disable_external_loggers(own_prefix="root"):
        for name in list(logging.root.manager.loggerDict):
            if not name.startswith(own_prefix):
                logger = logging.getLogger(name)
                logger.disabled = True

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "colored": {
                "()": "colorlog.ColoredFormatter",
                "format": "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "log_colors": {
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "bold_red",
                }
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "colored",
                "level": "DEBUG",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "INFO",
        },
    }
    logging.config.dictConfig(config)
    disable_external_loggers()


if __name__ == "__main__":
    setup_logging()