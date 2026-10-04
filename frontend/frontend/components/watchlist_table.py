"""The /watchlist page's own coin table — same visual design as the
homepage's coin_table.py (columns, badges, trend sparklines), but scoped to
CoinState.watchlist_coins instead of the full/filtered universe, with a new
star column (before Rank) whose click removes that row from the watchlist.

No narrative/chain sidebar, search, sorting, or pagination here — a personal
watchlist is small and unfiltered by design; those are homepage-table
concerns tied to browsing all ~8,000 coins, not this page's."""

import reflex as rx

from frontend.components.coin_table import (
    _COL_FROM_LG,
    _COL_FROM_MD,
    _COL_FROM_SM,
    _STICKY_HEADER_STYLE,
    _change_cell,
    _chain_badge,
    _name_link,
    _narrative_badge,
    _trend_cell,
)
from frontend.state import CoinState


def _watchlist_star_cell(row: dict) -> rx.Component:
    # Every row here is already-watchlisted, so this star is always filled —
    # unlike coin_detail.py's star (which reflects membership either way),
    # clicking this one is always a removal. stop_propagation keeps it from
    # also firing the row's own on_click (navigate to the coin's page).
    return rx.table.cell(
        rx.icon(
            "star",
            size=16,
            color="var(--amber-9)",
            fill="var(--amber-9)",
            cursor="pointer",
        ),
        on_click=[CoinState.toggle_watchlist(row["cmc_id"]), rx.stop_propagation],
        vertical_align="middle",
    )


def _row(row: dict) -> rx.Component:
    return rx.table.row(
        _watchlist_star_cell(row),
        rx.table.cell(row["rank"], vertical_align="middle"),
        rx.table.cell(
            rx.vstack(
                _name_link(row),
                _narrative_badge(row),
                _chain_badge(row),
                spacing="2",
                align="start",
            ),
            vertical_align="middle",
        ),
        rx.table.cell(row["price_display"], vertical_align="middle"),
        rx.table.cell(row["market_cap_display"], vertical_align="middle", display=_COL_FROM_MD),
        rx.table.cell(row["volume_display"], vertical_align="middle", display=_COL_FROM_LG),
        _change_cell(row["change_1h_display"], row["change_1h_color"], display=_COL_FROM_LG),
        _change_cell(row["change_24h_display"], row["change_24h_color"]),
        _change_cell(row["change_7d_display"], row["change_7d_color"], display=_COL_FROM_SM),
        _trend_cell(row["trend_24h_data"], row["trend_24h_color"], row["trend_24h_shine"], display=_COL_FROM_LG),
        _trend_cell(row["trend_7d_data"], row["trend_7d_color"], row["trend_7d_shine"], display=_COL_FROM_LG),
        class_name="coin-row-linked",
        cursor="pointer",
        _hover={"background_color": "var(--gray-a3)"},
    )


def _table_header_row() -> rx.Component:
    return rx.table.row(
        rx.table.column_header_cell("", **_STICKY_HEADER_STYLE),
        rx.table.column_header_cell("Rank", **_STICKY_HEADER_STYLE),
        rx.table.column_header_cell("Name", **_STICKY_HEADER_STYLE),
        rx.table.column_header_cell("Price", **_STICKY_HEADER_STYLE),
        rx.table.column_header_cell("Market Cap", display=_COL_FROM_MD, **_STICKY_HEADER_STYLE),
        rx.table.column_header_cell("24H Volume", display=_COL_FROM_LG, **_STICKY_HEADER_STYLE),
        rx.table.column_header_cell("1H", display=_COL_FROM_LG, **_STICKY_HEADER_STYLE),
        rx.table.column_header_cell("24H", **_STICKY_HEADER_STYLE),
        rx.table.column_header_cell("7D", display=_COL_FROM_SM, **_STICKY_HEADER_STYLE),
        rx.table.column_header_cell("24H Price", display=_COL_FROM_LG, **_STICKY_HEADER_STYLE),
        rx.table.column_header_cell("7D Price", display=_COL_FROM_LG, **_STICKY_HEADER_STYLE),
    )


def _empty_state() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon("star", size=32, color="var(--gray-8)"),
            rx.text("Your watchlist is empty", size="4", weight="bold"),
            rx.text(
                "Click the star icon on any coin's own page to add it here.",
                size="2",
                color_scheme="gray",
            ),
            spacing="2",
            align="center",
        ),
        height="50vh",
        width="100%",
    )


def _table_header_bar() -> rx.Component:
    return rx.hstack(
        rx.heading("My Watchlists", size="5"),
        rx.spacer(),
        rx.hstack(
            rx.text("Total Coins:", size="2", color_scheme="gray"),
            rx.heading(CoinState.watchlist_count, size="5"),
            spacing="2",
            align="center",
        ),
        align="center",
        justify="between",
        wrap="wrap",
        width="100%",
        style={"row-gap": "0.5em"},
    )


def watchlist_table() -> rx.Component:
    return rx.vstack(
        _table_header_bar(),
        rx.cond(
            CoinState.has_watchlist_coins,
            rx.box(
                rx.table.root(
                    rx.table.header(_table_header_row()),
                    rx.table.body(rx.foreach(CoinState.watchlist_coins, _row)),
                    variant="surface",
                    width="100%",
                ),
                height="max-content",
                width="100%",
                class_name="coin-table-scroll-fix",
            ),
            _empty_state(),
        ),
        width="100%",
    )
