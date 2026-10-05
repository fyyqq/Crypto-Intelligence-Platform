"""State for /gainers-losers: top gainers and top losers per rank bucket and
window, computed from the app's own price snapshots
(app/services/price_snapshot_service.py), never from CMC's % change fields.

On load, every window's changes are computed once (one shared calculation)
and kept backend-side; switching window or bucket only re-cuts those lists,
with no further database work.
"""

import asyncio
import sys
from pathlib import Path

import reflex as rx

from frontend.state.coin_state import _fmt_compact_usd, _fmt_usd

_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
_LIMIT = 30


def _service():
    # Reflex's process only has frontend/ on sys.path, so the repo root is
    # added for `app.*`. APPENDED, not inserted first: window_options /
    # bucket_options run at compile time in the main process, and with the
    # repo root first the forked server workers resolve `frontend` to the
    # outer frontend/ folder and fail to load the app.
    if _ROOT not in sys.path:
        sys.path.append(_ROOT)
    from app.services import price_snapshot_service

    return price_snapshot_service


def _load_all() -> dict:
    """Status + changes for every configured window, from one DB session."""
    svc = _service()
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        out = {}
        for name, window in svc.WINDOWS.items():
            status = svc.window_status(db, name)
            changes = svc.compute_changes(db, name) if status["status"] == "ready" else []
            since = status["history_since"]
            out[name] = {
                "label": window.label,
                "status": status["status"],
                "days_remaining": str(status["days_remaining"]),
                "hours_remaining": str(status["hours_remaining"]),
                "since": since.strftime("%d %b %Y, %H:%M UTC") if since else "",
                "changes": changes,
            }
        return out
    finally:
        db.close()


def _display_row(position: int, c: dict) -> dict:
    up = c["pct_change"] > 0
    return {
        "position": str(position),
        "rank": str(c["rank"]),
        "name": c["name"],
        "symbol": c["symbol"],
        "href": f"/coin/{c['symbol'].lower()}",
        "icon_url": f"https://s2.coinmarketcap.com/static/img/coins/64x64/{c['coin_id']}.png",
        "price_now": _fmt_usd(c["price_now"]),
        "price_then": _fmt_usd(c["price_then"]),
        "then_at": c["then_at"].strftime("%d %b %H:%M UTC"),
        "pct_change": f"{c['pct_change']:+.2f}%",
        "color": "var(--green-11)" if up else "var(--red-11)",
        "volume_24h": _fmt_compact_usd(c["volume_24h"]),
    }


class GainersLosersState(rx.State):
    window: str = "24h"
    bucket: int = 100
    loading: bool = True
    error: str = ""
    # Per window: label, status, days/hours remaining, history start.
    statuses: dict[str, dict[str, str]] = {}
    # Per window: the raw change rows (backend only, never sent to the browser).
    _changes: dict[str, list[dict]] = {}

    @rx.var
    def window_options(self) -> list[dict[str, str]]:
        """Window buttons straight from the WINDOWS config (no hardcoding)."""
        svc = _service()
        return [{"key": k, "label": w.label} for k, w in svc.WINDOWS.items()]

    @rx.var
    def bucket_options(self) -> list[int]:
        return list(_service().BUCKETS)

    @rx.var
    def current(self) -> dict[str, str]:
        return self.statuses.get(
            self.window, {"label": "", "status": "collecting", "days_remaining": "", "hours_remaining": "", "since": ""}
        )

    @rx.var
    def is_ready(self) -> bool:
        return self.current.get("status") == "ready"

    def _board(self, direction: str) -> list[dict[str, str]]:
        svc = _service()
        rows = svc.rank_movers(self._changes.get(self.window, []), self.bucket, direction, _LIMIT)
        return [_display_row(i, c) for i, c in enumerate(rows, start=1)]

    @rx.var
    def gainers(self) -> list[dict[str, str]]:
        return self._board("gainers")

    @rx.var
    def losers(self) -> list[dict[str, str]]:
        return self._board("losers")

    @rx.event
    def set_window(self, window: str):
        self.window = window

    @rx.event
    def set_bucket(self, bucket: int):
        self.bucket = bucket

    @rx.event(background=True)
    async def load(self):
        # Keep the hourly hot sync (which records the snapshots) running even
        # when this page is the first one opened after a restart.
        try:
            from frontend.news_catchup import ensure_running

            ensure_running()
        except Exception:  # noqa: BLE001
            pass
        async with self:
            self.loading = True
            self.error = ""
        try:
            data = await asyncio.to_thread(_load_all)
        except Exception as exc:  # noqa: BLE001
            async with self:
                self.loading = False
                self.error = f"Could not load price history: {exc}"
            return
        async with self:
            self._changes = {k: v.pop("changes") for k, v in data.items()}
            self.statuses = data
            self.loading = False
