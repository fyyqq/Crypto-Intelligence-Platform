"""Narrative / chain 24h scores: average of the top 20 coins by market cap that have a 24h change."""

from app.services import sector_performance_service as sp


def coin(cid, cap, narratives=(), chain=""):
    return {"cmc_id": cid, "market_cap_usd": cap, "narrative_list": list(narratives), "main_chain": chain}


def test_average_of_the_top_coins_by_market_cap_with_a_change():
    rows = [coin(i, 1000 - i, ["Memes"]) for i in range(1, 26)] + [coin(99, 5000, ["Memes"])]  # 99 has no change
    changes = {i: float(i) for i in range(1, 26)}
    s = sp.sector_scores(rows, changes, lambda r: r["narrative_list"])
    assert s["Memes"]["coins"] == 20 and s["Memes"]["pct"] == sum(range(1, 21)) / 20  # coins 1-20 are the biggest


def test_a_coin_counts_in_every_narrative_it_has_and_small_sectors_get_no_score():
    rows = [coin(1, 10, ["DeFi", "AI"]), coin(2, 9, ["DeFi"]), coin(3, 8, ["DeFi", "AI"]), coin(4, 7, ["AI"])]
    s = sp.sector_scores(rows, {1: 10.0, 2: -4.0, 3: 0.0, 4: 3.0}, lambda r: r["narrative_list"])
    assert s["DeFi"] == {"pct": 2.0, "coins": 3} and s["AI"] == {"pct": 13 / 3, "coins": 3}
    assert sp.sector_scores(rows[:2], {1: 1.0, 2: 1.0}, lambda r: r["narrative_list"]) == {}  # under 3 coins


def test_chains_use_each_coins_one_chain_and_ranking_puts_unscored_last():
    rows = [coin(i, 100 - i, chain="Solana" if i % 2 else "Base") for i in range(1, 9)]
    s = sp.sector_scores(rows, {i: (5.0 if i % 2 else -5.0) for i in range(1, 9)}, lambda r: [r["main_chain"]])
    assert s["Solana"]["pct"] == 5.0 and s["Base"]["pct"] == -5.0
    assert sp.ranked(["Base", "Tron", "Solana", "Sui"], s) == ["Solana", "Base", "Tron", "Sui"]


def test_table_rows_have_the_top_coins_and_the_three_biggest_gainers_and_losers():
    rows = [coin(i, 1000 - i, ["Memes"]) for i in range(1, 16)] + [coin(50, 1, ["Memes"]), coin(51, 0, ["Memes"])]
    changes = {i: (i - 8.0) for i in range(1, 16)}  # -7 .. +7, coin 8 is 0
    changes[50] = 90.0  # a tiny coin: not in the top 20 by cap but still the biggest gainer
    t = sp.sector_table(rows, changes, lambda r: r["narrative_list"])["Memes"]
    assert t["top"] == list(range(1, 11))  # the 10 largest by market cap
    assert [c for c, _ in t["gainers"]] == [50, 15, 14] and [c for c, _ in t["losers"]] == [1, 2, 3]
    assert t["pct"] is not None and t["coins"] == 16
    assert all(p > 0 for _, p in t["gainers"]) and all(p < 0 for _, p in t["losers"])  # coin 8 (0%) is neither


def test_a_small_sector_still_gets_a_row_without_a_score_and_ranking_puts_it_last():
    rows = [coin(1, 5, ["Tiny"]), coin(2, 4, ["Tiny"])]
    t = sp.sector_table(rows, {1: 2.0, 2: -1.0}, lambda r: r["narrative_list"])
    assert t["Tiny"]["pct"] is None and t["Tiny"]["top"] == [1, 2] and t["Tiny"]["gainers"] == [(1, 2.0)]
    assert sp.ranked(["Tiny", "Big"], {"Tiny": t["Tiny"], "Big": {"pct": 1.0}}) == ["Big", "Tiny"]


def test_sector_view_sorts_by_gainer_or_loser_numbers_rows_and_searches_by_name(monkeypatch):
    import sys
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent / "frontend"))
    from frontend.state import coin_state as cs

    base = [
        {"name": "Alpha", "gain": 5.0, "loss": -2.0}, {"name": "Beta", "gain": None, "loss": -9.0},
        {"name": "Gamma", "gain": 12.0, "loss": None}, {"name": "Usd Stablecoin", "gain": 0.1, "loss": -0.1},
    ]
    names = lambda v: [r["name"] for r in v]
    assert names(cs.sector_view(base)) == ["Alpha", "Beta", "Gamma", "Usd Stablecoin"]
    assert names(cs.sector_view(base, "gainer_desc")) == ["Gamma", "Alpha", "Usd Stablecoin", "Beta"]  # no gainer: last
    assert names(cs.sector_view(base, "gainer_asc")) == ["Usd Stablecoin", "Alpha", "Gamma", "Beta"]
    assert names(cs.sector_view(base, "loser_desc")) == ["Beta", "Alpha", "Usd Stablecoin", "Gamma"]  # biggest fall first
    assert names(cs.sector_view(base, "loser_asc")) == ["Usd Stablecoin", "Alpha", "Beta", "Gamma"]
    found = cs.sector_view(base, "gainer_desc", " AL")
    assert names(found) == ["Alpha"] and found[0]["id"] == 2  # keeps its position in the sorted table
    assert cs.sector_view(base, "bogus") == [{**r, "id": i} for i, r in enumerate(base, 1)]
    assert [cs._next_sort(x, "gainer") for x in ("", "gainer_desc", "gainer_asc", "loser_desc")] == ["gainer_desc", "gainer_asc", "", "gainer_desc"]
    assert [cs._is_stablecoin(n) for n in ("Fiat Stablecoin", "Usd STABLECOIN", "Memes")] == [True, True, False]
