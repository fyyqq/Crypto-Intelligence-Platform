"""Top filter bar (moved out of the sidebar) for the narrative filter."""

import reflex as rx

from frontend.state import CoinState


def filter_bar() -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.icon("list-filter", size=16),
            rx.text("Filters", weight="bold"),
            spacing="2",
            align="center",
        ),
        rx.divider(orientation="vertical", height="1.5em"),
        rx.text("Group by CMC narrative", size="2", color_scheme="gray"),
        rx.select(
            CoinState.categories,
            value=CoinState.selected_category,
            on_change=CoinState.set_category,
            width="260px",
        ),
        rx.spacer(),
        rx.text("Coins shown", size="2", color_scheme="gray"),
        rx.heading(CoinState.total_shown, size="5"),
        spacing="3",
        align="center",
        width="100%",
        padding="0.85em 1em",
        border="1px solid var(--gray-a5)",
        border_radius="8px",
    )
