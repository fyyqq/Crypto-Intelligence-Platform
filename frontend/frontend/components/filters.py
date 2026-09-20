"""Sidebar narrative-filter control."""

import reflex as rx

from frontend.state import CoinState


def narrative_filter() -> rx.Component:
    return rx.vstack(
        rx.text("Filters", size="5", weight="bold"),
        rx.text("Group by CMC narrative", size="2", color_scheme="gray"),
        rx.select(
            CoinState.categories,
            value=CoinState.selected_category,
            on_change=CoinState.set_category,
            width="100%",
        ),
        rx.divider(),
        rx.text("Coins shown", size="2", color_scheme="gray"),
        rx.heading(CoinState.total_shown, size="6"),
        spacing="3",
        width="260px",
        padding="1em",
        align_items="stretch",
    )
