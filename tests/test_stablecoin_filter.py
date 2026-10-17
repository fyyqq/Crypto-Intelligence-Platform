"""Stablecoins never fill the Gainers & Losers boards, in any window, rank band or saved day; protocol tokens that
merely carry a "Stablecoin" tag keep moving freely."""

from datetime import datetime, timedelta

import pytest

from app.models.category import Category
from app.models.coin import Coin
from app.models.movers_daily import MoversDaily
from app.models.price_snapshot import PriceSnapshot
from app.services import price_snapshot_service as svc

NOW = datetime(2026, 10, 5, 12, 0, 0)


@pytest.fixture(autouse=True)
def _fresh_tag_cache():
    svc._stable_cache.update(at=0.0, ids=frozenset())


def row(coin_id, symbol, name, price, pct, rank=50):
    return {"coin_id": coin_id, "symbol": symbol, "name": name, "rank": rank, "price_now": price, "price_then": price / (1 + pct / 100),
            "pct_change": pct, "volume_24h": 1e8, "then_at": NOW, "now_at": NOW}


def test_pegged_tagged_coins_are_stablecoins_but_tagged_protocol_tokens_are_not():
    tagged = {1, 2, 3, 4, 5}
    assert svc.is_stablecoin(row(1, "USDT", "Tether", 0.999, -0.02), tagged)
    assert svc.is_stablecoin(row(2, "EURC", "EURC", 1.118, 0.0), tagged)  # euro peg
    assert svc.is_stablecoin(row(3, "USDY", "Ondo US Dollar Yield", 1.151, 0.2), tagged)  # yield-bearing, drifts up
    assert svc.is_stablecoin(row(4, "CUSD", "cUSD", 0.95, -4.9), tagged)  # a depeg is still a stablecoin
    assert not svc.is_stablecoin(row(5, "XPL", "Plasma", 0.08, 14.0), tagged)  # tagged, but a normal token far from $1


def test_untagged_dollar_lookalikes_need_the_price_the_name_and_a_tiny_move():
    assert svc.is_stablecoin(row(10, "USX", "Solstice USX", 0.9994, 0.01))
    assert svc.is_stablecoin(row(11, "USDon", "U.S. Dollar Tokenized Currency (Ondo)", 0.9994, -0.1))
    assert not svc.is_stablecoin(row(12, "SUI", "Sui", 1.0098, 1.2))  # near $1 but no stablecoin look
    assert not svc.is_stablecoin(row(13, "BP", "Backpack", 0.9876, -0.5))
    assert not svc.is_stablecoin(row(14, "USX", "Solstice USX", 0.9994, 6.0))  # moved 6%: a real mover, not a peg
    assert not svc.is_stablecoin(row(15, "USDX", "Some dollar coin", 0.5, 0.0))  # far from $1


def test_boards_skip_stablecoins_in_every_band_and_direction_but_keep_the_rest():
    changes = [
        {**row(1, "USDC", "USDC", 1.001, 0.05, rank=6), "stable": True},
        {**row(2, "USD1", "USD1", 1.0, -0.01, rank=26), "stable": True},
        row(3, "SOL", "Solana", 100.0, 2.0, rank=7),
        row(4, "ETH", "Ethereum", 2000.0, -1.0, rank=2),
        {**row(5, "FRAX", "Frax", 0.99, 0.2, rank=150), "stable": True},
    ]
    assert [c["symbol"] for c in svc.rank_movers(changes, 100, "gainers")] == ["SOL"]
    assert [c["symbol"] for c in svc.rank_movers(changes, 100, "losers")] == ["ETH"]
    assert svc.rank_movers(changes, 200, "gainers") == []
    rows = svc.board_rows(changes, 100, "losers", 30, {1})  # a held stablecoin is no longer marked or listed
    assert [r["coin"]["symbol"] for r in rows] == ["ETH"]


def test_the_database_tags_drive_compute_changes_and_saved_days(db):
    from app.models.category import coin_category  # noqa: F401  (table must exist)

    stable_cat = Category(cmc_category_id="s1", name="USD Stablecoin", slug="usd-stablecoin")
    other = Category(cmc_category_id="s2", name="Layer 1", slug="layer-1")
    dai = Coin(cmc_id=1, symbol="DAI", name="Dai", slug="dai")
    dai.categories.append(stable_cat)
    xpl = Coin(cmc_id=2, symbol="XPL", name="Plasma", slug="plasma")
    xpl.categories.extend([stable_cat, other])
    db.add_all([dai, xpl])
    for cid, sym, then, now in ((1, "DAI", 1.0, 0.999), (2, "XPL", 0.07, 0.08)):
        db.add(PriceSnapshot(coin_id=cid, symbol=sym, price_usd=then, cmc_rank=cid * 10, volume_24h=1e8, synced_at=NOW - timedelta(hours=24)))
        db.add(PriceSnapshot(coin_id=cid, symbol=sym, price_usd=now, cmc_rank=cid * 10, volume_24h=1e8, synced_at=NOW))
    db.add(PriceSnapshot(coin_id=999999, symbol="OLD", price_usd=1.0, cmc_rank=9999, volume_24h=1e8, synced_at=NOW - timedelta(days=40)))
    db.commit()

    changes = svc.compute_changes(db, "24h")
    assert {c["symbol"]: c["stable"] for c in changes} == {"DAI": True, "XPL": False}
    assert [c["symbol"] for c in svc.get_movers(db, 100, "24h", "losers")["coins"]] == []  # DAI -0.1% is not a loser
    assert [c["symbol"] for c in svc.get_movers(db, 100, "24h", "gainers")["coins"]] == ["XPL"]

    # A day saved before the filter existed holds DAI; loading it flags it, so its board still skips it.
    db.add(MoversDaily(day=NOW.date(), window="24h", coin_id=1, cmc_rank=10, name="Dai", symbol="DAI", price_now=0.999, price_then=1.0,
                       pct_change=-0.1, volume_24h=1e8, then_at=NOW - timedelta(hours=24), now_at=NOW))
    db.commit()
    saved = svc.load_daily_movers(db, NOW.date())["24h"]
    assert saved[0]["stable"] is True and svc.rank_movers(saved, 100, "losers") == []
