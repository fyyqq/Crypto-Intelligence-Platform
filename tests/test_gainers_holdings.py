"""/gainers-losers marks the coins you hold: in place when they are in the board's top rows, otherwise at the end
with their real # in the band; coins outside the rank band (or unknown) are not shown."""

from app.services import price_snapshot_service as svc


def c(coin_id, symbol, rank, pct, price=1.0):
    return {"coin_id": coin_id, "symbol": symbol, "name": symbol, "rank": rank, "pct_change": pct, "price_now": price,
            "price_then": price, "volume_24h": 1e6, "then_at": None, "now_at": None}


CHANGES = (
    [c(i, f"G{i}", i, 40 - i * 0.1) for i in range(1, 41)]  # 40 gainers, ranks 1-40, + 40% down to +36%
    + [c(100 + i, f"L{i}", 40 + i, -0.5 - i * 0.1) for i in range(1, 31)]  # 30 losers, ranks 41-70
    + [c(900, "FET", 92, -0.3, price=0.2), c(901, "FET", 480, 12.0, price=0.0004)]  # two coins named FET
    + [c(902, "ABC", 150, 5.0), c(903, "XYZ", 650, 9.0)]  # ABC is in the 101-200 band; XYZ is beyond rank 500
)


def test_the_held_ticker_resolves_to_the_best_ranked_coin_with_a_plausible_price():
    assert svc.held_coin_ids(CHANGES, {"FET": 0.21}) == {900}  # not the rank-480 lookalike
    assert svc.held_coin_ids(CHANGES, {"FET": 5.0}) == set()  # nothing within 0.5x-2x of that price
    assert svc.held_coin_ids(CHANGES, {"NOPE": 1.0}) == set() and svc.held_coin_ids(CHANGES, None) == set()


def test_a_held_coin_in_the_top_rows_is_marked_in_place():
    rows = svc.board_rows(CHANGES, 100, "gainers", 30, {5})
    assert len(rows) == 30 and not any(r["extra"] for r in rows)
    assert [(r["position"], r["held"]) for r in rows if r["held"]] == [(5, True)]


def test_a_held_coin_outside_the_top_rows_goes_to_the_end_of_its_own_side_only():
    band = [x for x in CHANGES if x["rank"] <= 100]
    # A gainer beyond the top 30 (the 31st-40th of 40 gainers): last row of Gainers, with its real position; never in Losers.
    gain = svc.board_rows(CHANGES, 100, "gainers", 30, {35})
    assert len(gain) == 31 and gain[-1]["extra"] and gain[-1]["held"] and gain[-1]["coin"]["coin_id"] == 35 and gain[-1]["position"] == 35
    assert all(r["coin"]["coin_id"] != 35 for r in svc.board_rows(CHANGES, 100, "losers", 30, {35}))
    # FET is down 0.3%: Losers only (a mild loser sits after the worst ones), never on the Gainers board.
    assert all(r["coin"]["coin_id"] != 900 for r in svc.board_rows(CHANGES, 100, "gainers", 30, {900}))
    loss = svc.board_rows(CHANGES, 100, "losers", 30, {900})
    assert loss[-1]["extra"] and loss[-1]["position"] == sorted(band, key=lambda x: x["pct_change"]).index(CHANGES[70]) + 1 > 30
    # exactly 0% is in no top list: it goes with the gainers
    flat = CHANGES + [c(950, "FLAT", 50, 0.0)]
    assert svc.board_rows(flat, 100, "gainers", 30, {950})[-1]["coin"]["coin_id"] == 950
    assert all(r["coin"]["coin_id"] != 950 for r in svc.board_rows(flat, 100, "losers", 30, {950}))


def test_the_other_bands_show_their_own_holdings_and_nothing_beyond_rank_500():
    assert [r["coin"]["coin_id"] for r in svc.board_rows(CHANGES, 200, "gainers", 30, {902})] == [902]  # 101-200: only that coin exists, up 5%
    assert svc.board_rows(CHANGES, 100, "gainers", 30, {902})[-1]["coin"]["coin_id"] != 902  # not in the 1-100 board
    allbands = [r["coin"]["coin_id"] for b in svc.BUCKETS for r in svc.board_rows(CHANGES, b, "gainers", 30, {903})]
    assert 903 not in allbands  # rank 650: never shown


def test_without_holdings_the_board_is_exactly_rank_movers():
    plain = svc.rank_movers(CHANGES, 100, "gainers", 30)
    rows = svc.board_rows(CHANGES, 100, "gainers", 30)
    assert [r["coin"]["coin_id"] for r in rows] == [x["coin_id"] for x in plain] and [r["position"] for r in rows] == list(range(1, 31))


def test_only_listed_viewers_get_any_holdings(monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "frontend"))
    from app.services import mexc_service
    from frontend.state import gainers_losers_state as gls

    monkeypatch.setattr(mexc_service.settings, "mexc_viewer_emails", "me@example.com")
    monkeypatch.setattr(mexc_service, "held_assets", lambda: {"FET": 0.2})
    assert gls._load_holdings("me@example.com") == {"FET": 0.2}
    assert gls._load_holdings("someone@else.com") == {} and gls._load_holdings("") == {}
    from datetime import datetime, timezone

    coin = {**CHANGES[0], "then_at": datetime(2026, 10, 15, tzinfo=timezone.utc)}
    monkeypatch.setattr(gls, "_coin_slug", lambda cmc_id, symbol: symbol.lower())
    row = gls._display_row(3, coin, held=True, extra=True)
    assert row["held"] == "1" and row["extra"] == "1" and "amount" not in row  # only a flag reaches the browser
