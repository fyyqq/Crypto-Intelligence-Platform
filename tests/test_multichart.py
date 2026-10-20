"""/tools/multichart: the Tools menu entry, the route and the empty two-column grid of + cards."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "frontend"))


def test_multichart_is_the_last_tools_menu_entry_with_a_route():
    from frontend.components.tools_page import TOOL_PAGES

    assert TOOL_PAGES[-1]["href"] == "/tools/multichart" and TOOL_PAGES[-1]["title"] == "Multichart"
    assert 'route="/tools/multichart"' in (ROOT / "frontend" / "frontend" / "frontend.py").read_text()


def test_multichart_page_is_a_two_column_grid_of_empty_plus_cards():
    src = (ROOT / "frontend" / "frontend" / "components" / "tools_page.py").read_text()
    page = src[src.index("def _chart_slot"):src.index("def market_indicators_content")]
    assert 'rx.icon("plus"' in page and 'initial="1", sm="2"' in page and "MULTICHART_SLOTS = 4" in page
    css = (ROOT / "frontend" / "assets" / "styles.css").read_text()
    assert ".multichart-slot" in css and ".multichart-plus" in css
