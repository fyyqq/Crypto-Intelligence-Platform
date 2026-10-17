"""The boards re-price "now" from live sources between the hourly snapshots: the exchange list first, then the stored
price, then the snapshot's own; the % change and the order follow; a forced refresh is rate limited."""

from datetime import datetime, timedelta

import pytest

from app.models.coin import Coin
from app.models.price_snapshot import PriceSnapshot
from app.services import price_hub
from app.services import price_snapshot_service as svc

NOW = datetime(2026, 10, 5, 12, 0, 0)


def snap(db, coin_id, symbol, price, at, rank=10):
    db.add(PriceSnapshot(coin_id=coin_id, symbol=symbol, price_usd=price, cmc_rank=rank, volume_24h=1e8, synced_at=at))


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    svc._live_cache.update(at=0.0, forced_at=0.0, prices={})
    monkeypatch.setattr(svc, "_utcnow", lambda: NOW + timedelta(minutes=10))


def seed(db):
    snap(db, 999999, "OLD", 1.0, NOW - timedelta(days=40), rank=9999)
    for cid, sym, then, now in ((1, "AAA", 100.0, 110.0), (2, "BBB", 10.0, 9.0), (3, "CCC", 5.0, 5.0), (4, "DDD", 1.0, 1.0)):
        snap(db, cid, sym, then, NOW - timedelta(hours=24), rank=cid)
        snap(db, cid, sym, now, NOW, rank=cid)
    db.add(Coin(cmc_id=3, symbol="CCC", name="CCC", slug="ccc", price_usd=5.5))  # stored price moved (the 5-minute refresh)
    db.add(Coin(cmc_id=4, symbol="DDD", name="DDD", slug="ddd", price_usd=500.0))  # absurd stored price: ignored
    db.commit()


def test_live_price_sources_in_order_and_sanity_checks(db, monkeypatch):
    seed(db)
    quotes = {"AAA": {"price": 120.0}, "BBB": {"price": 1000.0}}  # BBB's quote is 100x off: another coin with that ticker
    monkeypatch.setattr(price_hub, "get_prices", lambda max_age=30: quotes)
    prices, at = svc.live_prices(db)
    assert prices[1] == 120.0  # exchange list
    assert prices[2] == 9.0  # implausible quote and no stored price: the snapshot's own
    assert prices[3] == 5.5  # no quote: the stored price
    assert prices[4] == 1.0  # absurd stored price rejected
    assert at > 0


def test_a_stale_latest_snapshot_is_never_mixed_with_a_live_price(db, monkeypatch):
    seed(db)
    monkeypatch.setattr(price_hub, "get_prices", lambda max_age=30: {"AAA": {"price": 120.0}})
    monkeypatch.setattr(svc, "_utcnow", lambda: NOW + timedelta(hours=4))
    assert svc.live_prices(db)[0] == {}
    monkeypatch.setattr(svc, "_utcnow", lambda: NOW + timedelta(hours=2))
    svc._live_cache.update(at=0.0)
    assert svc.live_prices(db)[0][1] == 120.0


def test_a_failing_exchange_list_falls_back_without_raising(db, monkeypatch):
    seed(db)

    def boom(max_age=30):
        raise RuntimeError("exchanges down")

    monkeypatch.setattr(price_hub, "get_prices", boom)
    prices, _ = svc.live_prices(db)
    assert prices[1] == 110.0 and prices[3] == 5.5


def test_boards_follow_the_live_price_and_order(db, monkeypatch):
    seed(db)
    monkeypatch.setattr(price_hub, "get_prices", lambda max_age=30: {"AAA": {"price": 90.0}, "BBB": {"price": 12.0}})
    live, _ = svc.live_prices(db)
    changes = svc.apply_live(svc.compute_changes(db, "24h"), live)
    by = {c["symbol"]: c for c in changes}
    assert by["AAA"]["price_now"] == 90.0 and by["AAA"]["pct_change"] == pytest.approx(-10.0)  # was +10% on the snapshot
    assert by["BBB"]["pct_change"] == pytest.approx(20.0) and by["BBB"]["price_then"] == 10.0
    assert [c["symbol"] for c in svc.rank_movers(changes, 100, "gainers")] == ["BBB", "CCC"]
    assert [c["symbol"] for c in svc.rank_movers(changes, 100, "losers")] == ["AAA"]
    assert svc.apply_live(changes, None) is changes and svc.apply_live(changes, {}) is changes


def test_results_are_shared_for_30_seconds_and_a_forced_refresh_is_rate_limited(db, monkeypatch):
    seed(db)
    reads = []
    refreshes = []
    monkeypatch.setattr(price_hub, "get_prices", lambda max_age=30: reads.append(1) or {"AAA": {"price": 120.0 + len(reads)}})
    monkeypatch.setattr(price_hub, "refresh", lambda: refreshes.append(1))
    first, _ = svc.live_prices(db)
    again, _ = svc.live_prices(db)
    assert again is first and len(reads) == 1  # cached: a second viewer costs nothing
    forced, _ = svc.live_prices(db, force=True)
    assert len(refreshes) == 1 and len(reads) == 2 and forced[1] != first[1]  # the refresh icon re-reads the exchanges
    svc.live_prices(db, force=True)
    assert len(refreshes) == 1  # a second click within 10 s reuses the fresh copy
    svc._live_cache["forced_at"] -= svc.FORCE_MIN_GAP + 1
    svc._live_cache["at"] -= 1
    svc.live_prices(db, force=True)
    assert len(refreshes) == 2
