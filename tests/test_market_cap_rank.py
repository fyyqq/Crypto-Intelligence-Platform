"""The homepage list follows CoinMarketCap's own rank, and a rounding-artifact market cap can never rank a coin
above Bitcoin (2026-10-16: Jesus Coin / Bitgert showed 10^20 dollars)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "frontend"))

from frontend.state.coin_state import _rank_order, _sane_market_cap  # noqa: E402


def test_a_cap_far_above_price_times_supply_is_replaced():
    assert _sane_market_cap(9e21, 1e-8, 1.5e14) == 1e-8 * 1.5e14  # Jesus Coin
    assert _sane_market_cap(1.77e11, 1e-8, 2.1e15) == 1e-8 * 2.1e15  # SATS
    assert _sane_market_cap(1.65e12, 82000, 19.9e6) == 1.65e12  # Bitcoin is untouched
    assert _sane_market_cap(342_582, 0.00176, 8.8e13) == 342_582  # CMC's own LOWER cap is kept


def test_a_huge_cap_with_nothing_to_check_it_against_is_dropped():
    assert _sane_market_cap(9e18, 5, 0) == 0.0
    assert _sane_market_cap(9e18, 0, 1e9) == 0.0
    assert _sane_market_cap(None, None, None) == 0.0


def test_the_list_is_in_cmc_rank_order_whatever_the_market_cap_says():
    rows = [
        {"cmc_id": 3, "cmc_rank": 1584, "market_cap_usd": 9e21},  # fake cap, rank 1584
        {"cmc_id": 1, "cmc_rank": 1, "market_cap_usd": 1.6e12},
        {"cmc_id": 4, "cmc_rank": 0, "market_cap_usd": 5e9},  # CMC has not ranked it: after every ranked coin
        {"cmc_id": 2, "cmc_rank": 2, "market_cap_usd": 3e11},
        {"cmc_id": 5, "cmc_rank": 0, "market_cap_usd": 9e9},
    ]
    assert [r["cmc_id"] for r in sorted(rows, key=_rank_order)] == [1, 2, 3, 5, 4]
