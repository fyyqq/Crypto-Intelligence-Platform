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
    src = (ROOT / "frontend" / "frontend" / "components" / "tools_page.py").read_text()
    page = src[src.index("def _chart_slot"):src.index("def market_indicators_content")]
    assert 'rx.icon("plus"' in page and "multichart-grid" in page and "Add more chart" in page and "max_width" not in page
    state = (ROOT / "frontend" / "frontend" / "state" / "multichart_state.py").read_text()
    assert "cards: list[int] = [1]" in state and "MAX_CARDS" in state  # starts with a single card
    css = (ROOT / "frontend" / "assets" / "styles.css").read_text()
    assert "can_remove" in state and "def remove_card" in state and "multichart-remove" in page and "MultichartState.remove_card" in page
    assert ".multichart-grid" in css and "repeat(2, minmax(0, 1fr))" in css and "min-height: 520px" in css and ".multichart-add-more" in css
