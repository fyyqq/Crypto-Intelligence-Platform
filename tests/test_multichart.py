"""/tools/multichart: the Tools menu entry, the route and the empty two-column grid of + cards."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "frontend"))


def test_multichart_is_the_last_tools_menu_entry_with_a_route():
    from frontend.components.tools_page import TOOL_PAGES

    assert TOOL_PAGES[-1]["href"] == "/tools/multichart" and TOOL_PAGES[-1]["title"] == "Multichart"
    assert 'route="/tools/multichart"' in (ROOT / "frontend" / "frontend" / "frontend.py").read_text()


def test_multichart_page_is_a_full_width_two_column_grid_with_one_card_and_an_add_more_button():
    src = (ROOT / "frontend" / "frontend" / "components" / "multichart_page.py").read_text()
    assert 'rx.icon("plus"' in src and "multichart-grid" in src and "Add more chart" in src and "max_width" not in src
    assert "multichart-remove" in src and "M.remove_card" in src and "can_remove" in src
    state = (ROOT / "frontend" / "frontend" / "state" / "multichart_state.py").read_text()
    assert "cards: list[dict] = [_empty_card(1)]" in state and "MAX_CARDS" in state  # starts with a single card
    css = (ROOT / "frontend" / "assets" / "styles.css").read_text()
    assert ".multichart-grid" in css and "repeat(2, minmax(0, 1fr))" in css and "min-height: 520px" in css and ".multichart-add-more" in css


def test_clicking_the_plus_opens_a_coin_search_and_a_picked_coin_shows_its_tradingview_chart():
    src = (ROOT / "frontend" / "frontend" / "components" / "multichart_page.py").read_text()
    assert "M.open_search(card[\"id\"])" in src and "M.choose_coin(card_id" in src and "search_form(" in src  # + opens the search, a row picks the coin
    assert "iframe_light" in src and "iframe_dark" in src and "rx.el.iframe(" in src  # a typed iframe, light / dark
    state = (ROOT / "frontend" / "frontend" / "state" / "multichart_state.py").read_text()
    assert "_resolve_chart_symbol" in state and "tradingview_widget_src" in state and "_fetch_tradingview_dex_symbol" in state


def test_search_coins_matches_name_or_ticker_exact_ticker_first_then_cmc_rank():
    from frontend.state.multichart_state import search_coins

    rows = [
        {"cmc_id": 1, "name": "Bitcoin", "symbol": "BTC", "cmc_rank": 1, "market_cap_usd": 9},
        {"cmc_id": 2, "name": "Wrapped Bitcoin", "symbol": "WBTC", "cmc_rank": 14, "market_cap_usd": 5},
        {"cmc_id": 3, "name": "Bitcoin Cash", "symbol": "BCH", "cmc_rank": 20, "market_cap_usd": 4},
        {"cmc_id": 4, "name": "BTC Fake", "symbol": "BTC", "cmc_rank": 0, "market_cap_usd": 0},
        {"cmc_id": 5, "name": "Ethereum", "symbol": "ETH", "cmc_rank": 2, "market_cap_usd": 8},
    ]
    ident = lambda r: {**r, "price_display": "$1", "change_24h_display": "0%", "change_24h_color": "gray", "slug": "x", "icon_url": ""}
    assert [r["cmc_id"] for r in search_coins(rows, "btc", ident)] == [1, 4, 2]  # exact ticker first, ranked; then name matches
    assert [r["cmc_id"] for r in search_coins(rows, "bitcoin", ident)] == [1, 2, 3]  # CMC rank order
    assert [r["cmc_id"] for r in search_coins(rows, "  eth ", ident)] == [5]
    assert search_coins(rows, "", ident) == [] and search_coins(rows, "zzz", ident) == []
    assert len(search_coins([{**rows[0], "cmc_id": i} for i in range(50)], "btc", ident)) == 20  # at most 20
