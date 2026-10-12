"""Guards that keep CoinMarketCap credit use inside the monthly plan: the
view-driven sync skips recently refreshed coins, a failing sync backs off,
and a re-used CMC slug no longer fails the daily sync. Fake CMC client only."""

from datetime import datetime, timedelta

from app.models.coin import Coin
from app.models.sync_log import SyncLog, SyncStatus, SyncType
from app.services.market_data_service import VIEW_SYNC_MIN_AGE, MarketDataService
from tests.conftest import fake_listing


class FakeClient:
    def __init__(self, listings=None):
        self.listings = listings or []
        self.quote_calls: list[list[int]] = []

    def get_quotes_by_ids(self, ids):
        self.quote_calls.append(list(ids))
        return [fake_listing(i, f"C{i}", 2.0, i) for i in ids]

    def get_all_listings(self):
        return self.listings


def add_coin(db, cmc_id, slug, synced_ago=None):
    db.add(Coin(
        cmc_id=cmc_id, symbol=f"C{cmc_id}", name=f"C{cmc_id}", slug=slug,
        last_synced_at=None if synced_ago is None else datetime.utcnow() - synced_ago,
    ))


def test_view_sync_only_requests_stale_coins(db):
    add_coin(db, 1, "c1", synced_ago=timedelta(minutes=1))  # fresh: skipped
    add_coin(db, 2, "c2", synced_ago=VIEW_SYNC_MIN_AGE + timedelta(minutes=1))  # stale
    add_coin(db, 3, "c3")  # never synced
    db.commit()
    client = FakeClient()
    log = MarketDataService(db, client).sync_ids([1, 2, 3])
    assert log.status == SyncStatus.SUCCESS and client.quote_calls == [[2, 3]]


def test_view_sync_with_everything_fresh_calls_nothing_and_logs_nothing(db):
    add_coin(db, 1, "c1", synced_ago=timedelta(minutes=2))
    db.commit()
    client = FakeClient()
    log = MarketDataService(db, client).sync_ids([1])
    assert log.status == SyncStatus.SUCCESS and client.quote_calls == []
    assert db.query(SyncLog).count() == 0


def test_recent_failure_backs_off(db):
    svc = MarketDataService(db, FakeClient())
    db.add(SyncLog(sync_type=SyncType.LISTINGS, status=SyncStatus.FAILED, started_at=datetime.utcnow() - timedelta(minutes=30)))
    db.commit()
    assert svc.is_sync_due(SyncType.LISTINGS) is True  # old behaviour: retries at once
    assert svc.is_sync_due(SyncType.LISTINGS, failure_backoff_hours=2) is False
    db.query(SyncLog).update({"started_at": datetime.utcnow() - timedelta(hours=3)})
    db.commit()
    assert svc.is_sync_due(SyncType.LISTINGS, failure_backoff_hours=2) is True


def test_reused_slug_no_longer_fails_the_daily_sync(db):
    add_coin(db, 100, "catcoin")  # old row still holding the slug
    db.commit()
    new = fake_listing(200, "CAT", 1.0, 300)
    new["slug"] = "catcoin"
    log = MarketDataService(db, FakeClient([new])).sync_listings()
    assert log.status == SyncStatus.SUCCESS, log.error_message
    slugs = {c.cmc_id: c.slug for c in db.query(Coin).all()}
    assert slugs == {100: "catcoin~100", 200: "catcoin"}


def test_swapped_slugs_both_resolve(db):
    add_coin(db, 1, "alpha")
    add_coin(db, 2, "beta")
    db.commit()
    a, b = fake_listing(1, "A", 1.0, 1), fake_listing(2, "B", 1.0, 2)
    a["slug"], b["slug"] = "beta", "alpha"
    log = MarketDataService(db, FakeClient([a, b])).sync_listings()
    assert log.status == SyncStatus.SUCCESS, log.error_message
    assert {c.cmc_id: c.slug for c in db.query(Coin).all()} == {1: "beta", 2: "alpha"}
