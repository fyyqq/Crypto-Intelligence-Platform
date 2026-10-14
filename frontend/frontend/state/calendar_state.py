"""State for /tools/crypto-calendar: the monthly @layergg calendar posts
(app/services/crypto_calendar_service.py), one month at a time with a pager
and month chips from January of the shown year (the latest year with a post)
to the current month. The month grid is rendered server-side to one HTML
string (escaped event text) and only the chosen month is sent to the browser.

While the page is open it re-checks every minute (watch): a new post or an
edited one updates the chips and, if the visitor is on the newest month,
switches to it by itself; a visitor browsing an older month keeps their place."""

import asyncio
import sys
import time
from datetime import date
from pathlib import Path

import reflex as rx

_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
_CACHE_SECONDS = 45
WATCH_SECONDS = 60
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
    keys = svc.month_keys(today, months)
    data = {
        "keys": keys,
        "html": {k: svc.build_month_html(k, months.get(k), icons, today) for k in keys},
        "counts": {k: len(months[k]["events"]) if k in months else 0 for k in keys},
        "urls": {k: months[k]["url"] if k in months else "" for k in keys},
    }
    # changes whenever a month appears, is edited, or the year rolls over
    data["signature"] = (tuple(keys), tuple(sorted(data["counts"].items())), tuple(sorted(data["urls"].items())), tuple(sorted((k, hash(h)) for k, h in data["html"].items())))
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
    following: bool = True  # on the newest month with events: new posts switch the view by themselves
    _data: dict = {}
    _watching: bool = False

    def _latest(self) -> int:
        with_data = [i for i, k in enumerate(self.keys) if self._data["counts"][k]]
        return with_data[-1] if with_data else len(self.keys) - 1

    def _show(self, i: int):
        svc = _service()
        i = max(0, min(i, len(self.keys) - 1))
        self.index = i
        self.following = i == self._latest()
        key = self.keys[i]
        self.month_html = self._data["html"][key]
        self.month_title = f"{svc.MONTHS[int(key[5:]) - 1]} {key[:4]}"
        self.post_url = self._data["urls"][key]
        self.chips = [
            {"key": k, "index": str(j), "label": svc.MONTHS[int(k[5:]) - 1][:3], "active": "1" if j == i else "0", "has_data": "1" if self._data["counts"][k] else "0"}
            for j, k in enumerate(self.keys)
        ]

    def _apply(self, data: dict):
        """Takes new data. Opens the newest month with events when the visitor was following the
        newest one (or on first load); otherwise stays on the month they are reading."""
        was_following, current = self.following, (self.keys[self.index] if self.keys else None)
        self._data = data
        self.keys = data["keys"]
        if not self.keys:
            return
        if was_following or current not in self.keys:
            self._show(self._latest())
        else:
            self._show(self.keys.index(current))  # stays on the month being read; `following` is recomputed

    @rx.event
    async def load(self):
        """on_load: all months of the shown year up to the current one, opening on the newest month with events."""
        self.following = True
        self._apply(await asyncio.to_thread(_load))
        self.loaded = True
        return CalendarState.watch

    @rx.event(background=True)
    async def watch(self):
        """Re-reads the posts every minute while this tab is open (one loop per tab): a new month's
        post, an edited post or a new year shows up without a reload."""
        async with self:
            if self._watching:
                return
            self._watching = True
        from frontend.frontend import app as reflex_app

        try:
            while True:
                await asyncio.sleep(WATCH_SECONDS)
                if self.router.session.client_token not in reflex_app.event_namespace.token_to_sid:
                    break  # tab closed
                try:
                    data = await asyncio.to_thread(_load)
                except Exception:  # noqa: BLE001  (keep the page as it is; try again next minute)
                    continue
                async with self:
                    if data["signature"] != self._data.get("signature"):
                        self._apply(data)
        finally:
            async with self:
                self._watching = False

    @rx.event
    def go(self, i: str):
        self._show(int(i))

    @rx.event
    def prev_month(self):
        self._show(self.index - 1)

    @rx.event
    def next_month(self):
        self._show(self.index + 1)
