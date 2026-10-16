"""Coin information (market cap, FDV, Vol/Mkt Cap, locked-supply value,
Liq/Mkt Cap) re-based on a live price.

The stored figures come from the hourly CoinMarketCap sync, so they go stale
(or freeze entirely while CMC is out of credits) and for a coin whose real
price has moved (e.g. a memecoin priced on a DEX) the market cap shown next
to the live chart price was simply wrong. The supply behind every figure
does not change, so each one is the stored figure scaled by live/stored
price: market cap = circulating supply x price.
"""

from __future__ import annotations


def _compact_usd(value: float) -> str:
    """Same compact style as the page's own figures ($1.86M, $769.64K)."""
    sign = "-" if value < 0 else ""
    v = abs(value)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= limit:
            return f"{sign}${v / limit:,.2f}{suffix}"
    return f"{sign}${v:,.2f}"


def scaled_info(stored: dict, live_price: float, liquidity_usd: float | None = None) -> dict:
    """Row fields to patch, given a coin's STORED row and a live USD price.

    `stored` needs price_raw, market_cap_usd, volume_raw and optionally
    fdv_raw / locked_supply_raw. {} when the live price can't be related to
    the stored one (no stored price or market cap)."""
    ref = float(stored.get("price_raw") or 0)
    market_cap = float(stored.get("market_cap_usd") or 0)
    if live_price <= 0 or ref <= 0 or market_cap <= 0:
        return {}
    # A stored price below $0.000001 is rounded (8 decimals): its ratio to a live price is meaningless and would
    # multiply the market cap by millions, so those coins keep their stored cap and FDV.
    ratio = live_price / ref if ref >= 1e-6 else 1.0
    new_cap = market_cap * ratio
    out = {
        "market_cap_usd": new_cap,
        "market_cap_display": _compact_usd(new_cap),
    }
    volume = float(stored.get("volume_raw") or 0)
    if volume > 0:
        out["vol_mkt_cap_display"] = f"{volume / new_cap * 100:.2f}%"
    fdv = float(stored.get("fdv_raw") or 0)
    if fdv > 0:
        out["fdv_display"] = _compact_usd(fdv * ratio)
    locked = float(stored.get("locked_supply_raw") or 0)
    if locked > 0:
        out["locked_supply_value_display"] = _compact_usd(locked * live_price)
    if liquidity_usd and liquidity_usd > 0:
        out["liq_mkt_cap_display"] = f"{liquidity_usd / new_cap * 100:.2f}%"
    return out
