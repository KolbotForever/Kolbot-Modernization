"""
Centralized logging for Kolbot-Python.

Provides per-instance, per-module logging with file and console output.
Each bot instance gets its own log file; a shared master log captures everything.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

_CONSOLE_FMT = "[%(asctime)s] %(levelname)-8s %(name)-24s %(message)s"
_FILE_FMT = "[%(asctime)s] %(levelname)-8s %(name)-24s [%(filename)s:%(lineno)d] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _make_formatter(fmt: str) -> logging.Formatter:
    return logging.Formatter(fmt, datefmt=_DATE_FMT)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_initialized: bool = False
_log_dir: Path = Path("logs")


def init_logging(
    log_dir: str | Path = "logs",
    level: int = logging.DEBUG,
    console_level: int = logging.INFO,
) -> None:
    """Initialize the root Kolbot logger. Call once at startup."""
    global _initialized, _log_dir
    if _initialized:
        return

    _log_dir = Path(log_dir)
    _log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("kolbot")
    root.setLevel(level)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(console_level)
    ch.setFormatter(_make_formatter(_CONSOLE_FMT))
    root.addHandler(ch)

    # Master file handler
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    master_path = _log_dir / f"kolbot_{ts}.log"
    fh = logging.FileHandler(master_path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(_make_formatter(_FILE_FMT))
    root.addHandler(fh)

    _initialized = True
    root.info("Logging initialized  dir=%s  level=%s", _log_dir, logging.getLevelName(level))


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'kolbot' namespace."""
    return logging.getLogger(f"kolbot.{name}")


def get_instance_logger(profile_name: str) -> logging.Logger:
    """Return a logger that also writes to a per-instance log file."""
    logger = logging.getLogger(f"kolbot.instance.{profile_name}")
    if not logger.handlers:
        _log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = _log_dir / f"{profile_name}_{ts}.log"
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_make_formatter(_FILE_FMT))
        logger.addHandler(fh)
    return logger
