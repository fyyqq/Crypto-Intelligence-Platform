"""Filter sidebar (1st column, next to the coin table) for the narrative +
chain filters — see frontend.py for the column layout."""

import reflex as rx

from frontend.components.search_form import q, search_form
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
    # Toggles between the default top-20 narratives (categories) and every
    # narrative (all_categories) — both already computed once in
    # load_coins, so this is a free client-side swap, not a re-query. Label
    # flips to "Show less" once expanded, so the same pill also collapses
    # back to the default view.
    return rx.box(
        rx.text(
            rx.cond(CoinState.narratives_expanded, "Show less", "More Narrative"),
            size="1",
            weight="bold",
        ),
        on_click=CoinState.toggle_narratives_expanded,
        class_name="narrative-pill narrative-pill-more",
    )


def _search_box(placeholder: str, value, on_change) -> rx.Component:
    # Searches on submit (Enter / the magnifier), not while typing.
    return search_form(
        rx.input(
            name="q",
            default_value=value,
            key=value,
            placeholder=placeholder,
            enter_key_hint="search",
            size="1",
            radius="full",
            variant="surface",
            width="150px",
            class_name="filter-search",
        ),
        on_submit=lambda form_data: on_change(q(form_data)),
    )


def _section_head(title: str, search: rx.Component) -> rx.Component:
    # Full width: the title on the left, the search box pushed to the right edge.
    return rx.hstack(
        rx.text(title, size="2", color_scheme="gray"),
        search,
        justify="between",
        align="center",
        width="100%",
    )


def _pager(page, count, on_prev, on_next) -> rx.Component:
    """Prev / "page x of y" / next under an expanded or searched list (50 pills a page); hidden for one page."""
    return rx.cond(
        count > 1,
        rx.hstack(
            rx.icon_button(rx.icon("chevron-left", size=14), on_click=on_prev, disabled=page <= 1, size="1", variant="soft", color_scheme="gray", cursor="pointer"),
            rx.text("Page ", page, " of ", count, size="1", color_scheme="gray"),
            rx.icon_button(rx.icon("chevron-right", size=14), on_click=on_next, disabled=page >= count, size="1", variant="soft", color_scheme="gray", cursor="pointer"),
            spacing="3",
            align="center",
            justify="center",
            width="100%",
        ),
        rx.fragment(),
    )


def _no_match(text: str, shown: rx.Var[bool]) -> rx.Component:
    return rx.cond(shown, rx.text(text, size="1", color_scheme="gray"), rx.fragment())


def _narrative_pills() -> rx.Component:
    # Wrapped onto multiple lines, no drag/arrow slider — this filter now
    # lives in the narrower 1st-column sidebar (see frontend.py) instead of
    # a full-width top bar, so a horizontal slider no longer fits.
    return rx.box(
        rx.foreach(CoinState.displayed_categories, _narrative_pill),
        rx.cond(CoinState.narrative_query == "", _more_narratives_pill(), rx.fragment()),
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
    # Same expand/collapse toggle as _more_narratives_pill, over
    # chains/all_chains instead.
    return rx.box(
        rx.text(
            rx.cond(CoinState.chains_expanded, "Show less", "More Chain"),
            size="1",
            weight="bold",
        ),
        on_click=CoinState.toggle_chains_expanded,
        class_name="chain-filter-pill chain-filter-pill-more",
    )


def _chain_filter_pills() -> rx.Component:
    # Same top-20-by-count list as before, combined with the narrative
    # filter (AND) — just wrapped instead of slider-scrolled now too.
    return rx.box(
        rx.foreach(CoinState.displayed_chains, _chain_filter_pill),
        rx.cond(CoinState.chain_query == "", _more_chains_pill(), rx.fragment()),
        class_name="filter-pills-wrap",
    )


def filter_bar() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("list-filter", size=16),
            rx.text("Filters", weight="bold"),
            spacing="2",
            align="center",
            width="100%",
            justify="between",
        ),
        rx.vstack(
            _section_head(
                "Group by narrative",
                _search_box("Search narrative", CoinState.narrative_query, CoinState.set_narrative_query),
            ),
            _narrative_pills(),
            _pager(CoinState.narrative_page_shown, CoinState.narrative_page_count, CoinState.narrative_page_prev, CoinState.narrative_page_next),
            _no_match("No narrative matches.", (CoinState.narrative_query != "") & (CoinState.displayed_categories.length() == 0)),
            spacing="2",
            width="100%",
            align_items="start",
            id="narrative-filters",
        ),
        rx.vstack(
            _section_head(
                "Filter by chain",
                _search_box("Search chain", CoinState.chain_query, CoinState.set_chain_query),
            ),
            _chain_filter_pills(),
            _pager(CoinState.chain_page_shown, CoinState.chain_page_count, CoinState.chain_page_prev, CoinState.chain_page_next),
            _no_match("No chain matches.", (CoinState.chain_query != "") & (CoinState.displayed_chains.length() == 0)),
            spacing="2",
            width="100%",
            align_items="start",
            id="chain-filters",
        ),
        spacing="4",
        width="100%",
        align_items="start",
        padding="0.85em 1em",
        border="1px solid var(--gray-a5)",
        border_radius="8px",
    )
