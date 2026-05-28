"""Logging configuration for the application."""

import logging
import sys
import os
from pathlib import Path
from config import LOG_LEVEL, LOG_FORMAT


def configure_root_logging(log_file: str = None):
    """
    Configure the root logger for the entire application.

    All child loggers will inherit from this root logger, ensuring
    all logs go to both console and file.

    Args:
        log_file: Path to log file for all application logs
    """
    root_logger = logging.getLogger()

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Set root logger level
    root_logger.setLevel(LOG_LEVEL)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(LOG_FORMAT)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(LOG_LEVEL)
    root_logger.addHandler(console_handler)

    # File handler (if log_file is provided)
    if log_file:
        # Create logs directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(LOG_LEVEL)
        root_logger.addHandler(file_handler)


def configure_logging(name: str = None, log_file: str = None) -> logging.Logger:
    """
    Configure and return a logger instance.

    Args:
        name: Logger name (typically __name__)
        log_file: Optional path to log file for this service

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name or "maas")

    # Only configure if not already configured
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(LOG_FORMAT)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler (if log_file is provided)
        if log_file:
            # Create logs directory if it doesn't exist
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, mode="a")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        logger.setLevel(LOG_LEVEL)

    return logger
