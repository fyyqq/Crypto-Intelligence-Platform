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
