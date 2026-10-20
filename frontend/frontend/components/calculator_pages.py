"""/tools/pnl-calculator, /tools/currency-converter and /tools/capital-splitter.

Both are plain forms whose arithmetic runs in the browser (assets/calculators.js): every keystroke or button press
answers at once. The live USD -> MYR rate comes from CalcState (fx_service, refreshed every 30 s) and reaches the
script as `data-rate` on the page's `.calc-root`, so a new rate recalculates the result by itself. Only USD and MYR.
Colours use theme tokens (styles.css `.calc-*`)."""

import reflex as rx

from frontend.components.tools_page import _PAGE_PADDING, _page_header
from frontend.state.calc_state import CalcState as C


def _seg(label: str, **attrs) -> rx.Component:
    """One button of a segmented control; assets/calculators.js marks the chosen one."""
    return rx.el.button(label, type="button", class_name="calc-seg", custom_attrs=attrs)


def _field(label: str, control: rx.Component, hint: str = "") -> rx.Component:
    return rx.box(
        rx.el.label(label, class_name="calc-label"),
        control,
        *([rx.text(hint, size="1", color="var(--gray-11)")] if hint else []),
        class_name="calc-field",
    )


def _input(field: str, placeholder: str, prefix: str = "", suffix: str = "", value: str = "", **attrs) -> rx.Component:
    """A number box with an optional prefix (the currency symbol, filled in by the script) and suffix."""
    return rx.box(
        *([rx.el.span(prefix, class_name="calc-affix", custom_attrs={"data-o": "prefix"})] if prefix else []),
        rx.el.input(
            type="text",
            input_mode="decimal",
            placeholder=placeholder,
            default_value=value,
            auto_complete="off",
            spell_check=False,
            class_name="calc-input",
            custom_attrs={"data-f": field, **attrs},
        ),
        *([rx.el.span(suffix, class_name="calc-affix")] if suffix else []),
        class_name="calc-input-wrap",
    )


def _rate_status() -> rx.Component:
    """The live-rate line shared by both pages (also the loading / error state)."""
    return rx.box(
        rx.cond(
            C.fx_rate != "",
            rx.hstack(
                rx.box(class_name="calc-live-dot"),
                rx.text(
                    "Live mid-market rate · ", C.fx_note, " · updated ", C.fx_time,
                    size="1", color="var(--gray-11)",
                ),
                spacing="2",
                align="center",
                wrap="wrap",
            ),
            rx.cond(
                C.fx_error != "",
                rx.text(C.fx_error, size="1", color="var(--red-11)"),
                rx.skeleton(rx.text("Loading the live USD / MYR rate", size="1"), height="16px"),
            ),
        ),
        class_name="calc-status",
    )


_WIDE = "1180px"  # the PNL Calculator page: every section (and its heading) is this wide


def _root(kind: str, *children, wide: bool = False, extra_class: str = "") -> rx.Component:
    """The element the script works on: its data attributes carry the live rate."""
    return rx.box(
        *children,
        class_name=("calc-root calc-wide" if wide else "calc-root") + (" " + extra_class if extra_class else ""),
        custom_attrs={"data-calc": kind, "data-rate": C.fx_rate, "data-note": C.fx_note, "data-time": C.fx_time},
    )


# ---- Profit calculator ------------------------------------------------------------------------------

def _dca_section() -> rx.Component:
    """Crypto DCA tiers against an all-time high: the capital you put in, the ATH, and one row per buy tier with what you
    spend, the token price, the loss at that drop and the balance left after the loss."""
    controls = rx.box(
        _field("Capital amount", _input("budget", "1000", prefix="$", value="1000")),
        _field(
            "All-time high (ATH) price",
            rx.box(
                rx.el.span("$", class_name="calc-affix", custom_attrs={"data-o": "prefix2"}),
                rx.el.input(type="text", input_mode="decimal", placeholder="100", default_value="100", auto_complete="off", spell_check=False,
                            class_name="calc-input", custom_attrs={"data-f": "ath"}),
                class_name="calc-input-wrap",
            ),
        ),
        class_name="calc-dca-top",
    )
    table = rx.box(
        rx.box(
            rx.heading("Buy tiers", size="4"),
            rx.el.button("+ Add tier", type="button", class_name="calc-chip", custom_attrs={"data-add-tier": "1"}),
            class_name="calc-dca-head",
        ),
        rx.text(
            "Buy in tiers as the price falls from the all-time high: each tier is how far below the ATH it is and how much "
            "of your capital you spend there.",
            size="2",
            color="var(--gray-11)",
        ),
        controls,
        rx.box(
            rx.el.table(
                rx.el.thead(
                    rx.el.tr(
                        rx.el.th("Tier"),
                        rx.el.th("Drop from ATH"),
                        rx.el.th("Budget %"),
                        rx.el.th("Spent"),
                        rx.el.th("Token price"),
                        rx.el.th("Loss %"),
                        rx.el.th("Loss amount"),
                        rx.el.th("Balance after loss"),
                        rx.el.th(""),
                    )
                ),
                rx.el.tbody(custom_attrs={"data-o": "tiers"}),
                class_name="calc-table calc-dca-table",
            ),
            class_name="calc-scroll",
        ),
        rx.el.button("+ Add more", type="button", class_name="calc-add-more", custom_attrs={"data-add-tier": "1"}),
        rx.el.div("", class_name="calc-status-line", custom_attrs={"data-o": "status"}),
        rx.text(
            "Loss % follows each tier's drop from the ATH. Loss amount = your capital x that %, and Balance after loss = "
            "your capital - that loss. (Hover a Loss % to see how far the price falls from the previous tier.)",
            size="1",
            color="var(--gray-11)",
        ),
        class_name="calc-card",
    )
    return _root("dca", table, wide=True)


def pnl_calculator_content() -> rx.Component:
    form = rx.box(
        rx.heading("Your trade", size="4"),
        _field(
            "Currency",
            rx.box(_seg("USD ($)", **{"data-cur": "USD"}), _seg("MYR (RM)", **{"data-cur": "MYR"}), class_name="calc-segs"),
        ),
        _field("Capital", _input("capital", "1000", prefix="$")),
        _field(
            "Result of the trade",
            rx.box(
                _seg("Profit  +", **{"data-sign": "1"}),
                _seg("Loss  −", **{"data-sign": "-1"}),
                class_name="calc-segs",
            ),
        ),
        _field("Percentage", _input("pct", "50", suffix="%")),
        class_name="calc-card",
    )
    result = rx.box(
        rx.text("Result", size="2", color="var(--gray-11)"),
        rx.el.div("—", class_name="calc-big", custom_attrs={"data-o": "result"}),
        rx.el.div("", class_name="calc-sub", custom_attrs={"data-o": "change"}),
        rx.el.div("", class_name="calc-formula", custom_attrs={"data-o": "formula"}),
        rx.box(
            rx.text("In the other currency", size="1", color="var(--gray-11)"),
            rx.el.div("", class_name="calc-other", custom_attrs={"data-o": "other"}),
            class_name="calc-other-box",
        ),
        rx.el.div("", class_name="calc-warn", custom_attrs={"data-o": "warn"}),
        class_name="calc-card calc-result",
    )
    return rx.vstack(
        rx.box(_page_header("PNL Calculator", "Enter your capital and a profit or loss percentage to see the result, in USD or MYR, and plan your buy tiers below the all-time high."), width="100%", max_width=_WIDE),
        _root(
            "profit",
            rx.box(form, result, class_name="calc-two"),
            _rate_status(),
            wide=True,
        ),
        _dca_section(),
        spacing="5",
        align="center",
        width="100%",
        padding=_PAGE_PADDING,
    )


# ---- Currency converter -----------------------------------------------------------------------------

def _sum_card() -> rx.Component:
    """Add or subtract amounts ($1000 + $1000 - $250) in the one currency picked with the USD / MYR switch; the total is also shown in the other currency."""
    return _root(
        "sum",
        rx.box(
            rx.box(
                rx.heading("Add / subtract amounts", size="4"),
                rx.el.button("+ Add amount", type="button", class_name="calc-chip", custom_attrs={"data-add-term": "1"}),
                class_name="calc-dca-head",
            ),
            rx.text(
                "Pick a currency, type the main value first, then the amounts with + or - between them. The % next to the total is the rise or drop from the main value. Example: $1,000 - $250 = $750 (-25%).",
                size="2",
                color="var(--gray-11)",
            ),
            rx.box(custom_attrs={"data-o": "terms"}, class_name="calc-terms"),
            _field(
                "Currency",
                rx.box(_seg("USD ($)", **{"data-cur": "USD"}), _seg("MYR (RM)", **{"data-cur": "MYR"}), class_name="calc-segs"),
            ),
            rx.box(
                rx.box(
                    rx.el.div("—", class_name="calc-big", custom_attrs={"data-o": "result"}),
                    rx.el.span("", class_name="calc-pct", custom_attrs={"data-o": "pct"}),
                    class_name="calc-big-row",
                ),
                rx.el.div("", class_name="calc-formula", custom_attrs={"data-o": "formula"}),
                rx.el.div("", class_name="calc-formula", custom_attrs={"data-o": "other"}),
                rx.el.div("", class_name="calc-rates", custom_attrs={"data-o": "rates"}),
                class_name="calc-result-block",
            ),
            class_name="calc-card",
        ),
        extra_class="calc-area-sum",
    )


def currency_converter_content() -> rx.Component:
    card = rx.box(
        rx.box(
            _field("Amount", _input("amount", "1000", prefix="$", value="1000")),
            _field(
                "From",
                rx.box(_seg("USD", **{"data-cur": "USD"}), _seg("MYR", **{"data-cur": "MYR"}), class_name="calc-segs"),
            ),
            rx.el.button(
                rx.icon("arrow-left-right", size=18),
                type="button",
                title="Swap currencies",
                aria_label="Swap currencies",
                class_name="calc-swap",
                custom_attrs={"data-swap": "1"},
            ),
            _field("To", rx.el.div("", class_name="calc-to", custom_attrs={"data-o": "to-label"})),
            class_name="calc-convert-row",
        ),
        rx.box(
            rx.el.div("—", class_name="calc-big", custom_attrs={"data-o": "result"}),
            rx.el.div("", class_name="calc-formula", custom_attrs={"data-o": "formula"}),
            rx.el.div("", class_name="calc-rates", custom_attrs={"data-o": "rates"}),
            class_name="calc-result-block",
        ),
        class_name="calc-card calc-area-conv",
    )
    table = rx.box(
        rx.heading("Quick conversions", size="3"),
        rx.el.table(
            rx.el.thead(rx.el.tr(rx.el.th("", custom_attrs={"data-o": "th-from"}), rx.el.th("", custom_attrs={"data-o": "th-to"}))),
            rx.el.tbody(custom_attrs={"data-o": "table"}),
            class_name="calc-table",
        ),
        class_name="calc-card calc-area-table",
    )
    return rx.vstack(
        rx.box(_page_header("Currency Converter", "Convert between US dollars and Malaysian ringgit at the live mid-market rate."), width="100%", max_width="980px"),
        rx.box(
            _root("convert", card, table),
            _sum_card(),
            class_name="calc-two calc-two-convert",
        ),
        rx.box(
            _rate_status(),
            rx.text(
                "The mid-market rate is the real exchange rate (no bank margin). A bank or card may charge a fee or a different rate.",
                size="1",
                color="var(--gray-11)",
            ),
            display="flex",
            flex_direction="column",
            gap="16px",
            width="100%",
            max_width="980px",
        ),
        spacing="5",
        align="center",
        width="100%",
        padding=_PAGE_PADDING,
    )


# ---- Capital splitter -------------------------------------------------------------------------------

# Every preset lists the smaller percentages first.
_PRESETS = [("Equal 2", "50,50"), ("20 / 20 / 60", "20,20,60"), ("30 / 30 / 40", "30,30,40"), ("20 / 30 / 50", "20,30,50"), ("25 x 4", "25,25,25,25"), ("10 / 20 / 30 / 40", "10,20,30,40")]


def capital_splitter_content() -> rx.Component:
    controls = rx.box(
        rx.box(
            _field("Currency", rx.box(_seg("USD ($)", **{"data-cur": "USD"}), _seg("MYR (RM)", **{"data-cur": "MYR"}), class_name="calc-segs")),
            _field("Capital", _input("capital", "1000", prefix="$", value="1000")),
            class_name="calc-split-top",
        ),
        rx.box(
            _field("Split", rx.box(_seg("Equal parts", **{"data-mode": "equal"}), _seg("Custom %", **{"data-mode": "custom"}), class_name="calc-segs")),
            _field(
                "Number of parts",
                rx.box(
                    rx.el.button("−", type="button", aria_label="Fewer parts", class_name="calc-step", custom_attrs={"data-step": "-1"}),
                    rx.el.div("3", class_name="calc-count", custom_attrs={"data-o": "count"}),
                    rx.el.button("+", type="button", aria_label="More parts", class_name="calc-step", custom_attrs={"data-step": "1"}),
                    class_name="calc-stepper",
                ),
            ),
            class_name="calc-split-top",
        ),
        rx.box(
            rx.text("Quick splits", size="1", color="var(--gray-11)"),
            rx.box(
                *[rx.el.button(label, type="button", class_name="calc-chip", custom_attrs={"data-preset": pcts}) for label, pcts in _PRESETS],
                rx.el.button("Make equal", type="button", class_name="calc-chip", custom_attrs={"data-equalize": "1"}),
                class_name="calc-chips",
            ),
            class_name="calc-field",
        ),
        class_name="calc-card",
    )
    table = rx.box(
        rx.heading("Your parts", size="4"),
        rx.box(
            rx.el.table(
                rx.el.thead(
                    rx.el.tr(
                        rx.el.th("Part"),
                        rx.el.th("Percent"),
                        rx.el.th("Amount"),
                        rx.el.th("", custom_attrs={"data-o": "th-oth"}),
                    )
                ),
                rx.el.tbody(custom_attrs={"data-o": "parts"}),
                rx.el.tfoot(
                    rx.el.tr(
                        rx.el.td("Total"),
                        rx.el.td("", custom_attrs={"data-o": "total-pct"}),
                        rx.el.td("", custom_attrs={"data-o": "total"}),
                        rx.el.td(""),
                    )
                ),
                class_name="calc-table calc-parts-table",
            ),
            class_name="calc-scroll",
        ),
        rx.el.div("", class_name="calc-status-line", custom_attrs={"data-o": "status"}),
        class_name="calc-card",
    )
    return rx.vstack(
        rx.box(
            _page_header("Capital Splitter", "Split your capital into equal parts or your own percentages (for example 20% + 20% + 60%), in USD or MYR."),
            width="100%",
            max_width="980px",
        ),
        _root("split", rx.box(controls, table, class_name="calc-two calc-two-split"), _rate_status()),
        spacing="5",
        align="center",
        width="100%",
        padding=_PAGE_PADDING,
    )
