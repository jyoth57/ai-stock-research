from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class _JSONFormatter(logging.Formatter):
    """Machine-readable JSON log lines for production / file output."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            payload.update(record.extra)  # type: ignore[arg-type]
        return json.dumps(payload, ensure_ascii=False)


class _DevFormatter(logging.Formatter):
    """Human-readable coloured formatter for local development."""

    _COLOURS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self._COLOURS.get(record.levelname, "")
        prefix = f"{colour}{record.levelname:<8}{self._RESET}"
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        return f"{ts}  {prefix}  {record.name}  {record.getMessage()}"


def setup_logging(
    level: str = "INFO",
    log_dir: Optional[Path] = None,
    json_logs: bool = False,
) -> None:
    """Configure root logger with console + rotating daily file handler.

    Call once at application startup::

        from src.core.logging import setup_logging
        setup_logging(level="INFO", log_dir=Path("logs"))
    """
    log_dir = log_dir or Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Console
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_JSONFormatter() if json_logs else _DevFormatter())

    # Daily file (always JSON for grep/jq)
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(
        log_dir / f"app-{today}.log", encoding="utf-8"
    )
    file_handler.setFormatter(_JSONFormatter())

    logging.basicConfig(
        level=numeric_level,
        handlers=[console, file_handler],
        force=True,
    )

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger. Usage: log = get_logger(__name__)"""
    return logging.getLogger(name)
