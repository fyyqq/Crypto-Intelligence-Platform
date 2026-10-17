"""/portfolio: the owner's MEXC spot portfolio (read-only), the Portfolio view of the account area.

Top: total balance with its 24h change, four figures (unrealized profit/loss, cash in stablecoins, value held by
open orders, coins held) and an allocation ring. Below: holdings (live price, 24h, value, average buy price,
profit/loss, share of the wallet), open orders (limit / stop) and the latest fills. Colours use the theme tokens
so it follows light/dark mode. State: frontend/state/portfolio_state.py; data: app/services/mexc_service.py."""

import reflex as rx

from frontend.state.portfolio_state import PortfolioState as S


def _coin_icon(row, size: str = "28px") -> rx.Component:
    return rx.cond(
        row["icon"] != "",
        rx.image(src=row["icon"], alt="", width=size, height=size, border_radius="50%", flex_shrink="0", loading="lazy"),
        rx.box(rx.text(row["initial"], size="1", weight="bold"), class_name="pf-coin-initial", width=size, height=size),
    )


def _coin_cell(row, sub=None) -> rx.Component:
    """Logo + ticker (+ a second line); a link to the coin page when the site knows the coin."""
    label = rx.hstack(
        _coin_icon(row),
        rx.vstack(
            rx.text(row["asset"], size="2", weight="bold", color="var(--gray-12)"),
            rx.text(sub if sub is not None else row["name"], size="1", color="var(--gray-11)", class_name="pf-ellipsis"),
            spacing="0",
            min_width="0",
        ),
        spacing="2",
        align="center",
        min_width="0",
    )
    return rx.cond(row["href"] != "", rx.link(label, href=row["href"], underline="none", class_name="pf-coin-link"), label)


def _card(*children, **props) -> rx.Component:
    class_name = "pf-card " + props.pop("class_name", "")
    return rx.box(*children, class_name=class_name, **props)


def _section_title(icon: str, title: str, *extra) -> rx.Component:
    return rx.hstack(
        rx.icon(icon, size=17, color="var(--gray-11)"),
        rx.text(title, size="3", weight="bold", color="var(--gray-12)"),
        *extra,
        spacing="2",
        align="center",
        margin_bottom="0.75em",
    )


def _side_badge(row) -> rx.Component:
    return rx.badge(row["side"], color_scheme=row["side_color"], variant="soft", radius="full", size="1")


# ------------------------------------------------------------------------------------------------- top


def _header() -> rx.Component:
    return rx.flex(
        rx.hstack(
            rx.heading("Portfolio", size="7", color="var(--gray-12)"),
            rx.badge(rx.icon("shield-check", size=12), "MEXC Spot · read-only", variant="soft", radius="full", color_scheme="gray"),
            rx.cond(S.pf_demo, rx.badge("Demo data", color_scheme="amber", variant="solid", radius="full")),
            spacing="3",
            align="center",
            wrap="wrap",
        ),
        rx.hstack(
            rx.cond(S.pf_summary["updated"], rx.text("Updated ", S.pf_summary["updated"], size="1", color="var(--gray-11)")),
            rx.icon_button(
                rx.icon("refresh-cw", size=15, class_name=rx.cond(S.pf_refreshing, "pf-spin", "")),
                on_click=S.refresh_portfolio,
                variant="soft",
                color_scheme="gray",
                size="2",
                radius="full",
                title="Refresh from MEXC now",
                aria_label="Refresh from MEXC now",
                cursor="pointer",
            ),
            spacing="2",
            align="center",
        ),
        justify="between",
        align="center",
        gap="0.75em",
        wrap="wrap",
        width="100%",
    )


def _stat(label: str, icon: str, value, sub=None, color="var(--gray-12)") -> rx.Component:
    return rx.box(
        rx.hstack(rx.icon(icon, size=14, color="var(--gray-10)"), rx.text(label, size="1", color="var(--gray-11)"), spacing="1", align="center"),
        rx.text(value, size="4", weight="bold", color=color, class_name="pf-num", margin_top="0.35em"),
        rx.cond(sub, rx.text(sub, size="1", color="var(--gray-11)", class_name="pf-num")) if sub is not None else rx.fragment(),
        class_name="pf-stat",
    )


def _currency_button(code: str) -> rx.Component:
    return rx.el.button(
        code,
        type="button",
        on_click=S.set_pf_currency(code),
        class_name=rx.cond(S.pf_currency == code, "pf-cur-btn pf-cur-active", "pf-cur-btn"),
        aria_pressed=rx.cond(S.pf_currency == code, "true", "false"),
        title="Show this card in " + code,
    )


def _currency_toggle() -> rx.Component:
    """MYR / USD buttons (MYR is the default since 2026-10-18). They change this card only: the live USD -> MYR rate is applied to
    its money amounts by the server (fx_service); the tables below stay in USD."""
    return rx.box(_currency_button("MYR"), _currency_button("USD"), class_name="pf-cur", role="group", aria_label="Card currency")


def _hero() -> rx.Component:
    return _card(
        rx.flex(
            rx.text("Total balance", size="2", color="var(--gray-11)"),
            _currency_toggle(),
            justify="between",
            align="center",
            gap="0.75em",
            width="100%",
        ),
        rx.text(S.pf_summary["total"], class_name="pf-total pf-num"),
        rx.hstack(
            rx.box(
                rx.icon(rx.cond(S.pf_summary["change"].contains("-"), "trending-down", "trending-up"), size=14),
                rx.text(S.pf_summary["change"], " (", S.pf_summary["change_pct"], ")", size="2", weight="medium", class_name="pf-num"),
                class_name="pf-pill",
                color=S.pf_summary["change_color"],
            ),
            rx.text("last 24h", size="1", color="var(--gray-11)"),
            spacing="2",
            align="center",
        ),
        rx.cond(S.pf_fx_note != "", rx.text(S.pf_fx_note, size="1", color="var(--gray-11)", margin_top="0.5em", class_name="pf-num")),
        rx.cond(S.pf_fx_error != "", rx.text(S.pf_fx_error, size="1", color="var(--amber-11)", margin_top="0.5em")),
        rx.grid(
            _stat("Unrealized P/L", "chart-line", S.pf_summary["pnl"], S.pf_summary["pnl_pct"], S.pf_summary["pnl_color"]),
            _stat("Stablecoins", "banknote", S.pf_summary["cash"], S.pf_summary["cash_pct"]),
            _stat("In open orders", "list-checks", S.pf_summary["in_orders"], S.pf_summary["orders_count"] + " open"),
            _stat("Coins held", "coins", S.pf_summary["coins"], S.pf_summary["dust"]),
            # 2 x 2 until the hero card is wide enough (xl) for four tiles without cutting the labels.
            columns=rx.breakpoints(initial="2", xl="4"),
            spacing="3",
            width="100%",
            margin_top="1.25em",
        ),
        rx.cond(
            S.pf_summary["cost_note"] != "",
            rx.text(rx.icon("info", size=13, display="inline", vertical_align="-2px"), " ", S.pf_summary["cost_note"], size="1", color="var(--gray-11)", margin_top="0.75em"),
        ),
        class_name="pf-hero",
    )


def _allocation() -> rx.Component:
    return _card(
        _section_title("chart-pie", "Allocation"),
        rx.flex(
            rx.box(
                rx.box(
                    rx.text(S.pf_summary["coins"], size="6", weight="bold", color="var(--gray-12)", class_name="pf-num"),
                    rx.text("coins", size="1", color="var(--gray-11)"),
                    class_name="pf-ring-hole",
                ),
                class_name="pf-ring",
                style={"background": S.pf_ring},
            ),
            rx.vstack(
                rx.foreach(
                    S.pf_alloc,
                    lambda a: rx.hstack(
                        rx.box(class_name="pf-dot", style={"background": a["color"]}),
                        rx.text(a["label"], size="2", color="var(--gray-12)", flex="1"),
                        rx.text(a["pct"], size="2", color="var(--gray-11)", class_name="pf-num"),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                ),
                spacing="2",
                flex="1",
                min_width="140px",
                width="100%",
            ),
            gap="1.5em",
            align="center",
            direction=rx.breakpoints(initial="column", xs="row"),
            width="100%",
        ),
    )


_CHART_BLUE = "#3B82F6"  # readable on light and dark
# Recharts has no typed prop for these in this Reflex version, so they go in as raw JS functions (one per currency
# symbol: the popup renders the chart for the selected one).
def _money_tick(symbol: str) -> rx.Var:
    return rx.Var(f"(v) => '{symbol}' + Number(v).toLocaleString('en-US', {{maximumFractionDigits: 0}})")


def _money_tooltip(symbol: str) -> rx.Var:
    return rx.Var(
        f"(v) => ['{symbol}' + Number(v).toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}}), 'Total balance']"
    )


def _balance_area(data, height, full: bool, symbol: str = "$") -> rx.Component:
    parts = [
        rx.el.svg.defs(
            rx.el.svg.linear_gradient(
                rx.el.svg.stop(offset="0%", stop_color=_CHART_BLUE, stop_opacity=0.35),
                rx.el.svg.stop(offset="100%", stop_color=_CHART_BLUE, stop_opacity=0.02),
                id="pfBalanceFill" + ("Full" if full else "Card"),
                x1="0", y1="0", x2="0", y2="1",
            )
        ),
        rx.recharts.area(
            data_key="v",
            type_="monotone",
            stroke=_CHART_BLUE,
            stroke_width=2,
            fill="url(#pfBalanceFill" + ("Full" if full else "Card") + ")",
            dot=False,
            active_dot={"r": 4} if full else False,
            is_animation_active=False,
        ),
    ]
    if full:
        parts += [
            rx.recharts.cartesian_grid(stroke_dasharray="3 3", vertical=False, stroke="rgba(128,128,128,0.25)"),
            rx.recharts.x_axis(data_key="t", min_tick_gap=56, tick_line=False, axis_line=False, custom_attrs={"tick": {"fontSize": 11, "fill": "#8b8d98"}}),
            rx.recharts.y_axis(domain=["auto", "auto"], width=72, tick_line=False, axis_line=False, custom_attrs={"tickFormatter": _money_tick(symbol), "tick": {"fontSize": 11, "fill": "#8b8d98"}}),
            rx.recharts.graphing_tooltip(
                content_style={"background": "var(--color-panel-solid)", "border": "1px solid var(--gray-a5)", "borderRadius": "8px", "color": "var(--gray-12)"},
                label_style={"color": "var(--gray-11)"},
                custom_attrs={"formatter": _money_tooltip(symbol)},
            ),
        ]
    else:
        parts.append(rx.recharts.y_axis(domain=["dataMin", "dataMax"], hide=True))
    return rx.recharts.area_chart(*parts, data=data, width="100%", height=height, margin={"top": 6, "right": 4, "left": 4, "bottom": 0})


def _balance_card() -> rx.Component:
    """Under Allocation: the total balance over the last 7 days (recorded every 5 min + the live total). A click
    opens the full chart."""
    return rx.box(
        rx.flex(
            rx.vstack(
                rx.text("Total balance · 7D", size="1", color="var(--gray-11)"),
                rx.text(rx.cond(S.pf_hist_card_info.contains("value"), S.pf_hist_card_info["value"], S.pf_summary["total"]), size="6", weight="bold", color="var(--gray-12)", class_name="pf-num"),
                rx.cond(
                    S.pf_hist_card.length() > 1,
                    rx.text(S.pf_hist_card_info["change"], " (", S.pf_hist_card_info["change_pct"], ")", size="1", weight="medium", color=S.pf_hist_card_info["color"], class_name="pf-num"),
                ),
                spacing="0",
            ),
            rx.icon("maximize-2", size=15, color="var(--gray-10)"),
            justify="between",
            align="start",
            width="100%",
        ),
        rx.cond(
            S.pf_hist_card.length() > 1,
            rx.box(_balance_area(S.pf_hist_card, 96, False), margin_top="0.5em", width="100%"),
            rx.text("Collecting data: the balance is saved every 5 minutes, the line appears after the first two readings.", size="1", color="var(--gray-11)", margin_top="0.75em"),
        ),
        on_click=S.open_balance_chart,
        class_name="pf-card pf-balance-card",
        role="button",
        tab_index=0,
        title="Open the balance chart",
    )


_HIST_RANGE_BUTTONS = [("24h", "24H"), ("7d", "7D"), ("1m", "1M"), ("full", "Full Chart")]


def _balance_popup() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.flex(
                rx.vstack(
                    rx.dialog.title("Total balance", margin="0", size="4"),
                    rx.cond(
                        S.pf_hist_info.contains("value"),
                        rx.hstack(
                            rx.text(S.pf_hist_info["value"], size="6", weight="bold", color="var(--gray-12)", class_name="pf-num"),
                            rx.text(S.pf_hist_info["change"], " (", S.pf_hist_info["change_pct"], ")", size="2", weight="medium", color=S.pf_hist_info["color"], class_name="pf-num"),
                            spacing="2",
                            align="baseline",
                            wrap="wrap",
                        ),
                    ),
                    spacing="1",
                ),
                rx.hstack(
                    rx.box(
                        *[
                            rx.el.button(
                                label,
                                type="button",
                                on_click=S.set_pf_hist_range(key),
                                class_name=rx.cond(S.pf_hist_range == key, "pf-cur-btn pf-cur-active", "pf-cur-btn"),
                                aria_pressed=rx.cond(S.pf_hist_range == key, "true", "false"),
                            )
                            for key, label in _HIST_RANGE_BUTTONS
                        ],
                        class_name="pf-cur pf-range",
                        role="group",
                        aria_label="Chart range",
                    ),
                    rx.dialog.close(rx.icon_button(rx.icon("x", size=16), variant="ghost", color_scheme="gray", aria_label="Close", cursor="pointer")),
                    spacing="2",
                    align="center",
                ),
                justify="between",
                align="start",
                gap="0.75em",
                wrap="wrap",
                width="100%",
            ),
            rx.box(
                rx.cond(
                    S.pf_hist_points.length() > 1,
                    rx.cond(S.pf_currency == "MYR", _balance_area(S.pf_hist_points, 380, True, "RM"), _balance_area(S.pf_hist_points, 380, True, "$")),
                    rx.center(
                        rx.text(
                            rx.cond(S.pf_hist_loading, "Loading…", "Not enough readings in this range yet: the server saves your balance every 5 minutes."),
                            size="2",
                            color="var(--gray-11)",
                            text_align="center",
                        ),
                        height="380px",
                    ),
                ),
                margin_top="1em",
                width="100%",
                class_name=rx.cond(S.pf_hist_loading, "pf-hist-chart pf-hist-loading", "pf-hist-chart"),
            ),
            rx.flex(
                rx.cond(
                    S.pf_hist_info.contains("high"),
                    rx.text("High ", S.pf_hist_info["high"], " · Low ", S.pf_hist_info["low"], size="1", color="var(--gray-11)", class_name="pf-num"),
                ),
                rx.cond(
                    (S.pf_currency == "MYR") & (S.pf_fx_note != ""),
                    rx.text("In MYR at today's rate: ", S.pf_fx_note, size="1", color="var(--gray-11)", class_name="pf-num"),
                ),
                rx.cond(S.pf_hist_since != "", rx.text("Recording since ", S.pf_hist_since, " (Kuala Lumpur)", size="1", color="var(--gray-11)")),
                justify="between",
                gap="0.5em",
                wrap="wrap",
                margin_top="0.5em",
                width="100%",
            ),
            max_width="min(960px, calc(100vw - 32px))",
            width="100%",
        ),
        open=S.pf_hist_open,
        on_open_change=S.set_pf_hist_open,
    )


# ---------------------------------------------------------------------------------------------- tables


def _th(label: str, align: str = "right") -> rx.Component:
    return rx.table.column_header_cell(label, text_align=align, class_name="pf-th")


def _td(*children, align: str = "right", **props) -> rx.Component:
    return rx.table.cell(*children, text_align=align, class_name="pf-td pf-num", **props)


def _holding_row(h) -> rx.Component:
    return rx.table.row(
        _td(_coin_cell(h), align="left"),
        _td(
            rx.text(h["amount"], size="2", color="var(--gray-12)"),
            rx.cond(h["locked"] != "", rx.text(h["locked"], size="1", color="var(--gray-11)")),
        ),
        _td(rx.text(h["price"], size="2", color="var(--gray-12)")),
        _td(rx.text(h["pct_24h"], size="2", color=h["pct_color"])),
        _td(rx.text(h["value"], size="2", weight="bold", color="var(--gray-12)")),
        _td(
            rx.cond(
                h["stable"] == "",
                rx.vstack(
                    rx.text(h["avg"], size="2", color="var(--gray-12)"),
                    rx.cond(h["avg_source"] != "", rx.text(h["avg_source"], size="1", color="var(--gray-11)")),
                    spacing="0",
                    align="end",
                ),
            ),
        ),
        _td(
            rx.cond(
                h["pnl"] != "",
                rx.vstack(
                    rx.text(h["pnl"], size="2", weight="medium", color=h["pnl_color"]),
                    rx.text(h["pnl_pct"], size="1", color=h["pnl_color"]),
                    spacing="0",
                    align="end",
                ),
                rx.text("—", size="2", color="var(--gray-10)"),
            ),
        ),
        _td(
            rx.vstack(
                rx.text(h["alloc"], size="2", color="var(--gray-12)"),
                rx.box(rx.box(class_name="pf-bar-fill", style={"width": h["alloc_width"]}), class_name="pf-bar"),
                spacing="1",
                align="end",
            ),
        ),
        class_name="pf-tr",
    )


def _holdings() -> rx.Component:
    return _card(
        _section_title("wallet", "Holdings", rx.text(S.pf_summary["dust"], size="1", color="var(--gray-11)")),
        rx.box(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        _th("Coin", "left"), _th("Amount"), _th("Price"), _th("24h"), _th("Value"), _th("Avg buy"), _th("P/L"), _th("Share"),
                    ),
                ),
                rx.table.body(rx.foreach(S.pf_holdings, _holding_row)),
                variant="ghost",
                size="2",
                width="100%",
            ),
            class_name="pf-scroll",
        ),
    )


def _order_row(o) -> rx.Component:
    return rx.table.row(
        _td(_coin_cell(o, o["pair"]), align="left"),
        _td(_side_badge(o), align="left"),
        _td(rx.text(o["type"], size="2", color="var(--gray-12)"), align="left"),
        _td(rx.text(o["price"], size="2", weight="medium", color="var(--gray-12)")),
        _td(rx.text(rx.cond(o["trigger"] != "", o["trigger"], "—"), size="2", color="var(--gray-11)")),
        _td(rx.text(o["amount"], size="2", color="var(--gray-12)"), rx.text(o["filled"], " filled", size="1", color="var(--gray-11)")),
        _td(rx.text(o["value"], size="2", color="var(--gray-12)")),
        _td(rx.text(o["distance"], size="2", color="var(--gray-11)")),
        _td(rx.text(o["placed"], size="1", color="var(--gray-11)", white_space="nowrap")),
        class_name="pf-tr",
    )


def _orders() -> rx.Component:
    return _card(
        _section_title("list-checks", "Open orders", rx.badge(S.pf_summary["orders_count"], variant="soft", radius="full", color_scheme="gray")),
        rx.cond(
            S.pf_orders.length() > 0,
            rx.box(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            _th("Coin", "left"), _th("Side", "left"), _th("Type", "left"), _th("Price"), _th("Trigger"), _th("Amount"), _th("Value"),
                            _th("From market"), _th("Placed"),
                        ),
                    ),
                    rx.table.body(rx.foreach(S.pf_orders, _order_row)),
                    variant="ghost",
                    size="2",
                    width="100%",
                ),
                class_name="pf-scroll",
            ),
            rx.text("No open orders on MEXC.", size="2", color="var(--gray-11)"),
        ),
        rx.cond(
            S.pf_summary["unmatched"] != "",
            rx.text(rx.icon("info", size=13, display="inline", vertical_align="-2px"), " ", S.pf_summary["unmatched"], size="1", color="var(--gray-11)", margin_top="0.75em"),
        ),
    )


def _trade_row(t) -> rx.Component:
    return rx.table.row(
        _td(rx.text(t["time"], size="1", color="var(--gray-11)", white_space="nowrap"), align="left"),
        _td(_coin_cell(t), align="left"),
        _td(_side_badge(t), align="left"),
        _td(rx.text(t["price"], size="2", color="var(--gray-12)")),
        _td(rx.text(t["amount"], size="2", color="var(--gray-12)")),
        _td(rx.text(t["value"], size="2", color="var(--gray-12)")),
        _td(rx.text(t["fee"], size="1", color="var(--gray-11)")),
        class_name="pf-tr",
    )


def _trades() -> rx.Component:
    from frontend.components.news_page import _pagination_row  # the same pager as the news and index pages

    return _card(
        _section_title("history", "Recent fills", rx.text("coins you hold, last 30 days", size="1", color="var(--gray-11)")),
        rx.cond(
            S.pf_trades.length() > 0,
            rx.box(
                rx.table.root(
                    rx.table.header(rx.table.row(_th("Time", "left"), _th("Coin", "left"), _th("Side", "left"), _th("Price"), _th("Amount"), _th("Total"), _th("Fee"))),
                    rx.table.body(rx.foreach(S.pf_trades, _trade_row)),
                    variant="ghost",
                    size="2",
                    width="100%",
                ),
                class_name="pf-scroll",
            ),
            rx.text("No trades in the last 30 days.", size="2", color="var(--gray-11)"),
        ),
        rx.cond(
            S.pf_trade_pages > 1,
            rx.box(
                _pagination_row(S.trades_first, S.trades_prev, S.trades_next, S.trades_last, S.pf_trade_page, S.pf_trade_pages),
                margin_top="0.75em",
            ),
        ),
    )


def _cost_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Average buy price · ", S.pf_cost_asset),
            rx.dialog.description(
                "Your average buy price for ",
                S.pf_cost_asset,
                " in USD (as shown in the MEXC app). It replaces the price worked out from your last 30 days of trades.",
                size="2",
                color="var(--gray-11)",
            ),
            rx.form(
                rx.vstack(
                    rx.input(
                        rx.input.slot("$"),
                        value=S.pf_cost_input,
                        on_change=S.set_pf_cost_input,
                        placeholder="0.00",
                        input_mode="decimal",
                        size="3",
                        width="100%",
                        auto_focus=True,
                    ),
                    rx.cond(S.pf_cost_error != "", rx.text(S.pf_cost_error, size="1", color="var(--red-11)")),
                    rx.hstack(
                        rx.button("Use trade history", type="button", variant="ghost", color_scheme="gray", on_click=S.clear_cost),
                        rx.spacer(),
                        rx.dialog.close(rx.button("Cancel", type="button", variant="soft", color_scheme="gray")),
                        rx.button("Save", type="submit"),
                        spacing="3",
                        width="100%",
                        align="center",
                    ),
                    spacing="3",
                    width="100%",
                    margin_top="1em",
                ),
                on_submit=lambda _: S.save_cost(),
                width="100%",
            ),
            max_width="420px",
        ),
        open=S.pf_cost_open,
        on_open_change=S.set_pf_cost_open,
    )


# ----------------------------------------------------------------------------------------------- states


def _message(icon: str, title: str, body) -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.box(rx.icon(icon, size=26, color="var(--gray-11)"), class_name="pf-empty-icon"),
            rx.heading(title, size="5", color="var(--gray-12)"),
            rx.text(body, size="2", color="var(--gray-11)", text_align="center", max_width="420px"),
            spacing="3",
            align="center",
        ),
        min_height="50vh",
        width="100%",
    )


def _skeleton() -> rx.Component:
    return rx.vstack(
        rx.grid(rx.skeleton(height="230px", border_radius="14px"), rx.skeleton(height="230px", border_radius="14px"), columns=rx.breakpoints(initial="1", md="2"), spacing="4", width="100%"),
        rx.skeleton(height="320px", border_radius="14px", width="100%"),
        spacing="4",
        width="100%",
    )


def _dashboard() -> rx.Component:
    return rx.vstack(
        _header(),
        rx.cond(
            S.pf_error != "",
            rx.callout(S.pf_error, icon="triangle_alert", color_scheme="amber", size="1", width="100%"),
        ),
        rx.cond(
            S.pf_summary.contains("total"),
            rx.vstack(
                rx.box(_hero(), rx.vstack(_allocation(), _balance_card(), spacing="4", width="100%", min_width="0"), class_name="pf-top"),
                _holdings(),
                _orders(),
                _trades(),
                rx.text(
                    rx.icon("lock", size=12, display="inline", vertical_align="-1px"),
                    " Read-only connection: this site can see your MEXC balances and orders but cannot trade, withdraw or move funds.",
                    size="1",
                    color="var(--gray-11)",
                ),
                spacing="4",
                width="100%",
            ),
            rx.cond(S.pf_loaded, _message("plug-zap", "MEXC data unavailable", "Nothing could be read from MEXC yet. See the message above."), _skeleton()),
        ),
        _cost_dialog(),
        _balance_popup(),
        spacing="4",
        width="100%",
    )


def portfolio_view() -> rx.Component:
    return rx.box(
        rx.cond(
            ~S.pf_loaded,
            _skeleton(),
            rx.cond(
                ~S.pf_allowed,
                _message("wallet", "Portfolio", "Exchange portfolios are not available for this account."),
                rx.cond(
                    ~S.pf_configured,
                    _message("plug-zap", "MEXC is not connected", "Add a read-only MEXC API key (MEXC_API_KEY, MEXC_API_SECRET) to this server's .env."),
                    _dashboard(),
                ),
            ),
        ),
        class_name="profile-main profile-view-portfolio pf-page",
    )


# ------------------------------------------------------------------------------------- coin page box


def _coin_order_row(o) -> rx.Component:
    return rx.hstack(
        _side_badge(o),
        rx.vstack(
            rx.text(o["type"], " · ", o["price"], size="2", weight="medium", color="var(--gray-12)", class_name="pf-num"),
            rx.text(
                o["amount"],
                " ",
                o["asset"],
                rx.cond(o["trigger"] != "", rx.fragment(" · trigger ", o["trigger"])),
                rx.cond(o["distance"] != "", rx.fragment(" · ", o["distance"])),
                size="1",
                color="var(--gray-11)",
                class_name="pf-num",
            ),
            spacing="0",
            min_width="0",
        ),
        spacing="2",
        align="center",
        width="100%",
        padding="0.5em 0.75em",
        border_radius="8px",
        background="var(--gray-a3)",
    )


def _legend_key(color: str, label: str, dashed: bool = False) -> rx.Component:
    return rx.hstack(
        rx.box(class_name="pf-key pf-key-dashed" if dashed else "pf-key", style={"background": color} if not dashed else {"borderTopColor": color}),
        rx.text(label, size="1", color="var(--gray-11)", white_space="nowrap"),
        spacing="1",
        align="center",
    )


def coin_chart_lines_bar() -> rx.Component:
    """Above the coin page chart, for MEXC viewers on a coin with a MEXC holding or order: "My lines" (the
    Lightweight Charts view with your price lines, default) / "TradingView" (the normal widget), the line legend
    and, in the lines view, its timeframe buttons."""
    from frontend.state.portfolio_state import CHART_INTERVALS

    return rx.cond(
        S.coin_mexc_visible & S.coin_mexc_has_lines,
        rx.flex(
            rx.box(
                *[
                    rx.el.button(
                        label,
                        type="button",
                        on_click=S.set_coin_chart_mode(mode),
                        class_name=rx.cond(S.coin_mexc_chart_mode == mode, "pf-cur-btn pf-cur-active", "pf-cur-btn"),
                        aria_pressed=rx.cond(S.coin_mexc_chart_mode == mode, "true", "false"),
                    )
                    for mode, label in (("lines", "My lines"), ("tv", "TradingView"))
                ],
                class_name="pf-cur pf-chart-mode",
                role="group",
                aria_label="Chart view",
            ),
            rx.cond(
                S.coin_mexc_chart_mode == "lines",
                rx.box(
                    *[
                        rx.el.button(
                            label,
                            type="button",
                            on_click=S.set_coin_chart_interval(interval),
                            class_name=rx.cond(S.coin_mexc_interval == interval, "pf-cur-btn pf-cur-active", "pf-cur-btn"),
                            aria_pressed=rx.cond(S.coin_mexc_interval == interval, "true", "false"),
                        )
                        for label, interval in CHART_INTERVALS
                    ],
                    class_name="pf-cur pf-chart-tf",
                    role="group",
                    aria_label="Lines chart timeframe",
                ),
            ),
            rx.hstack(
                _legend_key("#2962FF", "Avg buy"),
                _legend_key("#22C55E", "Limit"),
                _legend_key("#EF4444", "Stop-loss", dashed=True),
                spacing="3",
                align="center",
                wrap="wrap",
                margin_left="auto",
            ),
            gap="0.6em",
            align="center",
            wrap="wrap",
            width="100%",
        ),
    )


def coin_chart_lines_view() -> rx.Component:
    """The main chart area in "My lines" mode: the coin's MEXC USDT pair (Lightweight Charts, drawn by
    assets/mexc_lines_chart.js from the data-* attributes) with your average buy (blue), limit (green) and
    stop-loss (red, dashed) lines. Pan and zoom like a normal chart."""
    return rx.box(
        rx.box(class_name="pf-lines-canvas"),
        rx.text("Loading chart…", size="2", color="var(--gray-11)", class_name="pf-lines-empty"),
        class_name="pf-lines-chart",
        custom_attrs={
            "data-candles": S.coin_mexc_candles,
            "data-lines": S.coin_mexc_lines,
            "data-fit": S.selected_coin["symbol"].to(str) + ":" + S.coin_mexc_interval,
        },
        width="100%",
        height="100%",
    )


def coin_chart_lines_active() -> rx.Var:
    """True when the main chart area shows the lines view instead of the TradingView widget."""
    return S.coin_mexc_visible & S.coin_mexc_has_lines & (S.coin_mexc_chart_mode == "lines")


def coin_mexc_section() -> rx.Component:
    """Coin page, above Alerts, for MEXC viewers only: what you hold of this coin and its open orders."""
    return rx.cond(
        S.coin_mexc_visible,
        rx.vstack(
            rx.hstack(
                rx.icon("wallet", size=16, color="var(--gray-11)"),
                rx.text("Your MEXC", size="2", weight="bold"),
                rx.spacer(),
                rx.link("Portfolio", rx.icon("arrow-right", size=13), href="/portfolio", size="1", underline="none", display="inline-flex", align_items="center", gap="2px"),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.cond(
                ~S.coin_mexc_loaded,
                rx.skeleton(height="44px", width="100%", border_radius="8px"),
                rx.fragment(
                    rx.cond(
                        S.coin_mexc_holding.contains("amount"),
                        rx.box(
                            rx.hstack(
                                rx.text(S.coin_mexc_holding["amount"], size="2", weight="bold", color="var(--gray-12)", class_name="pf-num"),
                                rx.spacer(),
                                rx.text(S.coin_mexc_holding["value"], size="2", color="var(--gray-12)", class_name="pf-num"),
                                width="100%",
                            ),
                            rx.hstack(
                                rx.text("Avg buy ", S.coin_mexc_holding["avg"], size="1", color="var(--gray-11)", class_name="pf-num"),
                                rx.spacer(),
                                rx.text(S.coin_mexc_holding["pnl"], size="1", weight="medium", color=S.coin_mexc_holding["pnl_color"], class_name="pf-num"),
                                width="100%",
                            ),
                            width="100%",
                            padding="0.5em 0.75em",
                            border_radius="8px",
                            background="var(--gray-a3)",
                        ),
                    ),
                    rx.cond(
                        S.coin_mexc_orders.length() > 0,
                        rx.vstack(rx.foreach(S.coin_mexc_orders, _coin_order_row), spacing="2", width="100%"),
                        rx.text("No open MEXC orders for this coin.", size="1", color_scheme="gray"),
                    ),
                    rx.cond(S.coin_mexc_error != "", rx.text(S.coin_mexc_error, size="1", color="var(--amber-11)")),
                ),
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
    )
