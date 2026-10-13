"""Coin information re-based on a live price (CyberLeek: stored CMC price
$0.001054 vs a live $0.002554 made its market cap read $769K instead of
$1.86M)."""

import pytest

from app.services.coin_info import scaled_info

CYBERLEEK = {
    "price_raw": 0.00105432,
    "market_cap_usd": 769_641.74,
    "volume_raw": 1_003_069.55,
    "fdv_raw": 769_641.74,
    "locked_supply_raw": 0.0,
}


def test_market_cap_follows_the_live_price():
    out = scaled_info(CYBERLEEK, 0.002554, liquidity_usd=632_634.5)
    assert out["market_cap_usd"] == pytest.approx(769_641.74 * 0.002554 / 0.00105432)  # = supply x price
    assert out["market_cap_display"] == "$1.86M"
    assert out["fdv_display"] == "$1.86M"
    assert out["vol_mkt_cap_display"] == "53.80%"  # volume does not change; mcap did
    assert out["liq_mkt_cap_display"] == "33.93%"
    assert "locked_supply_value_display" not in out  # no locked supply


def test_locked_supply_value_uses_the_live_price():
    out = scaled_info({**CYBERLEEK, "locked_supply_raw": 1_000_000.0}, 0.5)
    assert out["locked_supply_value_display"] == "$500.00K"


def test_unrelatable_prices_change_nothing():
    assert scaled_info({**CYBERLEEK, "price_raw": 0}, 0.002) == {}
    assert scaled_info({**CYBERLEEK, "market_cap_usd": 0}, 0.002) == {}
    assert scaled_info(CYBERLEEK, 0) == {}


def test_no_liquidity_leaves_that_row_alone():
    assert "liq_mkt_cap_display" not in scaled_info(CYBERLEEK, 0.002554)
