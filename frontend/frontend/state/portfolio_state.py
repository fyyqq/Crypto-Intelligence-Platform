"""State of the MEXC portfolio: the /portfolio dashboard and the coin page's "Your MEXC" box (above Alerts).

Read-only (app/services/mexc_service.py). Only an account listed in MEXC_VIEWER_EMAILS gets any data: every
loop and event checks mexc_service.can_view(user_email) on the server. The browser only receives formatted
strings; the key, the secret and the raw MEXC replies stay on the server."""

import asyncio
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import reflex as rx

from frontend.state.coin_state import _ROOT_FOR_APP, _UNIVERSE, CoinState, _fmt_pct, _fmt_usd

_TZ = ZoneInfo("Asia/Kuala_Lumpur")
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


def _money(v: float) -> str:
    """A USD amount (a value, not a coin price: coin prices go through _fmt_usd)."""
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def _signed_money(v: float) -> str:
    return ("+" if v > 0 else "-" if v < 0 else "") + f"${abs(v):,.2f}"


def _color(v: float) -> str:
    return "var(--green-11)" if v > 0 else "var(--red-11)" if v < 0 else "var(--gray-11)"


def _qty(v: float) -> str:
    """A coin amount: thousands separators, up to 8 decimals for small amounts, no trailing zeros."""
    if v >= 1000:
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    if v >= 1:
        return f"{v:,.4f}".rstrip("0").rstrip(".")
    return f"{v:.8f}".rstrip("0").rstrip(".") or "0"


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
        "id": o["order_id"],
        "asset": o["asset"],
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


class PortfolioState(CoinState):
    pf_allowed: bool = False  # this account may see the MEXC data
    pf_loaded: bool = False
    pf_configured: bool = True
    pf_demo: bool = False
    pf_error: str = ""
    pf_refreshing: bool = False
    pf_summary: dict[str, str] = {}
    pf_holdings: list[dict[str, str]] = []
    pf_orders: list[dict[str, str]] = []
    pf_trades: list[dict[str, str]] = []
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
    _coin_mexc_running: bool = False

    # ------------------------------------------------------------------------------------------ dashboard

    def _apply(self, snap: dict) -> None:
        self.pf_configured = bool(snap.get("configured"))
        self.pf_demo = bool(snap.get("demo"))
        self.pf_error = snap.get("error") or ""
        if not snap.get("ok"):
            self.pf_loaded = True
            return
        total = snap["total_value"]
        updated = snap.get("updated_at") or 0
        cost_note = ""
        if snap["without_cost"]:
            n = snap["without_cost"]
            cost_note = f"{n} coin{'s' if n != 1 else ''} without a buy price (set it with the pencil)"
        self.pf_summary = {
            "total": _money(total),
            "change": _signed_money(snap["change_24h"]),
            "change_pct": _fmt_pct(snap["change_24h_pct"]),
            "change_color": _color(snap["change_24h"]),
            "pnl": _signed_money(snap["pnl"]) if snap["with_cost"] else "—",
            "pnl_pct": _fmt_pct(snap["pnl_pct"]) if snap["cost_total"] else "",
            "pnl_color": _color(snap["pnl"]),
            "cost": _money(snap["cost_total"]),
            "cost_note": cost_note,
            "cash": _money(snap["stable_value"]),
            "cash_pct": f"{snap['stable_value'] / total * 100:.1f}% of wallet" if total else "",
            "in_orders": _money(snap["locked_value"]),
            "orders_count": str(len(snap["orders"])),
            "coins": str(sum(1 for h in snap["holdings"] if not h["is_stable"])),
            "updated": datetime.fromtimestamp(updated, _TZ).strftime("%H:%M:%S") if updated else "",
            "dust": f"+ {snap['dust_count']} small balance{'s' if snap['dust_count'] != 1 else ''} ({_money(snap['dust_value'])})" if snap["dust_count"] else "",
            "unmatched": (
                f"{_money(snap['unmatched_locked_usdt'])} USDT is held by buy orders on coins you don't hold: open that coin's page to see them."
                if snap["unmatched_locked_usdt"] >= 1
                else ""
            ),
        }
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
        self.pf_trades = [
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

    async def _snapshot(self, force: bool = False) -> dict:
        return await asyncio.to_thread(_svc().portfolio, self.user_id or None, force)

    @rx.event(background=True)
    async def portfolio_loop(self):
        """Account-area on_load (/portfolio, /profile, /profile/edit-profile): redraws the dashboard every
        _PAGE_SECONDS while this tab is in the account area."""
        async with self:
            self.pf_allowed = bool(self.is_logged_in and _svc().can_view(self.user_email))
            if not self.pf_allowed:
                self.pf_loaded = True
                return
            if self._pf_running:
                return
            self._pf_running = True
        from frontend.frontend import app as reflex_app

        try:
            while True:
                snap = await self._snapshot()
                async with self:
                    if not _svc().can_view(self.user_email):  # logged out / another account in this tab
                        self.pf_allowed = False
                        break
                    self._apply(snap)
                    # The account sidebar swaps Portfolio/Edit in the browser (no server navigation), so the loop
                    # keeps going anywhere in the account area and stops when the tab leaves it.
                    on_page = self.router.url.path.rstrip("/") in _ACCOUNT_PATHS
                if not on_page:
                    break
                await asyncio.sleep(_PAGE_SECONDS)
                if self.router.session.client_token not in reflex_app.event_namespace.token_to_sid:
                    break
        finally:
            async with self:
                self._pf_running = False

    @rx.event(background=True)
    async def refresh_portfolio(self):
        """The refresh icon: reads MEXC now instead of waiting for the next cycle."""
        async with self:
            if not (self.is_logged_in and _svc().can_view(self.user_email)) or self.pf_refreshing:
                return
            self.pf_refreshing = True
        try:
            snap = await self._snapshot(force=True)
            async with self:
                self._apply(snap)
        finally:
            async with self:
                self.pf_refreshing = False

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
        await asyncio.to_thread(_svc().set_cost, self.user_id, self.pf_cost_asset, price)
        self.pf_cost_open = False
        self._apply(await self._snapshot())

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

    @rx.event(background=True)
    async def coin_mexc_loop(self):
        """Coin page on_load: the viewer's MEXC holding and open orders for the page's coin, every _COIN_SECONDS
        (follows the coin when the tab moves to another coin page)."""
        async with self:
            allowed = bool(self.is_logged_in and _svc().can_view(self.user_email))
            self.coin_mexc_visible = allowed
            if not allowed or self._coin_mexc_running:
                return
            self._coin_mexc_running = True
            self.coin_mexc_loaded = False
        from frontend.frontend import app as reflex_app

        shown = None
        try:
            while True:
                async with self:
                    coin = self.selected_coin
                    asset = str(coin.get("symbol") or "").upper() if coin else ""
                    on_page = self.router.url.path.startswith("/coins/")
                    if asset != shown:
                        self.coin_mexc_loaded, self.coin_mexc_orders, self.coin_mexc_holding = False, [], {}
                if not on_page:
                    break
                if asset:
                    svc = _svc()
                    snap, orders = await asyncio.gather(self._snapshot(), asyncio.to_thread(svc.coin_orders, asset))
                    held = next((h for h in snap.get("holdings") or [] if h["asset"] == asset), None)
                    async with self:
                        if not svc.can_view(self.user_email):
                            self.coin_mexc_visible = False
                            break
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
                    shown = asset
                await asyncio.sleep(_COIN_SECONDS)
                if self.router.session.client_token not in reflex_app.event_namespace.token_to_sid:
                    break
        finally:
            async with self:
                self._coin_mexc_running = False
