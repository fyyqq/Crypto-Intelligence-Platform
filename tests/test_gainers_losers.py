"""Steps 2-6: windows, lookback, edge cases, cold start, ranking, output.
Small fake data in an in-memory SQLite database only."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.coin import Coin
from app.models.price_snapshot import PriceSnapshot
from app.services import price_snapshot_service as svc

NOW = datetime(2026, 10, 5, 12, 0, 0)
BIG_VOL = 10_000_000.0


def snap(db, coin_id, symbol, price, at, rank=1, volume=BIG_VOL):
    db.add(PriceSnapshot(coin_id=coin_id, symbol=symbol, price_usd=price, cmc_rank=rank, volume_24h=volume, synced_at=at))


def coin(db, coin_id, symbol):
    db.add(Coin(cmc_id=coin_id, symbol=symbol, name=f"{symbol} Coin", slug=symbol.lower()))


def history_anchor(db, days=40):
    """An old snapshot of an unrelated coin so every window counts as ready."""
    snap(db, 999999, "OLD", 1.0, NOW - timedelta(days=days), rank=9999)


def symbols(rows):
    return [r["symbol"] for r in rows]


# ---- formula + direction -----------------------------------------------------
def test_gainer_only_in_gainers_loser_only_in_losers_dust_in_neither(db):
    history_anchor(db)
    snap(db, 1, "UP", 100.0, NOW - timedelta(hours=24), rank=10)
    snap(db, 1, "UP", 125.0, NOW, rank=10)  # +25%
    snap(db, 2, "DOWN", 100.0, NOW - timedelta(hours=24), rank=20)
    snap(db, 2, "DOWN", 90.0, NOW, rank=20)  # -10%
    snap(db, 3, "DUST", 100.0, NOW - timedelta(hours=24), rank=30, volume=1_000)
    snap(db, 3, "DUST", 300.0, NOW, rank=30, volume=49_999)  # +200% but dust
    db.commit()

    gainers = svc.get_movers(db, 100, "24h", "gainers")["coins"]
    losers = svc.get_movers(db, 100, "24h", "losers")["coins"]
    assert symbols(gainers) == ["UP"] and gainers[0]["pct_change"] == pytest.approx(25.0)
    assert symbols(losers) == ["DOWN"] and losers[0]["pct_change"] == pytest.approx(-10.0)


def test_zero_change_is_in_neither_list(db):
    history_anchor(db)
    snap(db, 1, "FLAT", 5.0, NOW - timedelta(hours=24))
    snap(db, 1, "FLAT", 5.0, NOW)
    db.commit()
    assert svc.get_movers(db, 100, "24h", "gainers")["coins"] == []
    assert svc.get_movers(db, 100, "24h", "losers")["coins"] == []


def test_sort_order_gainers_desc_losers_most_negative_first(db):
    history_anchor(db)
    for i, (then, now) in enumerate([(10, 11), (10, 15), (10, 12), (10, 9), (10, 5), (10, 8)], start=1):
        snap(db, i, f"C{i}", then, NOW - timedelta(hours=24), rank=i)
        snap(db, i, f"C{i}", now, NOW, rank=i)
    db.commit()
    assert symbols(svc.get_movers(db, 100, "24h", "gainers")["coins"]) == ["C2", "C3", "C1"]
    assert symbols(svc.get_movers(db, 100, "24h", "losers")["coins"]) == ["C5", "C6", "C4"]


def test_one_shared_calculation_for_both_directions(db):
    history_anchor(db)
    snap(db, 1, "UP", 10.0, NOW - timedelta(hours=24))
    snap(db, 1, "UP", 20.0, NOW)
    db.commit()
    changes = svc.compute_changes(db, "24h")
    assert svc.rank_movers(changes, 100, "gainers")[0]["pct_change"] == pytest.approx(100.0)
    assert svc.rank_movers(changes, 100, "losers") == []


# ---- edge cases ---------------------------------------------------------------
def test_new_coin_without_history_is_skipped(db):
    history_anchor(db)
    snap(db, 1, "NEW", 50.0, NOW - timedelta(hours=2))  # too recent for 24h
    snap(db, 1, "NEW", 80.0, NOW)
    db.commit()
    assert svc.compute_changes(db, "24h") == []


def test_missed_sync_uses_closest_snapshot_inside_tolerance(db):
    history_anchor(db)
    # No snapshot at exactly -24h: -22h and -27h exist, -22h is closer.
    snap(db, 1, "GAP", 80.0, NOW - timedelta(hours=27))
    snap(db, 1, "GAP", 90.0, NOW - timedelta(hours=22))
    snap(db, 1, "GAP", 99.0, NOW)
    db.commit()
    row = svc.compute_changes(db, "24h")[0]
    assert row["price_then"] == 90.0 and row["then_at"] == NOW - timedelta(hours=22)


def test_missed_sync_with_nothing_inside_tolerance_is_skipped(db):
    history_anchor(db)
    snap(db, 1, "GAP", 80.0, NOW - timedelta(hours=30))  # outside 20-28h
    snap(db, 1, "GAP", 90.0, NOW - timedelta(hours=18))  # outside 20-28h
    snap(db, 1, "GAP", 99.0, NOW)
    db.commit()
    assert svc.compute_changes(db, "24h") == []


def test_zero_price_then_is_never_divided_by(db):
    history_anchor(db)
    snap(db, 1, "ZERO", 0.0, NOW - timedelta(hours=24))
    snap(db, 1, "ZERO", 5.0, NOW)
    db.commit()
    assert svc.compute_changes(db, "24h") == []


def test_dust_floor_uses_current_volume_and_applies_to_every_window(db):
    history_anchor(db)
    for back in (timedelta(hours=24), timedelta(days=7), timedelta(days=30)):
        snap(db, 1, "DUST", 1.0, NOW - back, volume=BIG_VOL)  # liquid in the past
    snap(db, 1, "DUST", 2.0, NOW, volume=10_000)  # dust now
    db.commit()
    for window in svc.WINDOWS:
        for direction in svc.DIRECTIONS:
            assert svc.get_movers(db, 500, window, direction)["coins"] == []


# ---- (a) each window picks the right lookback snapshot -----------------------
def test_each_window_picks_its_own_lookback_snapshot(db):
    history_anchor(db)
    snap(db, 1, "BTC", 30.0, NOW - timedelta(days=30))
    snap(db, 1, "BTC", 31.0, NOW - timedelta(days=29))  # also in tolerance, further from target
    snap(db, 1, "BTC", 70.0, NOW - timedelta(days=7))
    snap(db, 1, "BTC", 75.0, NOW - timedelta(days=6, hours=12))
    snap(db, 1, "BTC", 240.0, NOW - timedelta(hours=24))
    snap(db, 1, "BTC", 230.0, NOW - timedelta(hours=22))
    snap(db, 1, "BTC", 300.0, NOW)
    db.commit()
    picks = {w: svc.compute_changes(db, w)[0] for w in svc.WINDOWS}
    assert (picks["24h"]["price_then"], picks["24h"]["then_at"]) == (240.0, NOW - timedelta(hours=24))
    assert (picks["7d"]["price_then"], picks["7d"]["then_at"]) == (70.0, NOW - timedelta(days=7))
    assert (picks["30d"]["price_then"], picks["30d"]["then_at"]) == (30.0, NOW - timedelta(days=30))
    assert picks["30d"]["pct_change"] == pytest.approx(900.0)


# ---- (b) in the 24h board, skipped in the 30d board --------------------------
def test_coin_with_24h_but_no_30d_history(db):
    history_anchor(db)
    snap(db, 1, "OLDCOIN", 10.0, NOW - timedelta(days=30), rank=1)
    snap(db, 1, "OLDCOIN", 10.0, NOW - timedelta(hours=24), rank=1)
    snap(db, 1, "OLDCOIN", 20.0, NOW, rank=1)
    snap(db, 2, "YOUNG", 10.0, NOW - timedelta(hours=24), rank=2)
    snap(db, 2, "YOUNG", 30.0, NOW, rank=2)
    db.commit()
    assert set(symbols(svc.get_movers(db, 100, "24h", "gainers")["coins"])) == {"OLDCOIN", "YOUNG"}
    assert symbols(svc.get_movers(db, 100, "30d", "gainers")["coins"]) == ["OLDCOIN"]


# ---- buckets, limit, no padding ---------------------------------------------
def test_buckets_are_cumulative_by_current_rank(db):
    history_anchor(db)
    for cid, rank in ((1, 50), (2, 150), (3, 450)):
        snap(db, cid, f"R{rank}", 1.0, NOW - timedelta(hours=24), rank=rank)
        snap(db, cid, f"R{rank}", 2.0, NOW, rank=rank)
    db.commit()
    assert symbols(svc.get_movers(db, 100, "24h", "gainers")["coins"]) == ["R50"]
    assert set(symbols(svc.get_movers(db, 200, "24h", "gainers")["coins"])) == {"R50", "R150"}
    assert len(svc.get_movers(db, 500, "24h", "gainers")["coins"]) == 3


def test_limit_and_no_padding(db):
    history_anchor(db)
    for i in range(1, 6):
        snap(db, i, f"C{i}", 1.0, NOW - timedelta(hours=24), rank=i)
        snap(db, i, f"C{i}", 1.0 + i, NOW, rank=i)
    db.commit()
    assert len(svc.get_movers(db, 100, "24h", "gainers", limit=3)["coins"]) == 3
    assert len(svc.get_movers(db, 100, "24h", "gainers", limit=30)["coins"]) == 5  # not padded


def test_output_fields(db):
    history_anchor(db)
    coin(db, 1, "BTC")
    snap(db, 1, "BTC", 100.0, NOW - timedelta(hours=24))
    snap(db, 1, "BTC", 110.0, NOW)
    db.commit()
    row = svc.get_movers(db, 100, "24h", "gainers")["coins"][0]
    assert {"rank", "name", "symbol", "price_now", "price_then", "pct_change", "volume_24h", "then_at"} <= set(row)
    assert row["name"] == "BTC Coin" and row["then_at"] == NOW - timedelta(hours=24)


def test_unknown_window_bucket_or_direction_is_rejected(db):
    with pytest.raises(svc.SnapshotConfigError, match="Unknown window"):
        svc.get_movers(db, 100, "1y", "gainers")
    with pytest.raises(svc.SnapshotConfigError, match="Unknown bucket"):
        svc.rank_movers([], 150, "gainers")
    with pytest.raises(svc.SnapshotConfigError, match="Unknown direction"):
        svc.rank_movers([], 100, "sideways")


# ---- cold start, per window ---------------------------------------------------
def test_cold_start_is_per_window(db):
    snap(db, 1, "BTC", 1.0, NOW - timedelta(days=2))  # 2 days of history in total
    snap(db, 1, "BTC", 1.0, NOW - timedelta(hours=24))
    snap(db, 1, "BTC", 1.1, NOW)
    db.commit()
    s24, s7, s30 = (svc.get_movers(db, 100, w, "gainers") for w in ("24h", "7d", "30d"))
    assert s24["status"] == "ready" and s24["coins"][0]["symbol"] == "BTC"
    assert (s7["status"], s7["days_remaining"], s7["coins"]) == ("collecting", 4, [])  # needs 6 days
    assert (s30["status"], s30["days_remaining"]) == ("collecting", 26)  # needs 28 days


def test_cold_start_with_no_snapshots_at_all(db):
    out = svc.get_movers(db, 100, "24h", "gainers")
    assert out["status"] == "collecting" and out["coins"] == [] and out["hours_remaining"] == 20


# ---- (c) + (d) retention ------------------------------------------------------
def test_cleanup_keeps_a_31_day_old_snapshot(db):
    snap(db, 1, "BTC", 1.0, NOW - timedelta(days=31))
    snap(db, 1, "BTC", 1.0, NOW - timedelta(days=44))
    snap(db, 1, "BTC", 1.0, NOW - timedelta(days=46))
    db.commit()
    deleted = svc.cleanup_snapshots(db, now=NOW)
    remaining = sorted((NOW - at).days for at in db.scalars(select(PriceSnapshot.synced_at)).all())
    assert deleted == 1 and remaining == [31, 44]


def test_startup_check_rejects_too_short_retention():
    for too_short in (30, 32):  # longest window needs 30d + 2d tolerance
        with pytest.raises(svc.SnapshotConfigError, match="too short"):
            svc.validate_retention(too_short)
    svc.validate_retention(45)  # the real setting is fine


def test_cleanup_refuses_an_unsafe_retention(db):
    snap(db, 1, "BTC", 1.0, NOW - timedelta(days=31))
    db.commit()
    with pytest.raises(svc.SnapshotConfigError):
        svc.cleanup_snapshots(db, now=NOW, retention_days=20)
    assert db.scalar(select(func.count()).select_from(PriceSnapshot)) == 1


def test_adding_a_window_only_needs_a_config_entry(db, monkeypatch):
    windows = dict(svc.WINDOWS)
    windows["3d"] = svc.Window("3d", timedelta(days=3), timedelta(days=2, hours=12), timedelta(days=3, hours=12))
    monkeypatch.setattr(svc, "WINDOWS", windows)
    history_anchor(db)
    snap(db, 1, "BTC", 50.0, NOW - timedelta(days=3))
    snap(db, 1, "BTC", 100.0, NOW)
    db.commit()
    assert svc.get_movers(db, 100, "3d", "gainers")["coins"][0]["pct_change"] == pytest.approx(100.0)


# ---- coin page: market cap / volume vs ~24h ago ---------------------------
def test_pct_change_formula_and_guards():
    assert svc.pct_change(115.09, 100.0) == pytest.approx(15.09)
    assert svc.pct_change(50.0, 100.0) == pytest.approx(-50.0)
    assert svc.pct_change(10.0, 0) is None  # never divides by zero
    assert svc.pct_change(10.0, None) is None and svc.pct_change(None, 10.0) is None


def mcap_snap(db, at, market_cap, volume):
    db.add(PriceSnapshot(coin_id=1, symbol="BTC", price_usd=1.0, cmc_rank=1, volume_24h=volume, market_cap=market_cap, synced_at=at))


def test_reference_values_pick_closest_to_24h_inside_tolerance(db):
    mcap_snap(db, NOW - timedelta(hours=30), 500.0, 50.0)  # outside 20-28h
    mcap_snap(db, NOW - timedelta(hours=25), 900.0, 90.0)
    mcap_snap(db, NOW - timedelta(hours=21), 950.0, 95.0)
    mcap_snap(db, NOW - timedelta(hours=1), 999.0, 99.0)  # too recent
    db.commit()
    ref = svc.get_reference_values(db, 1, now=NOW)
    assert (ref["market_cap"], ref["volume_24h"]) == (900.0, 90.0)
    assert ref["market_cap_at"] == NOW - timedelta(hours=25)


def test_reference_values_per_field_and_missing(db):
    # The closest row has no market cap (older snapshot): market cap falls
    # back to the next usable one, volume uses the closest.
    mcap_snap(db, NOW - timedelta(hours=24), None, 80.0)
    mcap_snap(db, NOW - timedelta(hours=27), 700.0, 70.0)
    db.commit()
    ref = svc.get_reference_values(db, 1, now=NOW)
    assert ref["volume_24h"] == 80.0 and ref["market_cap"] == 700.0
    assert svc.get_reference_values(db, 2, now=NOW) == {
        "market_cap": None, "market_cap_at": None, "volume_24h": None, "volume_24h_at": None,
    }


def test_snapshot_records_market_cap(db):
    svc.record_snapshots(db, [{"id": 1, "symbol": "BTC", "cmc_rank": 1, "quote": {"USD": {"price": 2.0, "volume_24h": 5.0, "market_cap": 1234.5}}}])
    assert float(db.scalars(select(PriceSnapshot.market_cap)).one()) == 1234.5
