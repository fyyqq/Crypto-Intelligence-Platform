"""State for the homepage "Gainers & Losers" card (components/market_overview.py):
the top 5 gainers and top 5 losers of the Top 100 over 24h, from the app's own
price snapshots (price_snapshot_service.top_movers, the same numbers as
/gainers-losers). Page 1 = gainers, page 2 = losers. Loaded in the background
on page load and cached 60s (the snapshots only change hourly)."""

import asyncio
import sys
import time
from pathlib import Path

import reflex as rx

from frontend.state.coin_state import _fmt_usd

_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
_CACHE_SECONDS = 60
_cache: tuple[float, dict] | None = None


def _service():
    if _ROOT not in sys.path:  # appended, like the other states (see gainers_losers_state)
        sys.path.append(_ROOT)
    from app.services import price_snapshot_service

    return price_snapshot_service


def _row(position: int, c: dict) -> dict:
    up = c["pct_change"] > 0
    return {
        "position": str(position),
        "symbol": c["symbol"],
        "href": f"/coin/{c['symbol'].lower()}",
        "icon_url": f"https://s2.coinmarketcap.com/static/img/coins/64x64/{c['coin_id']}.png",
        "price": _fmt_usd(c["price_now"]),
        "change": f"{'▲' if up else '▼'} {abs(c['pct_change']):.2f}%",
        "color": "var(--green-10)" if up else "var(--red-10)",
    }


def _load() -> dict:
    global _cache
    if _cache and time.time() - _cache[0] < _CACHE_SECONDS:
        return _cache[1]
    svc = _service()
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        m = svc.top_movers(db, "24h", 100, 5)
    finally:
        db.close()
    data = {
        "ready": m["status"] == "ready",
        "hours": m["hours_remaining"],
        "gainers": [_row(i, c) for i, c in enumerate(m["gainers"], 1)],
        "losers": [_row(i, c) for i, c in enumerate(m["losers"], 1)],
    }
    _cache = (time.time(), data)
    return data


class HomeMoversState(rx.State):
    loaded: bool = False
    failed: bool = False
    collecting: str = ""  # "about N hours" while the 24h window has too little history
    gainers: list[dict[str, str]] = []
    losers: list[dict[str, str]] = []
    page: int = 0  # 0 = gainers, 1 = losers

    @rx.var
    def rows(self) -> list[dict[str, str]]:
        return self.gainers if self.page == 0 else self.losers

    @rx.var
    def page_label(self) -> str:
        return f"{self.page + 1}/2"

    @rx.var
    def title(self) -> str:
        return "Top Gainers" if self.page == 0 else "Top Losers"

    @rx.event
    def flip_page(self):
        self.page = 1 - self.page

    @rx.event(background=True)
    async def load(self):
        try:
            data = await asyncio.to_thread(_load)
        except Exception:  # noqa: BLE001  (the card just shows its empty state)
            async with self:
                self.failed, self.loaded = True, True
            return
        async with self:
            self.failed = False
            self.collecting = "" if data["ready"] else f"about {data['hours']} hour(s)"
            self.gainers, self.losers = data["gainers"], data["losers"]
            self.loaded = True
