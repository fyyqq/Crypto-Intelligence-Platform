"""/narrative and /chains: every narrative / chain as pills on one page (no pagination, no search)."""

import reflex as rx

from frontend.state import CoinState


def _narrative_link(item: rx.Var[dict]) -> rx.Component:
    # Opens that narrative's news page (/narrative/<slug>).
    return rx.link(
        rx.box(rx.text(item["name"], size="1"), class_name="narrative-pill"),
        href=item["href"],
        underline="none",
        color="inherit",
    )


def _chain_pill(name: rx.Var[str]) -> rx.Component:
    # Shows that chain's coins on the homepage table.
    return rx.box(
        rx.text(name, size="1"),
        on_click=CoinState.open_chain(name),
        class_name="chain-filter-pill",
    )


def _page(title: str, count, pills: rx.Component) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading(title, size="6"),
            rx.badge(count, color_scheme="gray", variant="soft", size="2"),
            align="center",
            spacing="3",
        ),
        rx.cond(
            CoinState.is_loading,
            rx.hstack(*[rx.skeleton(height="26px", width="110px", border_radius="999px") for _ in range(12)], wrap="wrap", spacing="2"),
            rx.box(pills, class_name="filter-pills-wrap", width="100%"),
        ),
        spacing="5",
        width="100%",
        align_items="start",
        padding=["1em", "1em", "1.5em", "2em", "2em"],
    )


def narratives_index_content() -> rx.Component:
    return _page("Narratives", CoinState.narrative_links.length(), rx.foreach(CoinState.narrative_links, _narrative_link))


def chains_index_content() -> rx.Component:
    return _page("Chains", CoinState.chain_names.length(), rx.foreach(CoinState.chain_names, _chain_pill))
