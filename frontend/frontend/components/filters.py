"""Top filter bar (moved out of the sidebar) for the narrative + chain filters."""

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
        rx.text("More Narrative", size="1", weight="bold"),
        href="#view-all-narrative",
        underline="none",
        class_name="narrative-pill narrative-pill-more",
    )


def _narrative_pill_slider() -> rx.Component:
    # Drag-to-scroll and the arrow buttons are wired up once, globally, via
    # the delegated listeners in frontend.py's index() (assets/chain_pills.js
    # — shared with the chain dropdown's carousel and the chain filter below).
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


def _chain_filter_pill(name: rx.Var[str]) -> rx.Component:
    return rx.box(
        rx.text(name, size="1"),
        on_click=CoinState.set_chain(name),
        class_name=rx.cond(
            CoinState.active_chain == name,
            "chain-filter-pill chain-filter-pill-active",
            "chain-filter-pill",
        ),
    )


def _more_chains_pill() -> rx.Component:
    # No feature wired up yet — just a placeholder link.
    return rx.link(
        rx.text("More Chain", size="1", weight="bold"),
        href="#view-all-chain",
        underline="none",
        class_name="chain-filter-pill chain-filter-pill-more",
    )


def _chain_filter_slider() -> rx.Component:
    # Same drag/arrow mechanics as the narrative slider (assets/chain_pills.js
    # matches these class names too), just its own top-10-by-count list so it
    # can combine with the narrative filter (AND) instead of replacing it —
    # e.g. "Memes" + "BNB Smart Chain (BEP20)".
    return rx.box(
        rx.box(
            rx.icon("chevron-left", size=14),
            class_name="chain-filter-scroll-btn chain-filter-scroll-left",
        ),
        rx.box(
            rx.foreach(CoinState.chains, _chain_filter_pill),
            _more_chains_pill(),
            class_name="chain-filter-pills-track",
        ),
        rx.box(
            rx.icon("chevron-right", size=14),
            class_name="chain-filter-scroll-btn chain-filter-scroll-right",
        ),
        class_name="chain-filter-pills-wrap",
    )


def filter_bar() -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.icon("list-filter", size=16),
            rx.text("Filters", weight="bold"),
            spacing="2",
            align="center",
        ),
        rx.vstack(
            rx.hstack(
                rx.text(
                    "Group by CMC narrative",
                    size="2",
                    color_scheme="gray",
                    white_space="nowrap",
                    flex_shrink="0",
                    width="160px",
                ),
                _narrative_pill_slider(),
                spacing="5",
                align="center",
                width="100%",
                min_width="0",
            ),
            rx.hstack(
                rx.text(
                    "Filter by chain",
                    size="2",
                    color_scheme="gray",
                    white_space="nowrap",
                    flex_shrink="0",
                    width="160px",
                ),
                _chain_filter_slider(),
                spacing="5",
                align="center",
                width="100%",
                min_width="0",
            ),
            spacing="3",
            width="100%",
            min_width="0",
            margin_left="1.25em",
        ),
        spacing="3",
        align="center",
        width="100%",
        min_width="0",
        padding="0.85em 1em",
        border="1px solid var(--gray-a5)",
        border_radius="8px",
    )
