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
def test_percentage_change_from_the_main_value():
    assert run_js("c.pctChange(1000, 2000)") == 100  # $1000 + $1000
    assert run_js("c.pctChange(1000, 750)") == -25  # $1000 - $250
    assert run_js("c.pctChange(1000, 1000)") == 0
    assert run_js("c.pctChange(200, -100)") == -150  # can go below zero
    assert run_js("c.pctChange(0, 50)") is None  # no main value, no percentage


@needs_node
def test_add_and_subtract_amounts_left_to_right():
    assert run_js("c.sumTerms([{amount:1000,op:'+'},{amount:1000,op:'+'}])") == 2000  # $1000 + $1000
    assert run_js("c.sumTerms([{amount:1000,op:'+'},{amount:1000,op:'+'},{amount:250,op:'-'}])") == 1750
    assert run_js("c.sumTerms([{amount:500,op:'-'},{amount:700,op:'-'}])") == -200  # the first term's operator is ignored
    assert run_js("c.sumTerms([{amount:100.1,op:'+'},{amount:0.2,op:'-'}])") == pytest.approx(99.9)
    assert run_js("c.sumTerms([{amount:42,op:'-'}])") == 42


def test_add_amounts_card_is_on_the_converter_page_only():
    src = (ROOT / "frontend" / "frontend" / "components" / "calculator_pages.py").read_text()
    conv = src[src.index("def currency_converter_content"):src.index("# ---- Capital splitter")]
    assert "_sum_card()" in conv and '"sum"' in src[src.index("def _sum_card"):src.index("def currency_converter_content")]
    assert "_sum_card" not in src[src.index("def capital_splitter_content"):]


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
    assert by["/tools/pnl-calculator"] == "PNL Calculator" and "/tools/profit-calculator" not in by and by["/tools/currency-converter"] == "Currency Converter"
    src = (ROOT / "frontend" / "frontend" / "frontend.py").read_text()
    assert 'route="/tools/pnl-calculator"' in src and 'route="/tools/currency-converter"' in src
    assert 'route="/tools/profit-calculator"' in src and 'rx.redirect("/tools/pnl-calculator")' in src  # the old URL redirects


@needs_node
def test_capital_split_amounts_add_up_to_the_cent():
    assert run_js("c.splitAmounts(1000, [100/3, 100/3, 100/3])") == [333.34, 333.33, 333.33]  # never 999.99
    assert run_js("c.splitAmounts(1000, [20, 20, 60])") == [200, 200, 600]  # the 20% + 20% + 60% example
    assert run_js("c.splitAmounts(4000, [20, 20, 60])") == [800, 800, 2400]
    assert run_js("c.splitAmounts(100, [100/7, 100/7, 100/7, 100/7, 100/7, 100/7, 100/7])") == [14.29, 14.29, 14.29, 14.29, 14.28, 14.28, 14.28]
    assert sum(run_js("c.splitAmounts(0.05, [50, 50])")) == pytest.approx(0.05)
    assert run_js("c.splitAmounts(1000, [20, 20])") == [200, 200]  # percentages that do not reach 100 are not scaled up
    assert run_js("c.splitAmounts(1000, [70, 50])") == [700, 500]  # nor scaled down when over 100 (the page warns)


@needs_node
def test_equal_percentages_add_up_to_exactly_100():
    assert run_js("c.equalPcts(3)") == [33.33, 33.33, 33.34]
    assert run_js("c.equalPcts(2)") == [50, 50] and run_js("c.equalPcts(4)") == [25, 25, 25, 25]
    for n in range(2, 13):
        assert sum(run_js(f"c.equalPcts({n})")) == pytest.approx(100)


def test_capital_splitter_is_in_the_tools_menu_with_a_route():
    sys.path.insert(0, str(ROOT / "frontend"))
    from frontend.components.tools_page import TOOL_PAGES

    assert {p["href"]: p["title"] for p in TOOL_PAGES}["/tools/capital-splitter"] == "Capital Splitter"
    assert 'route="/tools/capital-splitter"' in (ROOT / "frontend" / "frontend" / "frontend.py").read_text()


def test_every_quick_split_lists_the_smaller_numbers_first_and_adds_up_to_100():
    sys.path.insert(0, str(ROOT / "frontend"))
    from frontend.components.calculator_pages import _PRESETS

    for label, pcts in _PRESETS:
        nums = [float(x) for x in pcts.split(",")]
        assert nums == sorted(nums), label  # smallest first
        assert sum(nums) == 100 and label.replace(" ", "").replace("/", ",").split(",")[:len(nums)] != [], label
    assert "30,30,40" in [p for _, p in _PRESETS] and "20,30,50" in [p for _, p in _PRESETS]
    assert "40,30,30" not in [p for _, p in _PRESETS] and "50,30,20" not in [p for _, p in _PRESETS]


@needs_node
def test_dca_plan_from_the_example():
    """Budget 1000, ATH 100, tiers -75% / 30%, -80% / 30%, -85% / 40%."""
    r = run_js("c.dca(1000, 100, [{drop: 75, pct: 30}, {drop: 80, pct: 30}, {drop: 85, pct: 40}])")
    prices = [x["price"] for x in r["rows"]]
    assert prices == pytest.approx([25, 20, 15])
    assert [x["spent"] for x in r["rows"]] == pytest.approx([300, 300, 400])
    assert [x["tokens"] for x in r["rows"]] == pytest.approx([12, 15, 400 / 15])
    assert [x["vsPrev"] for x in r["rows"]] == pytest.approx([-75, -20, -25])  # -75% from the ATH, then the real falls between tiers
    assert r["invested"] == pytest.approx(1000) and r["tokens"] == pytest.approx(12 + 15 + 400 / 15)
    assert r["avg"] == pytest.approx(1000 / (12 + 15 + 400 / 15)) and r["avgDrop"] == pytest.approx(-81.3665, abs=1e-3)
    # the loss at each tier's drop from the ATH, on the capital put in, and the balance left after it
    assert [x["loss"] for x in r["rows"]] == pytest.approx([750, 800, 850]) and [x["balance"] for x in r["rows"]] == pytest.approx([250, 200, 150])


@needs_node
def test_dca_edge_cases():
    partial = run_js("c.dca(1000, 100, [{drop: 50, pct: 20}])")
    assert partial["invested"] == 200 and partial["pctSum"] == 20 and partial["avg"] == pytest.approx(50) and partial["avgDrop"] == pytest.approx(-50)
    bad = run_js("c.dca(1000, 100, [{drop: 100, pct: 50}, {drop: -5, pct: 10}, {drop: null, pct: 10}, {drop: 60, pct: 40}])")
    assert [x["valid"] for x in bad["rows"]] == [False, False, False, True]  # a drop of 100% (price 0), negative or empty is skipped
    assert bad["invested"] == pytest.approx(400) and bad["rows"][3]["vsPrev"] == pytest.approx(-60) and bad["rows"][3]["fromAth"] is True  # no valid tier before it: measured from the ATH
    none = run_js("c.dca(1000, 100, [])")
    assert none["avg"] is None and none["tokens"] == 0
    rise = run_js("c.dca(100, 10, [{drop: 80, pct: 50}, {drop: 60, pct: 50}])")  # a shallower second tier: the price is higher
    assert rise["rows"][1]["vsPrev"] == pytest.approx(100)


def test_the_pnl_page_sections_share_one_width_and_the_tier_table_has_an_add_more_button():
    src = (ROOT / "frontend" / "frontend" / "components" / "calculator_pages.py").read_text()
    assert src.count("wide=True") == 2 and "max_width=_WIDE" in src  # the calculator, the tier card and the heading
    assert 'class_name="calc-add-more"' in src and '"+ Add more"' in src
    css = (ROOT / "frontend" / "assets" / "styles.css").read_text()
    dca_src = src[src.index("def _dca_section"):src.index("def pnl_calculator_content")]
    assert "data-cur" not in dca_src and "MYR" not in dca_src  # the buy tiers table has no currency switch: it is USD
    assert ".calc-root.calc-wide { max-width: 1180px; }" in css and 'calc-root[data-calc="dca"] { max-width' not in css
    assert "var MAX_TIERS = 20;" in JS.read_text()
