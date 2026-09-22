"""The main coin-list data table, with market-cap descending order and
pagination baked into CoinState.paged_coins."""

import reflex as rx

from frontend.state import CoinState


def _change_cell(text: rx.Var[str], color: rx.Var[str]) -> rx.Component:
    return rx.table.cell(rx.text(text, color=color))


def _trend_cell(data: rx.Var[list], color: rx.Var[str], is_gold: rx.Var[bool]) -> rx.Component:
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
            class_name=rx.cond(is_gold, "trend-gold-shine", ""),
        )
    )


def _row(row: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(row["rank"]),
        rx.table.cell(
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
            )
        ),
        rx.table.cell(row["price_display"]),
        rx.table.cell(row["market_cap_display"]),
        rx.table.cell(row["volume_display"]),
        _change_cell(row["change_1h_display"], row["change_1h_color"]),
        _change_cell(row["change_24h_display"], row["change_24h_color"]),
        _trend_cell(row["trend_24h_data"], row["trend_24h_color"], row["trend_24h_is_gold"]),
        _change_cell(row["change_7d_display"], row["change_7d_color"]),
        _trend_cell(row["trend_7d_data"], row["trend_7d_color"], row["trend_7d_is_gold"]),
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
                        rx.table.column_header_cell("Rank"),
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("Price"),
                        rx.table.column_header_cell("Market Cap"),
                        rx.table.column_header_cell("24h Volume"),
                        rx.table.column_header_cell("1h"),
                        rx.table.column_header_cell("24h"),
                        rx.table.column_header_cell("24h Price"),
                        rx.table.column_header_cell("7d"),
                        rx.table.column_header_cell("7d Price"),
                    )
                ),
                rx.table.body(rx.foreach(CoinState.paged_coins, _row)),
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
