"""The profit calculator and currency converter: the arithmetic (assets/calculators.js, run with node), the rate view
the page gets from the fx service, and that both tools are listed in the Tools menu."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "frontend" / "assets" / "calculators.js"


def run_js(expr: str):
    code = f"const c = require({json.dumps(str(JS))}); console.log(JSON.stringify({expr}));"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=20, check=True).stdout
    return json.loads(out)


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@needs_node
def test_profit_and_loss_examples():
    assert run_js("c.profit(1000, 50, 1)") == {"change": 500, "result": 1500, "pct": 50, "clamped": False}  # the spec example
    assert run_js("c.profit(1000, 50, -1)")["result"] == 500
    assert run_js("c.profit(4000, 12.5, 1)")["result"] == 4500
    assert run_js("c.profit(1000, 0, 1)")["result"] == 1000
    r = run_js("c.profit(1000, 150, -1)")  # a loss can't exceed 100%
    assert r["result"] == 0 and r["clamped"] is True and r["pct"] == 100
    assert run_js("c.profit(1000, 150, 1)")["result"] == 2500  # a gain can


@needs_node
def test_conversion_both_ways_and_round_trip():
    assert run_js("c.convert(1000, 'USD', 4.08)") == 4080
    assert run_js("c.convert(4080, 'MYR', 4.08)") == pytest.approx(1000)
    assert run_js("c.convert(c.convert(123.45, 'USD', 4.0795), 'MYR', 4.0795)") == pytest.approx(123.45)
    assert run_js("[c.other('USD'), c.other('MYR')]") == ["MYR", "USD"]


@needs_node
def test_number_parsing_and_money_format():
    assert run_js("[c.num('1,000.50'), c.num(' 12 '), c.num('.5'), c.num('abc'), c.num(''), c.num('1e3'), c.num('-5')]") == [1000.5, 12, 0.5, None, None, None, None]
    assert run_js("[c.money(1500, 'USD'), c.money(4080, 'MYR'), c.money(-12.345, 'USD'), c.signed(500, 'USD'), c.signed(-3, 'MYR')]") == [
        "$1,500.00", "RM4,080.00", "-$12.35", "+$500.00", "-RM3.00",
    ]


def test_rate_view_formats_the_rate_and_never_shows_a_missing_one():
    sys.path.insert(0, str(ROOT / "frontend"))
    from frontend.state import calc_state as cs

    view = cs.rate_view({"rate": 4.0795, "note": "Yahoo Finance · live", "as_of": time.time()})
    assert view["rate"] == "4.079500" and view["note"] == "Yahoo Finance · live" and view["time"].endswith("(KL)") and view["error"] == ""
    bad = cs.rate_view(None)
    assert bad["rate"] == "" and "unavailable" in bad["error"]


def test_both_tools_are_in_the_tools_menu_and_have_routes():
    sys.path.insert(0, str(ROOT / "frontend"))
    from frontend.components.tools_page import TOOL_PAGES

    by = {p["href"]: p["title"] for p in TOOL_PAGES}
    assert by["/tools/profit-calculator"] == "Profit Calculator" and by["/tools/currency-converter"] == "Currency Converter"
    src = (ROOT / "frontend" / "frontend" / "frontend.py").read_text()
    assert 'route="/tools/profit-calculator"' in src and 'route="/tools/currency-converter"' in src
