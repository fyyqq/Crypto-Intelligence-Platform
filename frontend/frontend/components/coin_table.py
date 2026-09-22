"""The main coin-list data table, with market-cap descending order and
pagination baked into CoinState.paged_coins."""

import reflex as rx

from frontend.state import CoinState


def _change_cell(text: rx.Var[str], color: rx.Var[str]) -> rx.Component:
    return rx.table.cell(rx.text(text, color=color), vertical_align="middle")


def _sort_icon(sort_key: str) -> rx.Component:
    is_active_col = CoinState.sort_key == sort_key
    up_active = is_active_col & (CoinState.sort_direction == "desc")
    down_active = is_active_col & (CoinState.sort_direction == "asc")
    return rx.vstack(
        rx.icon(
            "chevron-up",
            size=11,
            color=rx.cond(up_active, "var(--accent-9)", "var(--gray-8)"),
        ),
        rx.icon(
            "chevron-down",
            size=11,
            color=rx.cond(down_active, "var(--accent-9)", "var(--gray-8)"),
        ),
        spacing="0",
        align="center",
        margin_top="-2px",
        margin_bottom="-2px",
    )


def _sortable_header(label: str, sort_key: str) -> rx.Component:
    return rx.table.column_header_cell(
        rx.hstack(
            rx.text(label),
            _sort_icon(sort_key),
            spacing="1",
            align="center",
            cursor="pointer",
        ),
        on_click=CoinState.set_sort(sort_key),
    )


def _trend_cell(data: rx.Var[list], color: rx.Var[str], shine_class: rx.Var[str]) -> rx.Component:
    return rx.table.cell(
        rx.box(
            rx.recharts.line_chart(
                rx.recharts.line(
                    data_key="v",
                    stroke=color,
                    dot=False,
                    stroke_width=2,
                    is_animation_active=False,
                ),
                data=data,
                width=90,
                height=32,
            ),
            class_name=shine_class.to(str),
        ),
        vertical_align="middle",
    )


def _row(row: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(row["rank"], vertical_align="middle"),
        rx.table.cell(
            rx.vstack(
                rx.hstack(
                    rx.image(
                        src=row["icon_url"],
                        width="22px",
                        height="22px",
                        border_radius="50%",
                    ),
                    rx.text(row["name"], weight="bold"),
                    rx.text(row["symbol"], color_scheme="gray"),
                    spacing="2",
                    align="center",
                ),
                rx.badge(row["primary_narrative"], variant="outline", size="1", color_scheme="gray"),
                spacing="1",
                align="start",
            ),
            vertical_align="middle",
        ),
        rx.table.cell(row["price_display"], vertical_align="middle"),
        rx.table.cell(row["market_cap_display"], vertical_align="middle"),
        rx.table.cell(row["volume_display"], vertical_align="middle"),
        _change_cell(row["change_1h_display"], row["change_1h_color"]),
        _change_cell(row["change_24h_display"], row["change_24h_color"]),
        _change_cell(row["change_7d_display"], row["change_7d_color"]),
        _trend_cell(row["trend_24h_data"], row["trend_24h_color"], row["trend_24h_shine"]),
        _trend_cell(row["trend_7d_data"], row["trend_7d_color"], row["trend_7d_shine"]),
    )


def _pagination() -> rx.Component:
    return rx.hstack(
        rx.button("Prev", on_click=CoinState.prev_page, disabled=CoinState.page <= 1),
        rx.text("Page ", CoinState.page, " / ", CoinState.total_pages),
        rx.button(
            "Next", on_click=CoinState.next_page, disabled=CoinState.page >= CoinState.total_pages
        ),
        spacing="3",
        align="center",
        justify="end",
        width="100%",
        padding_y="0.75em",
    )


def coin_table() -> rx.Component:
    return rx.vstack(
        rx.box(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        _sortable_header("Rank", "rank"),
                        rx.table.column_header_cell("Name"),
                        _sortable_header("Price", "price_raw"),
                        _sortable_header("Market Cap", "market_cap_usd"),
                        _sortable_header("24H Volume", "volume_raw"),
                        _sortable_header("1H", "pct_1h_raw"),
                        _sortable_header("24H", "pct_24h_raw"),
                        _sortable_header("7D", "pct_7d_raw"),
                        rx.table.column_header_cell("24H Price"),
                        rx.table.column_header_cell("7D Price"),
                    )
                ),
                rx.table.body(rx.foreach(CoinState.sorted_paged_coins, _row)),
                variant="surface",
                width="100%",
            ),
            height="calc(100vh - 300px)",
            overflow="auto",
            width="100%",
        ),
        _pagination(),
        width="100%",
    )
