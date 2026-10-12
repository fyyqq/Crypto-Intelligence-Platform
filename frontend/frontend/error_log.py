"""Writes backend/frontend exceptions to `logs/error.log` with a short reference id.

Reflex's default backend handler shows visitors "An error occurred. Contact the
website administrator." in production and only logs the traceback to the
process output, which is easy to lose. These handlers keep that behaviour for
visitors (no internals leak) but also append the full traceback to a rotating
file, and put the same reference id in the toast so a report can be matched to
a log entry.
"""

import logging
import time
import traceback
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

import reflex as rx
from reflex.event import EventSpec

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "error.log"

_logger = logging.getLogger("repace.errors")


def _setup() -> None:
    if _logger.handlers:
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s UTC %(message)s")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    # Also keep it in the process output (reflex.log / journalctl) like Reflex's default.
    _logger.addHandler(logging.StreamHandler())
    _logger.setLevel(logging.ERROR)
    _logger.propagate = False


_setup()


def _record(kind: str, exception: Exception) -> str:
    ref = uuid.uuid4().hex[:8]
    tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    _logger.error("[%s] ref=%s %s: %s\n%s", kind, ref, type(exception).__name__, exception, tb)
    return ref


def backend_exception_handler(exception: Exception) -> EventSpec:
    ref = _record("backend", exception)
    return rx.toast(
        "An error occurred.",
        level="error",
        fallback_to_alert=True,
        description=f"Contact the website administrator.\nReference: {ref}",
        position="top-center",
        id="backend_error",
        style={"width": "500px", "white-space": "pre-wrap"},
    )


def frontend_exception_handler(exception: Exception) -> None:
    _record("frontend", exception)
