"""Top filter bar (moved out of the sidebar) for the narrative filter."""

import reflex as rx

from frontend.state import CoinState


def _narrative_pill(name: rx.Var[str]) -> rx.Component:
    return rx.box(
        rx.text(name, size="1"),
        on_click=CoinState.set_category(name),
        class_name=rx.cond(
            CoinState.active_category == name,
            "narrative-pill narrative-pill-active",
            "narrative-pill",
        ),
    )


def _more_narratives_pill() -> rx.Component:
    # No feature wired up yet — just a placeholder link.
    return rx.link(
        rx.text("More Chain", size="1", weight="bold"),
        href="#view-all-chain",
        underline="none",
        class_name="narrative-pill narrative-pill-more",
    )


def _narrative_pill_slider() -> rx.Component:
    # Drag-to-scroll and the arrow buttons are wired up once, globally, via
    # the delegated listeners in frontend.py's index() (assets/chain_pills.js
    # — shared with the chain dropdown's carousel).
    return rx.box(
        rx.box(
            rx.icon("chevron-left", size=14),
            class_name="narrative-scroll-btn narrative-scroll-left",
        ),
        rx.box(
            rx.foreach(CoinState.categories, _narrative_pill),
            _more_narratives_pill(),
            class_name="narrative-pills-track",
        ),
        rx.box(
            rx.icon("chevron-right", size=14),
            class_name="narrative-scroll-btn narrative-scroll-right",
        ),
        class_name="narrative-pills-wrap",
    )


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
        _narrative_pill_slider(),
        spacing="3",
        align="center",
        width="100%",
        padding="0.85em 1em",
        border="1px solid var(--gray-a5)",
        border_radius="8px",
    )
