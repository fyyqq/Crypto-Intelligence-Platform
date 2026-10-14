"""State for the homepage "Market Status" card (components/market_overview.py):
Fear & Greed, total crypto market cap, top 20 and Altcoin Season, from the same
free sources and caches as /tools (app/services/market_tools_service.py).
Loaded in the background on page load so it never delays the table; each
figure that fails to load just shows an em dash."""

import asyncio
import sys
from pathlib import Path

import reflex as rx

from frontend.state.coin_state import _fmt_compact_usd

_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
_UP, _DOWN = "var(--green-10)", "var(--red-10)"


def _service():
    if _ROOT not in sys.path:  # appended, like the other states (see gainers_losers_state)
        sys.path.append(_ROOT)
    from app.services import market_tools_service

    return market_tools_service


def _zone(value: int) -> tuple[str, str]:
    """(colour, text colour on it), the /tools gauge zones."""
    if value < 25:
        return "#ea3943", "#ffffff"
    if value < 45:
        return "#ea8c00", "#111111"
    if value < 55:
        return "#d6b800", "#111111"
    if value < 75:
        return "#93d900", "#111111"
    return "#16c784", "#111111"


def _change(pct) -> tuple[str, str]:
    """("▼ 0.46%", colour) or ("", "") when unknown."""
    if pct is None:
        return "", ""
    return f"{'▲' if pct >= 0 else '▼'} {abs(pct):.2f}%", _UP if pct >= 0 else _DOWN


class MarketStatusState(rx.State):
    loaded: bool = False
    fng_value: int = -1
    fng_label: str = ""
    fng_svg: str = ""
    fng_color: str = "#d6b800"
    fng_text_color: str = "#111111"
    season_value: int = -1
    season_label: str = ""
    mcap: str = "—"
    mcap_change: str = ""
    mcap_color: str = _UP
    top20: str = "—"
    top20_change: str = ""
    top20_color: str = _UP

    @rx.var
    def has_fng(self) -> bool:
        return self.fng_value >= 0

    @rx.var
    def has_season(self) -> bool:
        return self.season_value >= 0

    @rx.var
    def season_left(self) -> str:
        return f"calc({max(0, min(100, self.season_value))}% - 8px)"

    @rx.event(background=True)
    async def load(self):
        svc = _service()
        fng, season, status = await asyncio.gather(
            asyncio.to_thread(svc.with_stale, "home:fng", lambda: svc.get_fear_greed("alternative_me")),
            asyncio.to_thread(svc.with_stale, "home:season", lambda: svc.get_altcoin_season("coingecko")),
            asyncio.to_thread(svc.with_stale, "home:status", svc.get_market_status),
            return_exceptions=True,
        )
        async with self:
            if not isinstance(fng, Exception):
                self.fng_value, self.fng_label = int(fng["value"]), fng["label"]
                self.fng_svg = svc.fng_arc_svg(self.fng_value)
                self.fng_color, self.fng_text_color = _zone(self.fng_value)
            if not isinstance(season, Exception):
                self.season_value, self.season_label = int(season["index"]), season["label"]
            if not isinstance(status, Exception):
                self.mcap = _fmt_compact_usd(status["total"])
                self.mcap_change, self.mcap_color = _change(status["total_change"])
                self.top20 = _fmt_compact_usd(status["top20"])
                self.top20_change, self.top20_color = _change(status["top20_change"])
            self.loaded = True
