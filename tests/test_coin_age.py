"""Coin age: the display text and the launch-date store (best source wins, a miss is retried later). No network."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.coin import Coin
from app.models.coin_contract import CoinContract
from app.services import coin_age_service as ca


def test_age_text_is_years_and_days_without_the_date():
    t = date(2026, 10, 15)
    assert ca.format_age(date(2025, 10, 12), t) == "1 year 3 days"
    assert ca.format_age(date(2025, 10, 15), t) == "1 year"
    assert ca.format_age(date(2020, 8, 1), t) == "6 years 75 days"
    assert ca.format_age(date(2026, 9, 1), t) == "44 days"
    assert ca.format_age(date(2026, 10, 14), t) == "1 day" and ca.format_age(t, t) == "Today"
    assert ca.format_age(date(2024, 2, 29), date(2026, 3, 1)).startswith("2 years")  # a 29 Feb start
    assert ca.format_age(None, t) == "" and ca.format_age(date(2027, 1, 1), t) == ""  # unknown / a future date: nothing
    assert "(" not in ca.format_age(date(2019, 2, 25), t)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(ca, "SessionLocal", maker)
    s = maker()
    yield s
    s.close()
    engine.dispose()


def test_a_better_source_replaces_a_worse_one_but_never_the_reverse(db):
    assert ca.store(db, 1, date(2021, 5, 1), "cmc_added") is True
    assert ca.store(db, 1, date(2021, 3, 1), "dex") is True and ca.all_dates()[1] == date(2021, 3, 1)
    assert ca.store(db, 1, date(2020, 12, 25), "coingecko") is True
    assert ca.store(db, 1, date(2021, 5, 1), "cmc_added") is False and ca.store(db, 1, date(2021, 3, 1), "dex") is False
    assert ca.all_dates() == {1: date(2020, 12, 25)}


def test_record_cmc_reads_iso_dates_and_ignores_garbage(db):
    ca.record_cmc(db, 5, None, "2013-04-28T00:00:00.000Z")
    assert ca.all_dates()[5] == date(2013, 4, 28)
    ca.record_cmc(db, 5, "2009-01-03T00:00:00.000Z", "2013-04-28T00:00:00.000Z")  # date_launched beats date_added
    assert ca.all_dates()[5] == date(2009, 1, 3)
    ca.record_cmc(db, 6, "not a date", None)
    ca.record_cmc(db, 7, None, None)
    assert 6 not in ca.all_dates() and 7 not in ca.all_dates()


def make_coin(db, cmc_id=10, symbol="SHIB", rank=30, chain="Ethereum"):
    c = Coin(cmc_id=cmc_id, symbol=symbol, name=symbol, slug=symbol.lower(), cmc_rank=rank)
    c.contracts = [CoinContract(platform_name=chain, platform_symbol="ETH", contract_address="0xabc", sort_order=0, is_primary=True)]
    db.add(c)
    db.commit()


def test_lookup_order_coingecko_then_dex_and_a_miss_is_remembered_then_retried(db, monkeypatch):
    make_coin(db, rank=600)  # a smaller token: the DEX fallback applies
    calls = []
    monkeypatch.setattr(ca, "gecko_genesis", lambda path: calls.append(("gecko", path)) or None)
    monkeypatch.setattr(ca, "dex_oldest_pair", lambda addr: calls.append(("dex", addr)) or date(2020, 8, 1))
    from app.services import coingecko_service as cg

    monkeypatch.setattr(cg, "_get_top_coin_symbol_map", lambda: {"SHIB": "shiba-inu"})
    assert ca.ensure(10) == date(2020, 8, 1)
    assert calls == [("gecko", "ethereum/contract/0xabc"), ("dex", "0xabc")]  # rank 600: no top-coin id lookup
    calls.clear()
    assert ca.ensure(10) == date(2020, 8, 1) and calls == []  # a lesser source was just found: not asked again yet
    monkeypatch.setattr(ca, "gecko_genesis", lambda path: date(2020, 7, 31) if path.endswith("/0xabc") else None)
    row = db.get(ca.CoinLaunchDate, 10)
    row.checked_at = datetime.now(timezone.utc) - timedelta(days=4)
    db.commit()
    assert ca.ensure(10) == date(2020, 7, 31)  # the retry finds the better source and replaces the DEX date

    make_coin(db, 11, "NOPE", 9000)
    monkeypatch.setattr(ca, "gecko_genesis", lambda path: calls.append(("gecko", path)) or None)
    monkeypatch.setattr(ca, "dex_oldest_pair", lambda addr: None)
    assert ca.ensure(11) is None
    n = len(calls)
    assert ca.ensure(11) is None and len(calls) == n  # a miss is remembered
    assert ca.ensure(999) is None  # unknown coin


def test_bulk_cmc_record_keeps_the_best_source_and_survives_bad_input(db):
    n = ca.record_cmc_bulk(db, {1: (None, "2021-05-01T00:00:00Z"), 2: ("2015-07-30T00:00:00Z", "2015-08-07T00:00:00Z"), 3: (None, None), 4: ("junk", "junk")})
    assert n == 2 and ca.all_dates() == {1: date(2021, 5, 1), 2: date(2015, 7, 30)}  # launched beats added
    ca.store(db, 1, date(2020, 12, 25), "coingecko")
    assert ca.record_cmc_bulk(db, {1: ("2021-01-01T00:00:00Z", None), 5: (None, "2024-01-02T00:00:00Z")}) == 1
    assert ca.all_dates()[1] == date(2020, 12, 25) and ca.all_dates()[5] == date(2024, 1, 2)
    assert ca.record_cmc_bulk(db, {}) == 0


def test_a_native_coin_is_never_searched_on_a_dex_by_its_placeholder_contract(db, monkeypatch):
    make_coin(db, 20, "ETH", 2)
    c = db.query(Coin).filter(Coin.cmc_id == 20).one()
    c.contracts[0].contract_address = "0x" + "e" * 40
    db.commit()
    calls = []
    monkeypatch.setattr(ca, "gecko_genesis", lambda path: calls.append(path) or (date(2015, 7, 30) if path == "ethereum" else None))
    monkeypatch.setattr(ca, "dex_oldest_pair", lambda addr: calls.append(("dex", addr)) or date(2021, 1, 5))
    from app.services import coingecko_service as cg

    monkeypatch.setattr(cg, "_get_top_coin_symbol_map", lambda: {"ETH": "ethereum"})
    assert ca.ensure(20) == date(2015, 7, 30) and calls == ["ethereum"]  # by CoinGecko id only: no contract, no DEX
    make_coin(db, 21, "NATIVE", 9000)
    db.query(Coin).filter(Coin.cmc_id == 21).one().contracts[0].contract_address = "0x" + "0" * 40
    db.commit()
    calls.clear()
    assert ca.ensure(21) is None and not any(isinstance(c, tuple) for c in calls)


def test_a_rate_limited_coingecko_is_not_remembered_as_a_miss(db, monkeypatch):
    make_coin(db, 30, "OLD", 5)
    monkeypatch.setattr(ca, "dex_oldest_pair", lambda addr: None)

    def throttled(path):
        ca._GECKO_BACKOFF_UNTIL = __import__("time").time() + 100
        return None

    monkeypatch.setattr(ca, "gecko_genesis", throttled)
    from app.services import coingecko_service as cg

    monkeypatch.setattr(cg, "_get_top_coin_symbol_map", lambda: {})
    monkeypatch.setattr(ca, "_GECKO_BACKOFF_UNTIL", 0.0)
    assert ca.ensure(30) is None
    assert db.get(ca.CoinLaunchDate, 30) is None  # nothing stored, so the next visit asks again


def test_a_top_coin_never_falls_back_to_the_dex_pair_of_its_wrapped_contract(db, monkeypatch):
    make_coin(db, 40, "XRP", 4)  # top-5 coin with a (wrapped) contract
    monkeypatch.setattr(ca, "gecko_genesis", lambda path: None)
    dex = []
    monkeypatch.setattr(ca, "dex_oldest_pair", lambda addr: dex.append(addr) or date(2021, 3, 1))
    from app.services import coingecko_service as cg

    monkeypatch.setattr(cg, "_get_top_coin_symbol_map", lambda: {})
    assert ca.ensure(40) is None and dex == []


def test_a_failed_top_coin_map_is_not_cached_forever(monkeypatch):
    from app.services import coingecko_service as cg

    monkeypatch.setattr(cg, "_top_coin_symbol_to_id", None)
    monkeypatch.setattr(cg, "_top_coin_map_failed_at", 0.0)

    class R429:
        status_code = 429

        def raise_for_status(self):
            raise cg.requests.HTTPError("429")

    class OK:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return [{"symbol": "eth", "id": "ethereum"}]

    answers = [R429()]
    monkeypatch.setattr(cg.requests, "get", lambda *a, **k: answers[0])
    assert cg._get_top_coin_symbol_map() == {} and cg._top_coin_symbol_to_id is None
    assert cg._get_top_coin_symbol_map() == {}  # within the minute: no new request
    monkeypatch.setattr(cg, "_top_coin_map_failed_at", 0.0)
    answers[0] = OK()
    assert cg._get_top_coin_symbol_map() == {"ETH": "ethereum"} and cg._top_coin_symbol_to_id == {"ETH": "ethereum"}
