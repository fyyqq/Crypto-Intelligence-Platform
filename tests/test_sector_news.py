"""Stories for a narrative / chain page and the header search: found by the coins' names and tickers (whole words)."""

from pathlib import Path

import pytest


@pytest.fixture
def ns(monkeypatch):
    pytest.importorskip("reflex")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent / "frontend"))
    from frontend.state import news_state

    return news_state


def coin(symbol, name, cap):
    return {"symbol": symbol, "name": name, "market_cap_usd": cap, "icon_url": "", "cmc_id": 1}


def article(title, snippet="", target=False, slug="", group=""):
    return {"title": title, "snippet": snippet, "news_type": "Cryptocurrency", "has_target": target, "narrative_slug": slug,
            "target_group": group, "target_symbol": "X" if target else "", "target_narrative": "OLD" if target else "",
            "detail_url": "/news/cryptocurrency/" + title.lower().replace(" ", "-"), "time_display": "1h ago", "source_name": "S"}


ROWS = [coin("DOGE", "Dogecoin", 9), coin("PEPE", "Pepe", 8), coin("BONK", "Bonk", 7), coin("WIF", "dogwifhat", 6), coin("M", "MemeCore", 5), coin("X1", "Meme", 4)]


def test_tickers_match_exactly_as_whole_words_and_names_ignore_case(ns):
    find = ns.mention_finder(ROWS)
    assert find("DOGE jumps 10% as traders pile in") == "DOGE"
    assert find("dogecoin is back") == "DOGE" and find("Elon tweets about DOGECOIN") == "DOGE"
    assert find("doge-like rally") == "" and find("the dodgers won") == "" and find("EBONKED") == ""  # no partial words
    assert find("PEPE and BONK") in ("PEPE", "BONK")
    assert find("a Meme wave") == "" and find("M is the new") == ""  # generic name / 1-letter ticker are not looked for
    assert find("Bonk: new airdrop") == "BONK"  # a name of 4+ letters (the ticker needs its own case)


def test_a_chains_own_name_counts_for_its_top_coin(ns):
    find = ns.mention_finder([coin("SOL", "Solana", 9)], "Solana", "SOL")
    assert find("Solana outage ends") == "SOL" and find("Sui rallies") == ""
    chain = ns.mention_finder([coin("USDC", "USDC", 9)], "Base", "ETH")
    assert chain("Base adds a feature") == "ETH"


def test_sector_articles_keep_ai_tied_stories_and_add_mentions_newest_first(ns):
    arts = [article("DOGE rallies"), article("Unrelated headline"), article("Shiba news", target=True, slug="memes"),
            article("Other narrative", target=True, slug="defi"), article("Bonk holders vote", "airdrop")]
    out = ns.sector_articles(arts, "narrative", "memes", "Memes", ROWS)
    assert [a["title"] for a in out] == ["DOGE rallies", "Shiba news", "Bonk holders vote"]  # original (newest-first) order
    assert out[0]["target_symbol"] == "DOGE" and out[0]["target_narrative"] == "MEMES"  # card badges for a mention
    assert out[1]["target_symbol"] == "X"  # an AI-tied story keeps its own badges
    news = [dict(article("DOGE rallies"), news_type="Technology")]
    assert ns.sector_articles(news, "narrative", "memes", "Memes", ROWS) == []  # only Cryptocurrency stories


def test_header_search_articles(ns):
    arts = [article("Pepe surges"), article("Market wrap"), article("Why Ethereum ETF flows slow", "etf")]
    got = ns.articles_for_search("pepe", [ROWS[1]], arts)
    assert [a["title"] for a in got] == ["Pepe surges"] and set(got[0]) == {"title", "detail_url", "time_display", "source_name"}
    assert [a["title"] for a in ns.articles_for_search("ethereum etf", [], arts)] == ["Why Ethereum ETF flows slow"]  # typed text
    assert ns.articles_for_search("eth", [], arts) == []  # under 4 characters and no coin: no guess
    many = [article(f"DOGE story {i}") for i in range(10)]
    assert len(ns.articles_for_search("doge", [ROWS[0]], many)) == 4
