"""State of the MEXC portfolio: the /portfolio dashboard and the coin page's "Your MEXC" box (above Alerts).

Read-only (app/services/mexc_service.py). Only an account listed in MEXC_VIEWER_EMAILS gets any data: every
loop and event checks mexc_service.can_view(user_email) on the server. The browser only receives formatted
strings; the key, the secret and the raw MEXC replies stay on the server.

Rules for this state (Reflex sends every var without a leading underscore to the browser):
- A public var (pf_*, coin_mexc_*) holds ONLY display strings, never a raw MEXC reply, id or credential. Any raw
  MEXC data a feature needs must live in a `_`-prefixed (backend-only) var and be emptied in _clear_portfolio.
- _clear_portfolio runs on logout (CoinState.logout) and whenever a loop finds the viewer check failing, so a
  logged-out session keeps none of the balances or orders. It resets every pf_* / coin_mexc_* var by prefix, so
  a new var is covered automatically.
- A loop cycle that fails (network, database, bad reply) shows a short message and the loop carries on; the
  detail goes to the server log."""

import asyncio
import dataclasses
import json
import logging
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import reflex as rx

from frontend.state.coin_state import _ROOT_FOR_APP, _UNIVERSE, CoinState, _fmt_pct, _fmt_usd

_log = logging.getLogger(__name__)
_TZ = ZoneInfo("Asia/Kuala_Lumpur")
_REFRESH_FAILED = "MEXC data could not be refreshed just now. Retrying shortly."
_PORTFOLIO_VAR_PREFIXES = ("pf_", "coin_mexc_")  # every public var of this state starts with one of these
_TRADES_PER_PAGE = 5  # Recent fills: rows per page
_LINE_AVG = "#2962FF"  # coin page lines chart: average buy price (TradingView's blue)
_LINE_LIMIT = "#22C55E"  # limit orders (green)
_LINE_STOP = "#EF4444"  # stop-loss / stop orders, drawn at the trigger price (red, dashed)
# Timeframes of the coin page lines chart: (button label, MEXC kline interval).
CHART_INTERVALS = (("15m", "15m"), ("1h", "60m"), ("4h", "4h"), ("1D", "1d"), ("1W", "1W"))
_CHART_INTERVAL_SET = {iv for _, iv in CHART_INTERVALS}
_HIST_RANGES = ("24h", "7d", "1m", "full")
_PAGE_SECONDS = 10  # /portfolio redraw (the service reads MEXC at most every 20 s, prices every 10 s)
_COIN_SECONDS = 15  # coin page box
_ACCOUNT_PATHS = {"/portfolio", "/profile", "/profile/edit-profile"}
# Allocation ring colours (Radix step 9: readable on light and dark), the last one for "Others".
_RING = ["var(--blue-9)", "var(--violet-9)", "var(--teal-9)", "var(--amber-9)", "var(--pink-9)", "var(--cyan-9)", "var(--orange-9)"]
_RING_OTHER = "var(--gray-8)"


def _svc():
    if _ROOT_FOR_APP not in sys.path:
        sys.path.insert(0, _ROOT_FOR_APP)
    from app.services import mexc_service

    return mexc_service


def _fx():
    if _ROOT_FOR_APP not in sys.path:
        sys.path.insert(0, _ROOT_FOR_APP)
    from app.services import fx_service

    return fx_service


def _history():
    if _ROOT_FOR_APP not in sys.path:
        sys.path.insert(0, _ROOT_FOR_APP)
    from app.services import portfolio_history_service

    return portfolio_history_service


def _money(v: float) -> str:
    return _svc().fmt_money(v)


def _signed_money(v: float) -> str:
    return _svc().fmt_signed_money(v)


def _color(v: float) -> str:
    return "var(--green-11)" if v > 0 else "var(--red-11)" if v < 0 else "var(--gray-11)"


def _qty(v: float) -> str:
    return _svc().fmt_qty(v)


def _when(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, _TZ).strftime("%d %b, %H:%M") if ms else ""


_coin_index: dict = {"at": -1.0, "by_symbol": {}}


def _coin_for(asset: str) -> dict:
    """The site's coin for a MEXC asset code (biggest by rank when tickers repeat), for its logo and page link."""
    if _coin_index["at"] != _UNIVERSE.get("at"):
        by_symbol: dict = {}
        for row in _UNIVERSE.get("rows") or []:
            sym = str(row.get("symbol") or "").upper()
            best = by_symbol.get(sym)
            rank = row.get("cmc_rank") or 10**9
            if best is None or rank < (best.get("cmc_rank") or 10**9):
                by_symbol[sym] = row
        _coin_index.update(at=_UNIVERSE.get("at"), by_symbol=by_symbol)
    return _coin_index["by_symbol"].get(asset.upper()) or {}


def _coin_fields(asset: str) -> dict[str, str]:
    row = _coin_for(asset)
    return {
        "name": str(row.get("name") or asset),
        "icon": str(row.get("icon_url") or ""),
        "href": f"/coins/{row['slug']}" if row.get("slug") else "",
        "initial": asset[:1],
    }


def _order_view(o: dict) -> dict[str, str]:
    buy = o["side"] == "BUY"
    return {
        **_coin_fields(o["asset"]),
        "asset": o["asset"],  # (MEXC's order id is deliberately not sent: the page never needs it)
        "pair": f"{o['asset']}/{o['quote'] or 'USDT'}",
        "side": "Buy" if buy else "Sell",
        "side_color": "green" if buy else "red",
        "type": o["type_label"],
        "price": _fmt_usd(o["price"]) if o["price"] else "Market",
        "trigger": _fmt_usd(o["stop_price"]) if o["stop_price"] else "",
        "amount": _qty(o["qty"]),
        "filled": f"{o['filled_pct']:.0f}%",
        "value": _money(o["value"]),
        "distance": (f"{abs(o['distance_pct']):.2f}% " + ("above" if o["distance_pct"] > 0 else "below")) if o["distance_pct"] else "",
        "placed": _when(o["time_ms"]),
    }


def _hist_view(
    rows: list, live_total: float = 0.0, now: float | None = None, currency: str = "USD", rate: float = 1.0
) -> tuple[list[dict], dict[str, str]]:
    """Recorded (unix seconds, total USD) points + the current live total as the last point -> recharts rows
    ({"t": label, "v": value}) and the range's figures (value, change, high, low), in `currency` (every USD amount
    times `rate`, the current USD -> currency rate, the same one the Total balance card uses)."""
    now = now or time.time()
    fx = _fx()
    pts = [(float(t), float(v) * rate) for t, v in rows]
    if live_total > 0 and (not pts or now - pts[-1][0] > 30):
        pts.append((now, float(live_total) * rate))
    data = [{"t": datetime.fromtimestamp(t, _TZ).strftime("%d %b %H:%M"), "v": round(v, 2)} for t, v in pts]
    if not pts:
        return data, {}
    first, last = pts[0][1], pts[-1][1]
    change = last - first
    info = {
        "value": fx.format_amount(last, currency),
        "change": fx.format_amount(change, currency, signed=True),
        "change_pct": _fmt_pct(change / first * 100) if first else "",
        "color": _color(change),
        "high": fx.format_amount(max(v for _, v in pts), currency),
        "low": fx.format_amount(min(v for _, v in pts), currency),
        "points": str(len(pts)),
    }
    return data, info


def _chart_lines(held: dict | None, orders: list[dict]) -> list[dict]:
    """Horizontal lines for the coin page lines chart: the average buy price (blue), every open limit order (green)
    and every stop / stop-loss order (red, dashed, at its trigger price).
    {"p": price, "c": colour, "t": label, "s": 0 solid / 2 dashed}."""
    lines = []
    if held and held.get("avg_price", 0) > 0:
        lines.append({"p": held["avg_price"], "c": _LINE_AVG, "t": "Avg buy", "s": 0})
    for o in orders:
        stop = o.get("stop_price") or 0
        price = stop or o.get("price") or 0
        if price <= 0:
            continue
        side = "Buy" if o.get("side") == "BUY" else "Sell"
        label = f"{side} {o.get('type_label') or 'order'}" + (" trigger" if stop else "")
        lines.append({"p": price, "c": _LINE_STOP if stop else _LINE_LIMIT, "t": label, "s": 2 if stop else 0})
    return lines


def _summary_view(snap: dict, currency: str = "USD", rate: float = 1.0) -> dict[str, str]:
    """The hero card's strings. Only the card's own money amounts are converted (`rate` = USD -> `currency`):
    total, 24h change, unrealized P/L, stablecoins, value in orders and the small-balances note. Percentages,
    counts and everything below the card (tables, order list, the unmatched-USDT note) stay in USD."""
    fx = _fx()

    def cur(v: float) -> str:
        return fx.format_amount(v * rate, currency)

    def cur_signed(v: float) -> str:
        return fx.format_amount(v * rate, currency, signed=True)

    total = snap["total_value"]
    updated = snap.get("updated_at") or 0
    cost_note = ""
    if snap["without_cost"]:
        n = snap["without_cost"]
        cost_note = f"{n} coin{'s' if n != 1 else ''} without a known buy price"
    return {
        "total": cur(total),
        "change": cur_signed(snap["change_24h"]),
        "change_pct": _fmt_pct(snap["change_24h_pct"]),
        "change_color": _color(snap["change_24h"]),
        "pnl": cur_signed(snap["pnl"]) if snap["with_cost"] else "—",
        "pnl_pct": _fmt_pct(snap["pnl_pct"]) if snap["cost_total"] else "",
        "pnl_color": _color(snap["pnl"]),
        "cost": _money(snap["cost_total"]),
        "cost_note": cost_note,
        "cash": cur(snap["stable_value"]),
        "cash_pct": f"{snap['stable_value'] / total * 100:.1f}% of wallet" if total else "",
        "in_orders": cur(snap["locked_value"]),
        "orders_count": str(len(snap["orders"])),
        "coins": str(sum(1 for h in snap["holdings"] if not h["is_stable"])),
        "updated": datetime.fromtimestamp(updated, _TZ).strftime("%H:%M:%S") if updated else "",
        "dust": f"+ {snap['dust_count']} small balance{'s' if snap['dust_count'] != 1 else ''} ({cur(snap['dust_value'])})" if snap["dust_count"] else "",
        "unmatched": (
            f"{_money(snap['unmatched_locked_usdt'])} USDT is held by buy orders on coins you don't hold: open that coin's page to see them."
            if snap["unmatched_locked_usdt"] >= 1
            else ""
        ),
    }


class PortfolioState(CoinState):
    pf_allowed: bool = False  # this account may see the MEXC data
    pf_loaded: bool = False
    pf_configured: bool = True
    pf_demo: bool = False
    pf_error: str = ""
    pf_refreshing: bool = False
    pf_currency: str = "USD"  # the hero card only: "USD" (default) or "MYR"
    pf_fx_note: str = ""  # "1 USD = 4.0824 MYR · <source>" while MYR is shown
    pf_fx_error: str = ""
    _pf_snap: dict = {}  # last raw snapshot (backend-only, emptied by _clear_portfolio)
    # Balance chart: the 7-day card under Allocation and the full-size popup (24H / 7D / 1M / Full Chart).
    pf_hist_card: list[dict] = []
    pf_hist_card_info: dict[str, str] = {}
    pf_hist_open: bool = False
    pf_hist_range: str = "full"
    pf_hist_points: list[dict] = []
    pf_hist_info: dict[str, str] = {}
    pf_hist_since: str = ""
    pf_hist_loading: bool = False
    _pf_hist_card_rows: list = []  # raw USD readings behind the card / popup (backend-only): a currency switch
    _pf_hist_popup_rows: list = []  # redraws from these without reading the database again
    pf_summary: dict[str, str] = {}
    pf_holdings: list[dict[str, str]] = []
    pf_orders: list[dict[str, str]] = []
    pf_trades: list[dict[str, str]] = []  # the CURRENT page of Recent fills only (5 rows)
    pf_trade_page: int = 1
    pf_trade_pages: int = 1
    pf_trade_total: int = 0
    _pf_trades_all: list[dict[str, str]] = []  # every formatted fill; backend-only, emptied by _clear_portfolio
    pf_alloc: list[dict[str, str]] = []
    pf_ring: str = ""  # CSS conic-gradient of the allocation ring
    # Hand-typed average buy price dialog.
    pf_cost_open: bool = False
    pf_cost_asset: str = ""
    pf_cost_input: str = ""
    pf_cost_error: str = ""
    _pf_running: bool = False

    # Coin page box (above Alerts).
    coin_mexc_visible: bool = False
    coin_mexc_loaded: bool = False
    coin_mexc_error: str = ""
    coin_mexc_holding: dict[str, str] = {}
    coin_mexc_orders: list[dict[str, str]] = []
    # Main chart area: the "My lines" view (Lightweight Charts) for coins with a MEXC holding / order.
    coin_mexc_candles: str = "[]"  # [[time s, open, high, low, close], ...] of <coin>USDT on MEXC
    coin_mexc_lines: str = "[]"  # avg buy (blue), limit (green), stop (red): see _chart_lines
    coin_mexc_has_lines: bool = False  # there are lines AND candles: the main chart offers the lines view
    coin_mexc_chart_mode: str = "lines"  # "lines" (default when available) or "tv" (the TradingView widget)
    coin_mexc_interval: str = "60m"
    _coin_mexc_running: bool = False

    # ------------------------------------------------------------------------------------------ dashboard

    def _apply(self, snap: dict) -> None:
        self.pf_configured = bool(snap.get("configured"))
        self.pf_demo = bool(snap.get("demo"))
        self.pf_error = snap.get("error") or ""
        if not snap.get("ok"):
            self.pf_loaded = True
            return
        total = snap["total_value"]  # (the allocation ring below needs it)
        self._pf_snap = snap  # raw numbers stay on the server: a currency change re-renders the card from them
        self.pf_summary = _summary_view(snap, *self._card_currency())
        holdings = []
        for h in snap["holdings"]:
            has_cost = h["avg_price"] > 0
            holdings.append(
                {
                    **_coin_fields(h["asset"]),
                    "asset": h["asset"],
                    "amount": _qty(h["amount"]),
                    "locked": f"{_qty(h['locked'])} in orders" if h["locked"] > 0 else "",
                    "price": _fmt_usd(h["price"]) if h["priced"] else "—",
                    "pct_24h": _fmt_pct(h["pct_24h"]) if not h["is_stable"] else "",
                    "pct_color": _color(h["pct_24h"]),
                    "value": _money(h["value"]),
                    "avg": _fmt_usd(h["avg_price"]) if has_cost else ("—" if not h["is_stable"] else ""),
                    "avg_source": "set by you" if h["avg_source"] == "manual" else "",
                    "avg_plain": _fmt_usd(h["avg_price"]).lstrip("$").replace(",", "") if has_cost else "",
                    "pnl": _signed_money(h["pnl"]) if has_cost else "",
                    "pnl_pct": _fmt_pct(h["pnl_pct"]) if has_cost else "",
                    "pnl_color": _color(h["pnl"]),
                    "alloc": f"{h['allocation_pct']:.1f}%",
                    "alloc_width": f"{max(h['allocation_pct'], 0.5):.1f}%",
                    "stable": "1" if h["is_stable"] else "",
                }
            )
        self.pf_holdings = holdings
        self.pf_orders = [_order_view(o) for o in snap["orders"]]
        self._pf_trades_all = [
            {
                **_coin_fields(t["asset"]),
                "asset": t["asset"],
                "side": "Buy" if t["side"] == "BUY" else "Sell",
                "side_color": "green" if t["side"] == "BUY" else "red",
                "price": _fmt_usd(t["price"]),
                "amount": _qty(t["qty"]),
                "value": _money(t["value"]),
                "fee": f"{_qty(t['fee'])} {t['fee_asset']}" if t["fee"] else "0",
                "time": _when(t["time_ms"]),
            }
            for t in snap["trades"]
        ]
        self._show_trades_page()
        # Allocation: the 6 biggest holdings + "Others".
        top = snap["holdings"][:6]
        rest = sum(h["allocation_pct"] for h in snap["holdings"][6:]) + (snap["dust_value"] / total * 100 if total else 0)
        alloc = [{"label": h["asset"], "pct": h["allocation_pct"], "color": _RING[i]} for i, h in enumerate(top)]
        if rest >= 0.05:
            alloc.append({"label": "Others", "pct": rest, "color": _RING_OTHER})
        stops, start = [], 0.0
        for a in alloc:
            end = min(start + a["pct"], 100.0)
            stops.append(f"{a['color']} {start:.2f}% {end:.2f}%")
            start = end
        self.pf_ring = f"conic-gradient({', '.join(stops)})" if stops else "conic-gradient(var(--gray-a4) 0 100%)"
        self.pf_alloc = [{"label": a["label"], "pct": f"{a['pct']:.1f}%", "color": a["color"]} for a in alloc]
        self.pf_loaded = True

    def _clear_portfolio(self, loaded: bool = False) -> None:
        """Empties everything MEXC put into this session's state: every pf_* / coin_mexc_* var goes back to its
        default (found by prefix, so a var added later is covered too). `loaded=True` keeps the /portfolio page
        out of its loading skeleton (it then shows "not available"); logout passes False."""
        for name, field in PortfolioState.get_fields().items():
            if name.startswith(_PORTFOLIO_VAR_PREFIXES):
                factory = field.default_factory  # None or MISSING for a plain default such as False / ""
                has_factory = factory is not None and factory is not dataclasses.MISSING
                setattr(self, name, factory() if has_factory else field.default)
        self._pf_trades_all = []  # backend-only raw rows are not covered by the prefix loop above
        self._pf_snap = {}
        self._pf_hist_card_rows, self._pf_hist_popup_rows = [], []
        self.pf_loaded = loaded

    def _show_trades_page(self) -> None:
        """Puts the current page of Recent fills into pf_trades (the page number is kept between refreshes and
        clamped when the list shrinks)."""
        total = len(self._pf_trades_all)
        pages = max(1, -(-total // _TRADES_PER_PAGE))
        self.pf_trade_page = min(max(self.pf_trade_page, 1), pages)
        start = (self.pf_trade_page - 1) * _TRADES_PER_PAGE
        self.pf_trades = self._pf_trades_all[start : start + _TRADES_PER_PAGE]
        self.pf_trade_pages, self.pf_trade_total = pages, total

    def _viewer_lost(self) -> bool:
        """True (after wiping this session's MEXC state) when the account may no longer see MEXC data: logged out,
        or another account is now in this tab. Call it while holding the state."""
        if self.is_logged_in and _svc().can_view(self.user_email):
            return False
        self._clear_portfolio(loaded=True)
        return True

    def _live_total(self) -> float:
        return float(self._pf_snap.get("total_value") or 0) if self._pf_snap.get("ok") else 0.0

    def _chart_currency(self) -> tuple[str, float]:
        """The MYR / USD choice for the balance chart, from the shared rate cache (no network, no side effects;
        _card_currency, run first by _apply, already falls back to USD when MYR has no rate)."""
        if self.pf_currency == "MYR":
            info = _fx().cached("MYR")
            if info:
                return "MYR", info["rate"]
        return "USD", 1.0

    def _apply_history(self, card_rows: list | None, popup_rows: list | None = None, since: float | None = None) -> None:
        """New readings (None = keep the ones already held) -> the card and popup, in the selected currency."""
        if card_rows is not None:
            self._pf_hist_card_rows = card_rows
        if popup_rows is not None:
            self._pf_hist_popup_rows = popup_rows
        currency, rate = self._chart_currency()
        live = self._live_total()
        self.pf_hist_card, self.pf_hist_card_info = _hist_view(self._pf_hist_card_rows, live, currency=currency, rate=rate)
        self.pf_hist_points, self.pf_hist_info = _hist_view(self._pf_hist_popup_rows, live, currency=currency, rate=rate)
        if since:
            self.pf_hist_since = datetime.fromtimestamp(since, _TZ).strftime("%d %b %Y, %H:%M")

    async def _load_popup(self, range_key: str):
        """Reads one range for the popup (shared 60 s cache) and shows it."""
        hist = _history()
        try:
            rows, since = await asyncio.gather(asyncio.to_thread(hist.series, range_key), asyncio.to_thread(hist.first_recorded))
        except Exception:  # noqa: BLE001
            _log.exception("Balance history could not be read")
            rows, since = [], None
        self._apply_history(None, rows, since)
        self.pf_hist_loading = False

    @rx.event
    async def open_balance_chart(self):
        """The balance card was clicked: the centred popup opens on the Full Chart."""
        if not (self.is_logged_in and _svc().can_view(self.user_email)):
            return
        self.pf_hist_open, self.pf_hist_range, self.pf_hist_loading = True, "full", True
        await self._load_popup("full")

    @rx.event
    def set_pf_hist_open(self, value: bool):
        self.pf_hist_open = value

    @rx.event
    async def set_pf_hist_range(self, range_key: str):
        if range_key not in _HIST_RANGES or not (self.is_logged_in and _svc().can_view(self.user_email)):
            return
        self.pf_hist_range, self.pf_hist_loading = range_key, True
        await self._load_popup(range_key)

    def _card_currency(self) -> tuple[str, float]:
        """(currency, USD -> currency rate) for the hero card from the shared rate cache (no network). Falls back to
        USD, and says why, when MYR is chosen but no usable rate exists."""
        if self.pf_currency != "MYR":
            self.pf_fx_note = self.pf_fx_error = ""
            return "USD", 1.0
        info = _fx().cached("MYR")
        if info is None:
            self.pf_currency, self.pf_fx_note = "USD", ""
            self.pf_fx_error = "The live MYR rate is unavailable right now, so the card shows USD."
            return "USD", 1.0
        self.pf_fx_error = ""
        self.pf_fx_note = f"1 USD = {info['rate']:.4f} MYR · {info['note']}"
        return "MYR", info["rate"]

    @rx.event
    async def set_pf_currency(self, currency: str):
        """The MYR / USD buttons on the hero card. They switch the Total balance card and the balance chart (card +
        popup). MYR fetches the live rate first; if no rate can be had everything stays in USD with a message."""
        if currency not in ("USD", "MYR") or not (self.is_logged_in and _svc().can_view(self.user_email)):
            return
        if currency == "MYR":
            info = await asyncio.to_thread(_fx().get_rate, "MYR")
            if info is None:
                self.pf_fx_error = "The live MYR rate is unavailable right now. Try again in a moment."
                return
        self.pf_currency = currency
        if self._pf_snap:
            self.pf_summary = _summary_view(self._pf_snap, *self._card_currency())
        else:
            self._card_currency()
        self._apply_history(None, None)  # the balance chart (card + popup) follows the same choice

    async def _snapshot(self, force: bool = False) -> dict:
        return await asyncio.to_thread(_svc().portfolio, self.user_id or None, force)

    async def _portfolio_cycle(self) -> bool:
        """One dashboard refresh. Returns False when the loop should stop (the viewer lost access, or the tab left
        the account area). Any other failure only shows a short message and keeps the last data on screen."""
        snap, error, card_rows, popup_rows = None, "", None, None
        async with self:
            wants_myr = self.pf_currency == "MYR"
            popup_range = self.pf_hist_range if self.pf_hist_open else ""
        try:
            if wants_myr:
                await asyncio.to_thread(_fx().get_rate, "MYR")  # cached for 60 s and shared; never raises
            snap = await self._snapshot()
        except Exception:  # noqa: BLE001 - network/database/bad reply: log the detail, keep the loop alive
            _log.exception("MEXC portfolio refresh failed")
            error = _REFRESH_FAILED
        try:  # the balance chart (database, cached 60 s); a failure only leaves the chart as it was
            card_rows = await asyncio.to_thread(_history().series, "7d")
            if popup_range:
                popup_rows = await asyncio.to_thread(_history().series, popup_range)
        except Exception:  # noqa: BLE001
            _log.exception("Balance history could not be read")
        async with self:
            if self._viewer_lost():  # logged out / another account in this tab
                return False
            if snap is not None:
                try:
                    self._apply(snap)
                except Exception:  # noqa: BLE001
                    _log.exception("MEXC portfolio could not be displayed")
                    error = _REFRESH_FAILED
            if error:
                self.pf_error, self.pf_loaded = error, True
            if self.pf_hist_range != popup_range and popup_range:
                popup_rows = None  # the range changed while reading: the click's own load wins
            self._apply_history(card_rows, popup_rows)
            # The account sidebar swaps Portfolio/Edit in the browser (no server navigation), so the loop keeps
            # going anywhere in the account area and stops when the tab leaves it.
            return self.router.url.path.rstrip("/") in _ACCOUNT_PATHS

    @rx.event(background=True)
    async def portfolio_loop(self):
        """Account-area on_load (/portfolio, /profile, /profile/edit-profile): redraws the dashboard every
        _PAGE_SECONDS while this tab is in the account area."""
        async with self:
            if self._viewer_lost():
                return
            self.pf_allowed = True
            if self._pf_running:
                return
            self._pf_running = True
        from frontend.frontend import app as reflex_app

        try:
            while True:
                if not await self._portfolio_cycle():
                    break
                await asyncio.sleep(_PAGE_SECONDS)
                if self.router.session.client_token not in reflex_app.event_namespace.token_to_sid:
                    break
        finally:
            async with self:
                self._pf_running = False

    @rx.event(background=True)
    async def refresh_portfolio(self):
        """The refresh icon: reads MEXC now instead of waiting for the next cycle. (After a MEXC rate-limit answer
        the service refuses to send anything until its pause ends, so this cannot skip that wait.)"""
        async with self:
            if not (self.is_logged_in and _svc().can_view(self.user_email)) or self.pf_refreshing:
                return
            self.pf_refreshing = True
        snap = None
        try:
            snap = await self._snapshot(force=True)
        except Exception:  # noqa: BLE001
            _log.exception("MEXC portfolio manual refresh failed")
        async with self:
            self.pf_refreshing = False
            if self._viewer_lost():  # logged out while MEXC was being read: keep nothing
                return
            if snap is None:
                self.pf_error, self.pf_loaded = _REFRESH_FAILED, True
                return
            try:
                self._apply(snap)
            except Exception:  # noqa: BLE001
                _log.exception("MEXC portfolio could not be displayed")
                self.pf_error = _REFRESH_FAILED

    def _go_trades_page(self, page: int) -> None:
        if not (self.is_logged_in and _svc().can_view(self.user_email)):
            return
        self.pf_trade_page = page
        self._show_trades_page()

    @rx.event
    def trades_first(self):
        self._go_trades_page(1)

    @rx.event
    def trades_prev(self):
        self._go_trades_page(self.pf_trade_page - 1)

    @rx.event
    def trades_next(self):
        self._go_trades_page(self.pf_trade_page + 1)

    @rx.event
    def trades_last(self):
        self._go_trades_page(self.pf_trade_pages)

    @rx.event
    def open_cost_dialog(self, asset: str, current: str):
        self.pf_cost_asset, self.pf_cost_input, self.pf_cost_error = asset, current, ""
        self.pf_cost_open = True

    @rx.event
    def set_pf_cost_open(self, value: bool):
        self.pf_cost_open = value

    @rx.event
    def set_pf_cost_input(self, value: str):
        self.pf_cost_input, self.pf_cost_error = value, ""

    async def _save_cost(self, price: float | None):
        if not (self.is_logged_in and self.user_id and _svc().can_view(self.user_email)):
            self.pf_cost_open = False
            return
        try:
            await asyncio.to_thread(_svc().set_cost, self.user_id, self.pf_cost_asset, price)
            snap = await self._snapshot()
        except Exception:  # noqa: BLE001
            _log.exception("MEXC average buy price could not be saved")
            self.pf_cost_error = "Could not save just now. Please try again."
            return
        self.pf_cost_open = False
        self._apply(snap)

    @rx.event
    async def save_cost(self):
        raw = self.pf_cost_input.strip().replace(",", "").lstrip("$")
        try:
            price = float(raw)
        except ValueError:
            price = 0.0
        if price <= 0:
            self.pf_cost_error = "Enter your average buy price, e.g. 1.25."
            return
        await self._save_cost(price)

    @rx.event
    async def clear_cost(self):
        await self._save_cost(None)

    # ----------------------------------------------------------------------------------------- coin page

    def _apply_coin(self, asset: str, snap: dict, orders: list[dict], candles: list | None = None) -> None:
        held = next((h for h in snap.get("holdings") or [] if h["asset"] == asset), None)
        lines = _chart_lines(held, orders)
        self.coin_mexc_candles = json.dumps(candles or [], separators=(",", ":"))
        self.coin_mexc_lines = json.dumps(lines, separators=(",", ":"))
        self.coin_mexc_has_lines = bool(lines) and bool(candles)
        self.coin_mexc_error = snap.get("error") or ""
        self.coin_mexc_orders = [_order_view(o) for o in orders]
        self.coin_mexc_holding = (
            {
                "amount": f"{_qty(held['amount'])} {asset}",
                "value": _money(held["value"]),
                "avg": _fmt_usd(held["avg_price"]) if held["avg_price"] > 0 else "—",
                "pnl": f"{_signed_money(held['pnl'])} ({_fmt_pct(held['pnl_pct'])})" if held["avg_price"] > 0 else "—",
                "pnl_color": _color(held["pnl"]) if held["avg_price"] > 0 else "var(--gray-11)",
            }
            if held
            else {}
        )
        self.coin_mexc_loaded = True

    async def _coin_mexc_cycle(self, shown: str | None) -> tuple[bool, str | None]:
        """One coin-box refresh: (keep going?, the coin now shown). Failures show a short message in the box."""
        async with self:
            coin = self.selected_coin
            asset = str(coin.get("symbol") or "").upper() if coin else ""
            on_page = self.router.url.path.startswith("/coins/")
            interval = self.coin_mexc_interval
            if asset != shown:
                self.coin_mexc_loaded, self.coin_mexc_orders, self.coin_mexc_holding = False, [], {}
                self.coin_mexc_candles, self.coin_mexc_lines, self.coin_mexc_has_lines = "[]", "[]", False
        if not on_page:
            return False, shown
        if not asset:
            return True, shown
        svc = _svc()
        snap, orders, candles = None, [], []
        try:
            snap, orders, candles = await asyncio.gather(
                self._snapshot(), asyncio.to_thread(svc.coin_orders, asset), asyncio.to_thread(svc.klines, asset, interval)
            )
        except Exception:  # noqa: BLE001 - network/database/bad reply: log the detail, keep the loop alive
            _log.exception("MEXC coin box refresh failed")
        async with self:
            if self._viewer_lost():
                return False, shown
            failed = snap is None
            if interval != self.coin_mexc_interval:  # the timeframe changed while reading: its own load wins
                candles = None
            if not failed:
                try:
                    self._apply_coin(asset, snap, orders, candles if candles is not None else json.loads(self.coin_mexc_candles))
                except Exception:  # noqa: BLE001
                    _log.exception("MEXC coin box could not be displayed")
                    failed = True
            if failed:  # keep what was shown, say why it may be stale
                self.coin_mexc_error, self.coin_mexc_loaded = _REFRESH_FAILED, True
        return True, asset

    @rx.event
    def set_coin_chart_mode(self, mode: str):
        """"My lines" / "TradingView" switch above the coin page chart."""
        if mode in ("lines", "tv") and self.is_logged_in and _svc().can_view(self.user_email):
            self.coin_mexc_chart_mode = mode

    @rx.event
    async def set_coin_chart_interval(self, interval: str):
        """A timeframe button of the lines view: loads that timeframe's candles straight away."""
        if interval not in _CHART_INTERVAL_SET or not (self.is_logged_in and _svc().can_view(self.user_email)):
            return
        self.coin_mexc_interval = interval
        coin = self.selected_coin
        asset = str(coin.get("symbol") or "").upper() if coin else ""
        if not asset:
            return
        try:
            candles = await asyncio.to_thread(_svc().klines, asset, interval)
        except Exception:  # noqa: BLE001
            _log.exception("MEXC candles could not be read")
            return
        self.coin_mexc_candles = json.dumps(candles, separators=(",", ":"))
        self.coin_mexc_has_lines = self.coin_mexc_lines != "[]" and bool(candles)

    @rx.event(background=True)
    async def coin_mexc_loop(self):
        """Coin page on_load: the viewer's MEXC holding and open orders for the page's coin, every _COIN_SECONDS
        (follows the coin when the tab moves to another coin page)."""
        async with self:
            if self._viewer_lost():
                return
            self.coin_mexc_visible = True
            if self._coin_mexc_running:
                return
            self._coin_mexc_running = True
            self.coin_mexc_loaded = False
        from frontend.frontend import app as reflex_app

        shown = None
        try:
            while True:
                keep_going, shown = await self._coin_mexc_cycle(shown)
                if not keep_going:
                    break
                await asyncio.sleep(_COIN_SECONDS)
                if self.router.session.client_token not in reflex_app.event_namespace.token_to_sid:
                    break
        finally:
            async with self:
                self._coin_mexc_running = False
