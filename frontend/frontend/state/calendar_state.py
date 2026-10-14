"""State for /tools/crypto-calendar: the monthly @layergg calendar posts
(app/services/crypto_calendar_service.py), one month at a time with a pager
and month chips from January 2026 to the current month. The month grid is
rendered server-side to one HTML string (escaped event text) and only the
chosen month is sent to the browser."""

import asyncio
import sys
import time
from datetime import date
from pathlib import Path

import reflex as rx

_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
_CACHE_SECONDS = 300
_cache: tuple[float, dict] | None = None


def _service():
    if _ROOT not in sys.path:  # appended, like the other states (see gainers_losers_state)
        sys.path.append(_ROOT)
    from app.services import crypto_calendar_service

    return crypto_calendar_service


def _load() -> dict:
    global _cache
    if _cache and time.time() - _cache[0] < _CACHE_SECONDS:
        return _cache[1]
    svc = _service()
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        months = svc.load_months(db)
        tickers = {e["ticker"].upper() for m in months.values() for e in m["events"] if e["ticker"] and e["kind"] == "crypto"}
        try:
            icons = svc.symbol_icons(db, tickers)
        except Exception:  # noqa: BLE001  (logos are decoration: the calendar renders without them)
            db.rollback()
            icons = {}
    finally:
        db.close()
    today = date.today()
    keys = svc.month_keys(today)
    data = {
        "keys": keys,
        "html": {k: svc.build_month_html(k, months.get(k), icons, today) for k in keys},
        "counts": {k: len(months[k]["events"]) if k in months else 0 for k in keys},
        "urls": {k: months[k]["url"] if k in months else "" for k in keys},
    }
    _cache = (time.time(), data)
    return data


class CalendarState(rx.State):
    loaded: bool = False
    keys: list[str] = []
    index: int = 0
    month_html: str = ""
    month_title: str = ""
    post_url: str = ""
    chips: list[dict[str, str]] = []
    _data: dict = {}

    def _show(self, i: int):
        svc = _service()
        i = max(0, min(i, len(self.keys) - 1))
        self.index = i
        key = self.keys[i]
        self.month_html = self._data["html"][key]
        self.month_title = f"{svc.MONTHS[int(key[5:]) - 1]} {key[:4]}"
        self.post_url = self._data["urls"][key]
        self.chips = [
            {"key": k, "index": str(j), "label": svc.MONTHS[int(k[5:]) - 1][:3], "active": "1" if j == i else "0", "has_data": "1" if self._data["counts"][k] else "0"}
            for j, k in enumerate(self.keys)
        ]

    @rx.event
    async def load(self):
        """on_load: all months to the current one, opening on the latest month that has events."""
        data = await asyncio.to_thread(_load)
        self._data = data
        self.keys = data["keys"]
        if not self.keys:
            self.loaded = True
            return
        with_data = [i for i, k in enumerate(self.keys) if data["counts"][k]]
        self._show(with_data[-1] if with_data else len(self.keys) - 1)
        self.loaded = True

    @rx.event
    def go(self, i: str):
        self._show(int(i))

    @rx.event
    def prev_month(self):
        self._show(self.index - 1)

    @rx.event
    def next_month(self):
        self._show(self.index + 1)
