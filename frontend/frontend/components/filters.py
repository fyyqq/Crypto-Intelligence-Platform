"""Filter sidebar (1st column, next to the coin table) for the narrative +
chain filters — see frontend.py for the column layout."""

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
        href="#narratives",
        underline="none",
        class_name="narrative-pill narrative-pill-more",
    )


def _narrative_pills() -> rx.Component:
    # Wrapped onto multiple lines, no drag/arrow slider — this filter now
    # lives in the narrower 1st-column sidebar (see frontend.py) instead of
    # a full-width top bar, so a horizontal slider no longer fits.
    return rx.box(
        rx.foreach(CoinState.categories, _narrative_pill),
        _more_narratives_pill(),
        class_name="filter-pills-wrap",
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
        href="#blockchain",
        underline="none",
        class_name="chain-filter-pill chain-filter-pill-more",
    )


def _chain_filter_pills() -> rx.Component:
    # Same top-20-by-count list as before, combined with the narrative
    # filter (AND) — just wrapped instead of slider-scrolled now too.
    return rx.box(
        rx.foreach(CoinState.chains, _chain_filter_pill),
        _more_chains_pill(),
        class_name="filter-pills-wrap",
    )


def filter_bar() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("list-filter", size=16),
            rx.text("Filters", weight="bold"),
            spacing="2",
            align="center",
        ),
        rx.vstack(
            rx.text("Group by narrative", size="2", color_scheme="gray"),
            _narrative_pills(),
            spacing="2",
            width="100%",
            align_items="start",
        ),
        rx.vstack(
            rx.text("Filter by chain", size="2", color_scheme="gray"),
            _chain_filter_pills(),
            spacing="2",
            width="100%",
            align_items="start",
        ),
        spacing="4",
        width="100%",
        align_items="start",
        padding="0.85em 1em",
        border="1px solid var(--gray-a5)",
        border_radius="8px",
    )
