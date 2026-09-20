"""The main coin-list data table, with market-cap descending order and
pagination baked into CoinState.paged_coins."""

import reflex as rx

from frontend.state import CoinState


def _change_cell(text: rx.Var[str], color: rx.Var[str]) -> rx.Component:
    return rx.table.cell(rx.text(text, color=color))


def _row(row: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(row["rank"]),
        rx.table.cell(
            rx.text(row["name"], weight="bold"), " ", rx.text(row["symbol"], color_scheme="gray")
        ),
        rx.table.cell(row["price_display"]),
        rx.table.cell(row["market_cap_display"]),
        rx.table.cell(row["volume_display"]),
        _change_cell(row["change_1h_display"], row["change_1h_color"]),
        _change_cell(row["change_24h_display"], row["change_24h_color"]),
        _change_cell(row["change_7d_display"], row["change_7d_color"]),
        rx.table.cell(rx.text(row["narratives"], size="1", color_scheme="gray")),
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
                    rx.table.column_header_cell("7d"),
                    rx.table.column_header_cell("Narratives"),
                )
            ),
            rx.table.body(rx.foreach(CoinState.paged_coins, _row)),
            variant="surface",
            width="100%",
        ),
        _pagination(),
        width="100%",
    )
