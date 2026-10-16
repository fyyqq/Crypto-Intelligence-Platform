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
        first, last = svc.saved_days(db)
        out["_days"] = (first.isoformat() if first else "", last.isoformat() if last else "")
        latest = svc._latest_sync_time(db)
        out["_synced"] = latest.strftime("%d %b %H:%M UTC") if latest else ""
        return out
    finally:
        db.close()


def _refresh_all() -> dict:
    """Refresh button: a fresh top-500 CMC pull (skipped inside the global
    cooldown, see run_manual_hot_sync), save today's board, then reload."""
    _service()  # puts the repo root on sys.path
    from app.scheduler.jobs import run_manual_hot_sync

    if run_manual_hot_sync():
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            _service().record_daily_movers(db)
        finally:
            db.close()
    return _load_all()


def _load_day(day_iso: str) -> dict[str, list[dict]]:
    """A saved day's boards ({window: changes}) from movers_daily."""
    from datetime import date

    svc = _service()
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return svc.load_daily_movers(db, date.fromisoformat(day_iso))
    finally:
        db.close()


def _coin_slug(cmc_id, symbol):
    from frontend.state.coin_state import coin_slug  # lazy: the coin list may not be loaded yet

    return coin_slug(cmc_id, symbol)


def _load_holdings(email: str) -> dict[str, float]:
    """{ticker: price} of the coins held on the MEXC account, only for a viewer listed in MEXC_VIEWER_EMAILS
    (the same gate as the Portfolio page). {} for anyone else. Blocking."""
    _service()  # puts the repo root on sys.path
    from app.services import mexc_service

    if not mexc_service.can_view(email):
        return {}
    return mexc_service.held_assets()


def _display_row(position: int, c: dict, held: bool = False, extra: bool = False) -> dict:
    up = c["pct_change"] > 0
    return {
        "position": str(position),
        "held": "1" if held else "",  # the only thing about a holding that reaches the browser
        "extra": "1" if extra else "",  # a held coin added below the top rows
        "rank": str(c["rank"]),
        "name": c["name"],
        "symbol": c["symbol"],
        "href": "/coins/" + _coin_slug(c["coin_id"], c["symbol"]),
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
    # Calendar: "" = live board; else an ISO UTC day whose saved board
    # (movers_daily) is shown. first/last_day bound the date picker.
    selected_day: str = ""
    first_day: str = ""
    last_day: str = ""
    _day_changes: dict[str, list[dict]] = {}
    day_windows: list[str] = []  # windows with a saved board on selected_day
    # Refresh icon: spinning while a refresh runs; time of the newest sync.
    refreshing: bool = False
    synced_at: str = ""
    # Change-column sort per board, by signed % change. Defaults put the
    # biggest move first: gainers descending, losers ascending (most negative).
    gainers_desc: bool = True
    losers_desc: bool = False
    # {ticker: price} of the coins held on the viewer's MEXC account (backend only: just a "held" flag per row is sent).
    _held: dict[str, float] = {}

    @rx.var
    def selected_day_label(self) -> str:
        if not self.selected_day:
            return ""
        from datetime import date

        return date.fromisoformat(self.selected_day).strftime("%d %b %Y")

    @rx.var
    def first_day_label(self) -> str:
        if not self.first_day:
            return ""
        from datetime import date

        return date.fromisoformat(self.first_day).strftime("%d %b %Y")

    @rx.var
    def day_saved_at(self) -> str:
        """When the shown saved board was computed (its latest sync)."""
        rows = self._day_changes.get(self.window) or []
        return rows[0]["now_at"].strftime("%d %b %Y, %H:%M UTC") if rows else ""

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
        if self.selected_day:
            label = self.statuses.get(self.window, {}).get("label", self.window)
            status = "ready" if self.window in self.day_windows else "missing"
            return {"label": label, "status": status, "days_remaining": "", "hours_remaining": "", "since": ""}
        return self.statuses.get(
            self.window, {"label": "", "status": "collecting", "days_remaining": "", "hours_remaining": "", "since": ""}
        )

    @rx.var
    def is_ready(self) -> bool:
        return self.current.get("status") == "ready"

    @rx.var
    def day_missing(self) -> bool:
        """A past day is picked but nothing was saved for this window."""
        return self.current.get("status") == "missing"

    def _board(self, direction: str) -> list[dict[str, str]]:
        svc = _service()
        source = self._day_changes if self.selected_day else self._changes
        changes = source.get(self.window, [])
        # Held coins are marked on the live board only (a saved day's board says nothing about what you hold now).
        held_ids = set() if self.selected_day else svc.held_coin_ids(changes, self._held)
        rows = svc.board_rows(changes, self.bucket, direction, _LIMIT, held_ids)
        # The Change header's sort only reorders the board's own top coins (it never swaps in different ones);
        # # stays the biggest-move position. A held coin that is not among them stays at the end, whatever its #.
        desc = self.gainers_desc if direction == "gainers" else self.losers_desc
        top = sorted((r for r in rows if not r["extra"]), key=lambda r: r["coin"]["pct_change"], reverse=desc)
        extra = [r for r in rows if r["extra"]]
        return [_display_row(r["position"], r["coin"], r["held"], r["extra"]) for r in top + extra]

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

    @rx.event
    def toggle_sort(self, direction: str):
        if direction == "gainers":
            self.gainers_desc = not self.gainers_desc
        else:
            self.losers_desc = not self.losers_desc

    @rx.event
    def set_day(self, day: str):
        """From the calendar's date input; "" goes back to the live board."""
        self.selected_day = day or ""
        self._day_changes = {}
        self.day_windows = []
        if self.selected_day:
            return GainersLosersState.load_day

    @rx.event
    def show_live(self):
        return GainersLosersState.set_day("")

    @rx.event(background=True)
    async def load_day(self):
        async with self:
            day = self.selected_day
            self.loading = True
            self.error = ""
        try:
            data = await asyncio.to_thread(_load_day, day)
        except Exception as exc:  # noqa: BLE001
            async with self:
                self.loading = False
                self.error = f"Could not load the saved board: {exc}"
            return
        async with self:
            if self.selected_day == day:  # ignore a stale answer after a re-pick
                self._day_changes = data
                self.day_windows = list(data)
            self.loading = False

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
            self._apply(data)
            self.loading = False
        await self._load_held()

    async def _load_held(self):
        """Which coins the logged-in viewer holds on MEXC (the board then marks them). Never blocks or breaks the
        page: any failure just means no marks."""
        from frontend.state.coin_state import CoinState

        try:
            async with self:
                cs = await self.get_state(CoinState)
                email = cs.user_email if cs.is_logged_in else ""
            held = await asyncio.to_thread(_load_holdings, email) if email else {}
        except Exception:  # noqa: BLE001
            held = {}
        async with self:
            self._held = held

    def _apply(self, data: dict):
        self.first_day, self.last_day = data.pop("_days")
        self.synced_at = data.pop("_synced")
        self._changes = {k: v.pop("changes") for k, v in data.items()}
        self.statuses = data

    @rx.event(background=True)
    async def refresh(self):
        """Refresh icon: fresh CMC prices (global 5-minute cooldown), then
        recompute every window. Keeps the tables up while it runs (the icon
        spins instead), and spins at least one full turn."""
        async with self:
            if self.refreshing:
                return
            self.refreshing = True
            self.error = ""
            self.selected_day = ""  # a refresh always shows the live board
            self._day_changes = {}
            self.day_windows = []
        try:
            data, _ = await asyncio.gather(asyncio.to_thread(_refresh_all), asyncio.sleep(0.8))
        except Exception as exc:  # noqa: BLE001
            async with self:
                self.refreshing = False
                self.error = f"Could not refresh prices: {exc}"
            return
        async with self:
            self._apply(data)
            self.refreshing = False
        await self._load_held()
