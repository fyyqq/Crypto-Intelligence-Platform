"""Step 1: the price_snapshot table and the sync hook (fake data only)."""

from datetime import datetime

from sqlalchemy import func, select

from app.models.coin import Coin
from app.models.price_snapshot import PriceSnapshot
from app.services.market_data_service import MarketDataService
from app.services.price_snapshot_service import record_snapshots
from tests.conftest import fake_listing


def _rows(db):
    return db.scalars(select(PriceSnapshot).order_by(PriceSnapshot.id)).all()


def test_one_row_per_coin_with_the_right_fields(db):
    t = datetime(2026, 10, 1, 12, 0, 0)
    added = record_snapshots(
        db,
        [fake_listing(1, "BTC", 85000.5, 1, 30e9), fake_listing(1027, "ETH", 2700.25, 2, 15e9)],
        synced_at=t,
    )
    rows = _rows(db)
    assert added == 2 and len(rows) == 2
    btc = rows[0]
    assert (btc.coin_id, btc.symbol, float(btc.price_usd), btc.cmc_rank, float(btc.volume_24h)) == (
        1, "BTC", 85000.5, 1, 30e9,
    )
    assert all(r.synced_at == t for r in rows)  # one sync shares one timestamp


def test_a_second_sync_adds_rows_and_never_overwrites(db):
    record_snapshots(db, [fake_listing(1, "BTC", 80000.0, 1)], synced_at=datetime(2026, 10, 1, 0))
    record_snapshots(db, [fake_listing(1, "BTC", 90000.0, 1)], synced_at=datetime(2026, 10, 1, 1))
    rows = _rows(db)
    assert [float(r.price_usd) for r in rows] == [80000.0, 90000.0]
    assert [r.synced_at.hour for r in rows] == [0, 1]


def test_coins_without_a_usable_price_are_skipped(db):
    added = record_snapshots(
        db,
        [
            fake_listing(1, "BTC", 85000.0, 1),
            fake_listing(2, "NOPRICE", None, 50),
            fake_listing(3, "ZERO", 0, 60),
            fake_listing(4, "NEG", -1.0, 70),
        ],
    )
    assert added == 1
    assert [r.symbol for r in _rows(db)] == ["BTC"]


def test_micro_cap_price_keeps_its_precision(db):
    record_snapshots(db, [fake_listing(9, "TINY", 0.000000001234, 400)])
    assert float(_rows(db)[0].price_usd) == 0.000000001234


def test_default_timestamp_is_utc_now(db):
    before = datetime.utcnow()
    record_snapshots(db, [fake_listing(1, "BTC", 1.0, 1)])
    after = datetime.utcnow()
    ts = _rows(db)[0].synced_at
    assert ts.tzinfo is None and before <= ts <= after


class _FakeCMC:
    def __init__(self, listings):
        self.listings = listings

    def get_top_listings(self, limit):
        return self.listings[:limit]

    def get_all_listings(self):
        return self.listings

    def get_quotes_by_ids(self, ids):
        return [c for c in self.listings if c["id"] in ids]


def _seed_coins(db, listings):
    for c in listings:
        db.add(Coin(cmc_id=c["id"], symbol=c["symbol"], name=c["name"], slug=c["slug"]))
    db.commit()


def test_hot_sync_records_snapshots(db):
    listings = [fake_listing(1, "BTC", 85000.0, 1), fake_listing(1027, "ETH", 2700.0, 2)]
    _seed_coins(db, listings)
    MarketDataService(db, client=_FakeCMC(listings)).sync_hot_listings()
    assert db.scalar(select(func.count()).select_from(PriceSnapshot)) == 2


def test_full_listings_sync_records_snapshots(db):
    listings = [fake_listing(1, "BTC", 85000.0, 1), fake_listing(1027, "ETH", 2700.0, 2)]
    MarketDataService(db, client=_FakeCMC(listings)).sync_listings()
    assert db.scalar(select(func.count()).select_from(PriceSnapshot)) == 2


def test_view_driven_sync_ids_does_not_record_snapshots(db):
    listings = [fake_listing(1, "BTC", 85000.0, 1)]
    _seed_coins(db, listings)
    MarketDataService(db, client=_FakeCMC(listings)).sync_ids([1])
    assert db.scalar(select(func.count()).select_from(PriceSnapshot)) == 0
