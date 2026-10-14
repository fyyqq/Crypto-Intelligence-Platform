"""Crypto Calendar: the parser for the three formats of the @layergg monthly post
(October "10-03 - $HYPE - ...", September "Sep 1: US - ...", August Korean
"8월 1일: ... - ..."), the month and category detection, and the month HTML."""

from datetime import date, datetime

import pytest

from app.services import crypto_calendar_service as cc

OCT = """🗓 2026 October Crypto + Market Calendar

Sorry for the late upload.

Noteworthy events😨

10-03 - $HYPE - First AQAv2 USDC yield payout, buyback & burn
10-05 - $ENA - StablecoinX ENA permanent unlock
10-09 - China - Government bond sale
10-10 - PaperTrade Launch
10-21 - NVDA - GTC Tempodrom, Jensen Huang keynote
10-22 - BOK - Base rate decision
10-28 - HOOD - Q3 earnings & call
10-29 - FED - FOMC rate decision
11-02 - $XYZ - Belongs to next month

TBDs
TBD - $DRV - Derive V3 launch (imminent)
TBD - $SOL - Alpenglow upgrade (Oct target)

✖️ See detail @Layergg

🚫 Disclaimer
10-30 - BOJ - this line is after the disclaimer and must be ignored
#September #Schedule #Calendar"""

SEP = """🗓 2026 September Crypto + Market Calendar

Oh Vlad, thank you for saving crypto✋.
• Sep 9: 2x US Treasury buyback
• Sep 16: Arc chain launch

Noteworthy events😨

Sep 1: 🇺🇸US - Kevin Warsh will talk with Japan at G20
Sep 2: $AVGO - Earnings
Sep 15: 🇺🇸US - CLARITY Act Vote 🔥🔥🔥
Sep 16: $ARC - ARC Mainnet 🔥🔥🔥
Sep 29: $HOOD - 9/29–30 HOOD Summit: Engines of Creation 🔥🔥

TBA
$BTC - BIP 110
$HOOD - Something New: Robincat

✖️ See detail @Layergg
#September #Schedule #Calendar"""

AUG = """🗓 2026 8월 크립토 + Market 캘린더

7월 다이나믹한 증시에서 많은 분들이 피해를 보신 것 같습니다.

눈여겨볼 이벤트😨

8월 1일: 삼성전기- MLCC 가격 30% 인상
8월 3일: HOOD(@RobinhoodApp  ) - Ventures Fund II 로드쇼
8월 5일: $CRCL(@circle) - 실적 발표
8월 8일: 🇺🇸US - 미 의회 휴회 및 CLARITY 법안 처리 시한
8월 27일: 🇺🇸US- 잭슨홀 미팅 개최(8월 27~29일)

TBA
BTC - BIP 110 논의
SAMSUNG - V10 NAND 양산

... and many more

✖️ See detail @Layergg
#August #Schedule #Calendar"""


def test_october_format():
    ev = cc.parse_post(OCT, 2026, 10)
    dated = [e for e in ev if e["date"]]
    assert [e["date"] for e in dated] == ["2026-10-03", "2026-10-05", "2026-10-09", "2026-10-10", "2026-10-21", "2026-10-22", "2026-10-28", "2026-10-29"]
    hype = dated[0]
    assert (hype["who"], hype["ticker"], hype["desc"]) == ("$HYPE", "HYPE", "First AQAv2 USDC yield payout, buyback & burn")
    assert dated[3]["who"] == "" and dated[3]["desc"] == "PaperTrade Launch"  # no "who - " part
    assert [e["desc"] for e in ev if not e["date"]] == ["Derive V3 launch (imminent)", "Alpenglow upgrade (Oct target)"]
    assert not any("next month" in e["desc"] or "disclaimer" in e["desc"] for e in ev)  # other month / after the footer


def test_september_format_skips_intro_bullets_and_reads_tba_list():
    ev = cc.parse_post(SEP, 2026, 9)
    dated = [e for e in ev if e["date"]]
    assert [e["date"] for e in dated] == ["2026-09-01", "2026-09-02", "2026-09-15", "2026-09-16", "2026-09-29"]  # the "• Sep 9" bullets are skipped
    assert dated[0]["who"] == "🇺🇸US" and dated[2]["hot"] and dated[2]["desc"] == "CLARITY Act Vote"  # 🔥 flags importance, not text
    assert [(e["who"], e["desc"]) for e in ev if not e["date"]] == [("$BTC", "BIP 110"), ("$HOOD", "Something New: Robincat")]


def test_korean_august_format():
    ev = cc.parse_post(AUG, 2026, 8)
    dated = [e for e in ev if e["date"]]
    assert [e["date"] for e in dated] == ["2026-08-01", "2026-08-03", "2026-08-05", "2026-08-08", "2026-08-27"]
    assert (dated[0]["who"], dated[0]["desc"]) == ("삼성전기", "MLCC 가격 30% 인상")
    assert dated[1]["who"] == "HOOD"  # the (@RobinhoodApp ) handle is dropped
    assert dated[4]["who"] == "🇺🇸US" and "잭슨홀" in dated[4]["desc"]
    assert [e["who"] for e in ev if not e["date"]] == ["BTC", "SAMSUNG"]  # TBA list, stops at "... and many more"


def test_categories():
    assert cc.classify("FED", "FOMC rate decision") == "macro"
    assert cc.classify("China", "Government bond sale") == "macro"
    assert cc.classify("SEC", "Regulation Crypto Assets comment deadline") == "macro"
    assert cc.classify("🇺🇸US", "something unlisted") == "macro"  # a flag means a country
    assert cc.classify("HOOD", "Q3 earnings & call") == "earnings"
    assert cc.classify("NVDA", "GTC keynote") == "earnings"  # a listed company
    assert cc.classify("$CRCL", "실적 발표") == "earnings"
    assert cc.classify("$HYPE", "First yield payout") == "crypto"
    assert cc.classify("US", "Q3 GDP advance est.") == "macro"  # macro words win over Q3
    assert cc.classify("$VAR", "Variational TGE (Q4)") == "crypto"  # a quarter in a launch target is not earnings
    assert cc.classify("ASML", "Q3 prelim earnings") == "earnings"


def test_post_month_detection():
    assert cc.post_month("🗓 2026 October Crypto + Market Calendar", "", None) == (2026, 10)
    assert cc.post_month("🗓 2026 8월 크립토 + Market 캘린더", "", None) == (2026, 8)
    assert cc.post_month("Crypto + Market Calendar", "...#June #Schedule", datetime(2026, 6, 1)) == (2026, 6)
    assert cc.post_month("Crypto + Market Calendar", "no hashtag", datetime(2026, 3, 2)) == (2026, 3)


def test_month_keys_run_from_january_to_the_current_month():
    assert cc.month_keys(date(2026, 10, 14)) == [f"2026-{m:02d}" for m in range(1, 11)]
    assert cc.month_keys(date(2026, 1, 3)) == ["2026-01"]
    assert len(cc.month_keys(date(2027, 2, 1))) == 12 and cc.month_keys(date(2025, 12, 1)) == []


def _month_html(**kw):
    ev = cc.parse_post(OCT, 2026, 10)
    return cc.build_month_html("2026-10", {"events": ev, "url": "u", "posted": None}, kw.get("icons", {}), kw.get("today", date(2026, 10, 14)))


def test_month_html_layout():
    h = _month_html(icons={"HYPE": 32196})
    assert h.count('class="cal-wd"') == 5 and "Sat" not in h.split("cal-board")[1].split("cal-section")[0]  # Monday to Friday only
    # Oct 1 2026 is a Thursday: Mon-Wed of week 1 are empty cells (the 31st is a Saturday: no trailing blanks);
    # the 3rd (a Saturday) goes to the weekend list
    assert h.count("cal-out") == 3
    assert "Weekend events" in h and "Oct 03" in h and "HYPE" in h and "coins/64x64/32196.png" in h
    assert "Date to be announced" in h and "Derive V3 launch" in h
    assert h.count("cal-today") == 1 and "cal-ev-macro" in h and "cal-ev-earnings" in h


def test_event_text_is_escaped():
    ev = [{"date": "2026-10-05", "who": "<script>", "ticker": "", "desc": 'x"><img src=x onerror=alert(1)>', "kind": "crypto", "hot": False}]
    h = cc.build_month_html("2026-10", {"events": ev, "url": "", "posted": None}, {}, date(2026, 10, 1))
    assert "<script>" not in h and "<img src=x" not in h and "&lt;script&gt;" in h


def test_empty_month():
    assert "No calendar post stored for January 2026" in cc.build_month_html("2026-01", None, {}, date(2026, 10, 1))


def test_symbol_icons_query_matches_the_real_schema():
    """The first version of this query used a column that does not exist (market_cap): run it on a real
    SQLite table built from the Coin model so a wrong column name fails here, not on the page."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401
    from app.core.database import Base
    from app.models.coin import Coin

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    cols = {c.name for c in Coin.__table__.columns}
    assert {"symbol", "cmc_id", "market_cap_usd"} <= cols
    sql = str(cc.symbol_icons.__code__.co_consts)  # the query text lives in the function
    assert "market_cap_usd" in sql and "market_cap DESC" not in sql
    db.close()


def test_logos_only_on_crypto_events():
    base = {"date": "2026-10-05", "who": "$PLTR", "ticker": "PLTR", "desc": "Earnings", "hot": False}
    icons = {"PLTR": 111, "HYPE": 222}
    stock = cc.build_month_html("2026-10", {"events": [{**base, "kind": "earnings"}], "url": "", "posted": None}, icons, date(2026, 10, 1))
    coin = cc.build_month_html("2026-10", {"events": [{**base, "who": "$HYPE", "ticker": "HYPE", "kind": "crypto"}], "url": "", "posted": None}, icons, date(2026, 10, 1))
    assert "coins/64x64/111.png" not in stock and "coins/64x64/222.png" in coin
