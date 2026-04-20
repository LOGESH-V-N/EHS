import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

def get_logger(name="app_logger", log_dir="logs", level=logging.INFO):
    """
    Returns a logger instance that creates a new log file for each day with the date in filename.

    Args:
        name (str): logger name
        log_dir (str): directory to store log files
        level (int): logging level

    Returns:
        logger instance
    """
    import os
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)

        # File handler: new file each day
        log_file = f"{log_dir}/app_{datetime.now().strftime('%Y-%m-%d')}.log"
        file_handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",     # rotate at midnight
            interval=1,          # every 1 day
            backupCount=7,       # keep last 7 days
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.suffix = "%Y-%m-%d.log"

        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        # Add handlers
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger
