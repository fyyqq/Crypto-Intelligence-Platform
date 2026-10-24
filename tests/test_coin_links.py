"""Coin page: the Coinglass liquidation heat map link above the Alerts section."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_heatmap_link_sits_above_alerts_and_points_at_coinglass_with_the_ticker():
    page = (ROOT / "frontend" / "frontend" / "components" / "coin_detail.py").read_text()
    assert page.index("_heatmap_link(),") < page.index("_alerts_section(),")  # right above the Alerts section
    assert "is_external=True" in page and 'rel="noopener noreferrer"' in page and "Liquidation Heat Map" in page
    state = (ROOT / "frontend" / "frontend" / "state" / "coin_state.py").read_text()
    assert "https://www.coinglass.com/pro/futures/LiquidationHeatMap?coin=" in state and "quote(symbol, safe='')" in state
