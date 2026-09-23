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
    return rx.box(
        rx.text("More Chain", size="1", weight="bold"),
        on_click=CoinState.toggle_narratives_expanded,
        class_name=rx.cond(
            CoinState.narratives_expanded,
            "narrative-pill narrative-pill-more narrative-pill-active",
            "narrative-pill narrative-pill-more",
        ),
    )


def _expand_toggle_button() -> rx.Component:
    return rx.box(
        rx.cond(
            CoinState.narratives_expanded,
            rx.icon("chevron-up", size=14),
            rx.icon("chevron-down", size=14),
        ),
        on_click=CoinState.toggle_narratives_expanded,
        class_name="narrative-scroll-btn narrative-expand-toggle",
    )


def _narrative_pill_slider() -> rx.Component:
    # Drag-to-scroll, the arrow buttons, and hiding an arrow once its end is
    # reached are wired up once, globally, via the delegated listeners in
    # frontend.py's index() (assets/chain_pills.js — shared with the chain
    # dropdown's carousel).
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
        _expand_toggle_button(),
        class_name="narrative-pills-wrap",
    )


def _expanded_narratives_grid() -> rx.Component:
    # Every narrative (~600) as a wrapped grid below the slider — not more
    # pills appended to the horizontal track — capped to 10 per row.
    return rx.box(
        rx.foreach(CoinState.all_categories, _narrative_pill),
        class_name="narrative-expanded-grid",
    )


def filter_bar() -> rx.Component:
    return rx.vstack(
        rx.hstack(
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
        ),
        rx.cond(CoinState.narratives_expanded, _expanded_narratives_grid(), rx.fragment()),
        spacing="3",
        width="100%",
        padding="0.85em 1em",
        border="1px solid var(--gray-a5)",
        border_radius="8px",
    )
