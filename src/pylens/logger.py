from __future__ import annotations

import logging
import sys
from pylens.settings import log_dir


_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    _logger = logging.getLogger("pylens")
    _logger.setLevel(logging.DEBUG)

    if not _logger.handlers:
        fmt = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [PyLens] %(message)s",
            datefmt="%H:%M:%S",
        )

        # Standard console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        _logger.addHandler(ch)

        # File handler
        try:
            log_file = log_dir() / "pylens.log"
            fh = logging.FileHandler(str(log_file), encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(fmt)
            _logger.addHandler(fh)
        except Exception:
            pass

    return _logger


def log_info(msg: str) -> None:
    get_logger().info(msg)


def log_debug(msg: str) -> None:
    get_logger().debug(msg)


def log_warning(msg: str) -> None:
    get_logger().warning(msg)


def log_error(msg: str) -> None:
    get_logger().error(msg)
