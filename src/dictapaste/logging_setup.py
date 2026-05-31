from __future__ import annotations

import logging
from pathlib import Path

from .config import default_config_dir

LOG_FILE_NAME = "dictapaste.log"


def setup_app_logging() -> Path:
    log_dir = default_config_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILE_NAME

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    has_file_handler = False
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                if Path(handler.baseFilename) == log_path:
                    has_file_handler = True
            except Exception:
                continue

    if not has_file_handler:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setFormatter(formatter)

    logging.getLogger(__name__).info("Logging initialized. log_file=%s", log_path)
    return log_path


def log_file_path() -> Path:
    """Return the path to the log file."""
    return default_config_dir() / LOG_FILE_NAME
