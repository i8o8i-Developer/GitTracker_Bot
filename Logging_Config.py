"""
Logging Configuration For GitTracker Bot.
Provides Structured Logging For Production Use.
"""

import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_file: str = "logs/gittracker.log") -> logging.Logger:
    """
    Setup Comprehensive Logging Configuration.

    Args:
        log_level: Logging Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path To Log File

    Returns:
        Configured Logger Instance
    """

    # Create Logs Directory If It Doesn't Exist
    log_path = Path(log_file)
    log_path.parent.mkdir(exist_ok=True)

    # Convert String Log Level To Logging Constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create Logger
    logger = logging.getLogger('gittracker')
    logger.setLevel(numeric_level)

    # Remove Any Existing Handlers
    logger.handlers.clear()

    # Create Formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)

    # File Handler With Rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)

    return logger


# Global Logger Instance
logger = setup_logging()