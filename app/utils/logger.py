"""Logging setup for the API and worker processes.

Modules log through ``logging.getLogger(__name__)``. Each entry point
(main.py, worker.py) calls :func:`configure_root_logging` once; every module
logger propagates to the root logger and so goes to the console and that
process's log file.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from app.config import LOG_FORMAT, LOG_LEVEL


def configure_root_logging(log_file: Optional[str] = None) -> None:
    """Send all log records to the console and, if given, to ``log_file``."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(LOG_FORMAT)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode="a"))

    for handler in handlers:
        handler.setFormatter(formatter)
        handler.setLevel(LOG_LEVEL)
        root_logger.addHandler(handler)
