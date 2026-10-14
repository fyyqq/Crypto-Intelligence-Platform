"""State for /tools/cpi-fomc ("Forex Factory"): this week's CPI, FOMC and Non-Farm Employment events (app/services/macro_calendar_service.py).
While the page is open it re-reads every 30 s (the service itself fetches the free feed at most once a
minute for everyone, and asks Apify for actual values only after a release); the table, the "next
event" countdown and the Today/past/soon styling all follow the clock without a reload."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import reflex as rx

_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
WATCH_SECONDS = 30


def _service():
    if _ROOT not in sys.path:  # appended, like the other states (see gainers_losers_state)
        sys.path.append(_ROOT)
    from app.services import macro_calendar_service

    return macro_calendar_service


def _snapshot(scope: str) -> dict:
    """Blocking: everything the page shows for `scope` ("USD" or "ALL")."""
    svc = _service()
    now = datetime.now(timezone.utc)
    data = svc.get_events(now, ("USD",) if scope == "USD" else None)
    events = data["events"]
    svc.refresh_actuals_in_background(events, now)  # official sources (BLS/FRED), then Apify if configured; never blocks
    nxt = svc.next_event(events, now)
    fetched = data["fetched_at"]
    html = svc.build_html(events, now, data["has_actuals_source"])
    if data["error"] and not events:  # feed blocked or down and no copy yet: say so, do not claim "no events"
        html = '<div class="mc-empty">The calendar feed is rate limited or unreachable right now. This page retries by itself.</div>'
    return {
        "html": html,
        "count": len(events),
        "unavailable": bool(data["error"] and not events),  # feed blocked/down and no copy to show
        "updated": fetched.astimezone(svc.KL).strftime("%H:%M:%S") if fetched else "",
        "stale": data["stale"],
        "error": data["error"],
        "has_source": data["has_actuals_source"],
        "next_title": nxt["title"] if nxt else "",
        "next_when": nxt["start"].astimezone(svc.KL).strftime("%a %d %b, %H:%M") if nxt else "",
        "next_in": svc.countdown((nxt["start"] - now).total_seconds()) if nxt else "",
        "next_impact": nxt["impact"] if nxt else "",
        "next_currency": nxt["currency"] if nxt else "",
    }


class MacroCalendarState(rx.State):
    loaded: bool = False
    scope: str = "USD"
    html: str = ""
    count: int = 0
    updated: str = ""
    stale: bool = False
    error: str = ""
    has_source: bool = False
    unavailable: bool = False
    next_title: str = ""
    next_when: str = ""
    next_in: str = ""
    next_impact: str = ""
    next_currency: str = ""
    _watching: bool = False

    def _apply(self, snap: dict):
        for k, v in snap.items():
            setattr(self, k, v)

    @rx.event
    async def load(self):
        self._apply(await asyncio.to_thread(_snapshot, self.scope))
        self.loaded = True
        return MacroCalendarState.watch

    @rx.event
    async def set_scope(self, scope: str):
        if scope not in ("USD", "ALL") or scope == self.scope:
            return
        self.scope = scope
        self._apply(await asyncio.to_thread(_snapshot, scope))

    @rx.event(background=True)
    async def watch(self):
        """Refreshes every 30 s while this tab is open (one loop per tab)."""
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
                async with self:
                    scope = self.scope
                try:
                    snap = await asyncio.to_thread(_snapshot, scope)
                except Exception:  # noqa: BLE001  (keep what is shown; try again)
                    continue
                async with self:
                    if self.scope == scope:
                        self._apply(snap)
        finally:
            async with self:
                self._watching = False
