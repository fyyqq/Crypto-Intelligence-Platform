"""Hand-picked TradingView chart symbols per coin (coin page: the red report
icon next to "<Coin> Live Chart"). A saved choice is permanent until reset:
stored in Postgres (chart_symbol_overrides), loaded into the shared coin
list at build time, and checked first by coin_state._resolve_chart_symbol,
so it survives restarts, reloads and closed tabs and also drives the coin
page's 1-second live price."""

from __future__ import annotations

import re

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models.chart_symbol_override import ChartSymbolOverride

# "EXCHANGE:SYMBOL", as TradingView writes it: e.g. "BINANCE:BTCUSDT",
# "KCEX:CYBERLEEKUSDT", "UNISWAP4BASE:CYBERLEEKETH_3BCAF5.USD".
_SYMBOL_RE = re.compile(r"^[A-Z0-9_]{2,30}:[A-Z0-9_.!\-]{2,80}$")


class ChartOverrideError(ValueError):
    pass


def normalize(symbol: str) -> str:
    """Upper-cased, trimmed "EXCHANGE:SYMBOL", or ChartOverrideError."""
    value = (symbol or "").strip().upper().replace(" ", "")
    if not _SYMBOL_RE.match(value):
        raise ChartOverrideError('Use the TradingView form "EXCHANGE:SYMBOL", e.g. BINANCE:BTCUSDT.')
    return value


def all_overrides() -> dict[int, str]:
    db = SessionLocal()
    try:
        return {cmc_id: symbol for cmc_id, symbol in db.execute(select(ChartSymbolOverride.cmc_id, ChartSymbolOverride.symbol))}
    finally:
        db.close()


def set_override(cmc_id: int, symbol: str, user_id: int | None = None) -> str:
    value = normalize(symbol)
    db = SessionLocal()
    try:
        row = db.get(ChartSymbolOverride, cmc_id)
        if row is None:
            db.add(ChartSymbolOverride(cmc_id=cmc_id, symbol=value, updated_by=user_id))
        else:
            row.symbol, row.updated_by = value, user_id
        db.commit()
        return value
    finally:
        db.close()


def clear_override(cmc_id: int) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(ChartSymbolOverride).where(ChartSymbolOverride.cmc_id == cmc_id))
        db.commit()
    finally:
        db.close()


def search_options(query: str, limit: int = 30) -> list[dict]:
    """TradingView's own listings for a ticker/name, for the picker: real spot
    markets only (no perpetuals, no synthetic/index rows), each labelled CEX
    or DEX. [] when TradingView can't be reached."""
    from app.services import tradingview_symbol_service as tv

    query = (query or "").strip()
    if not query:
        return []
    rows = tv._search_tradingview(query) or []
    out: list[dict] = []
    seen: set[str] = set()
    for s in rows:
        if s.get("type") != "spot":
            continue
        typespecs = set(s.get("typespecs") or [])
        if typespecs & {"synthetic", "index"} or "discontinued" in typespecs:
            continue
        prefix = (s.get("prefix") or s.get("exchange") or "").upper().replace(" ", "")
        symbol = tv._EM_TAG_RE.sub("", s.get("symbol", "")).upper()
        full = f"{prefix}:{symbol}"
        if not prefix or full in seen or not _SYMBOL_RE.match(full):
            continue
        seen.add(full)
        out.append(
            {
                "symbol": full,
                "exchange": s.get("exchange", "") or prefix,
                "description": tv._EM_TAG_RE.sub("", s.get("description", "")),
                "kind": "DEX" if tv._is_dex_listing(s) else "CEX",
            }
        )
        if len(out) >= limit:
            break
    out.sort(key=lambda o: o["kind"] != "CEX")  # CEX first, TradingView's own order within each
    return out
