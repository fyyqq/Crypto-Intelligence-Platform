"""Header-level global search — sits left of the dark-mode toggle in
_header_bar (see frontend.py). Separate from coin_table.py's own
_coin_search (which re-filters the homepage table in place): this one is a
CMC-style autocomplete popover, works from any page, and searches coins by
name/ticker today with an "Articles" (news) section reserved for once that
feature exists.
"""

import reflex as rx

from frontend.state import CoinState


def _global_search_result_row(row: rx.Var[dict]) -> rx.Component:
    return rx.hstack(
        rx.image(src=row["icon_url"], width="22px", height="22px", border_radius="50%", flex_shrink="0"),
        # name+ticker share a truncating group (min_width=0 lets a flex
        # child shrink below its content size at all, and the name itself
        # gets the ellipsis) so a long name (e.g. "Artificial
        # Superintelligence Alliance") never wraps onto its own line and
        # drags the ticker down with it — previously that wrap made the
        # ticker land alone on a second line, reading as centered instead
        # of pinned to the row's left side.
        rx.hstack(
            rx.text(row["name"], size="2", weight="bold", class_name="global-search-result-name"),
            rx.text(row["symbol"], size="2", color_scheme="gray", flex_shrink="0"),
            spacing="1",
            align="center",
            min_width="0",
            flex="1",
        ),
        # Real price (from this coin's already-synced row — see
        # CoinState.global_search_matches, which reads all_coins +
        # coin_overrides, the same data live_sync_loop/detail_sync_loop
        # already keep fresh; no extra fetch triggered by typing a query)
        # stacked above a smaller 24h-change line, right-aligned.
        rx.vstack(
            rx.text(row["price_display"], size="2", weight="medium"),
            rx.text(row["change_24h_display"], size="1", color=row["change_24h_color"]),
            spacing="0",
            align="end",
            flex_shrink="0",
        ),
        spacing="2",
        align="center",
        width="100%",
        on_click=CoinState.go_to_coin_from_search(row["symbol"]),
        class_name="global-search-result-row",
    )


def _global_search_empty_state() -> rx.Component:
    return rx.text(
        "No coins found for \"", CoinState.global_search_query, "\"",
        size="2",
        color_scheme="gray",
        class_name="global-search-empty",
    )


def _global_search_show_more() -> rx.Component:
    return rx.cond(
        CoinState.global_search_has_more,
        rx.text(
            "Show more",
            size="2",
            weight="medium",
            on_click=CoinState.expand_global_search_results,
            class_name="global-search-show-more",
        ),
        rx.fragment(),
    )


def _global_search_coin_section() -> rx.Component:
    return rx.cond(
        CoinState.global_search_has_matches,
        rx.fragment(
            rx.foreach(CoinState.global_search_results, _global_search_result_row),
            _global_search_show_more(),
        ),
        _global_search_empty_state(),
    )


def _global_search_articles_section() -> rx.Component:
    # No news backend exists yet (see CLAUDE.md's Feature 2 notes) — this
    # section renders the real "Articles" heading now so the dropdown's
    # structure is already in place, with an honest empty state instead of
    # fabricated results, matching this codebase's placeholder-link
    # convention in filters.py's "More Narrative"/"More Chain" pills.
    return rx.box(
        rx.text("Articles", size="1", weight="bold", color_scheme="gray", class_name="global-search-section-label"),
        rx.text("News search isn't available yet", size="1", color_scheme="gray", class_name="global-search-empty"),
        class_name="global-search-articles-section",
    )


def _global_search_dropdown() -> rx.Component:
    return rx.box(
        _global_search_coin_section(),
        _global_search_articles_section(),
        class_name="global-search-dropdown",
    )


def global_search() -> rx.Component:
    return rx.box(
        rx.icon("search", size=14, class_name="global-search-icon"),
        rx.debounce_input(
            # A raw rx.el.input, not the Radix-themed rx.input — Radix's own
            # rt-TextFieldRoot background/border rules live inside a CSS
            # @layer that outranks a plain class override (see
            # coin_table.py::_coin_search's own note on this), which would
            # fight the transparent background this search bar needs. A raw
            # element has no such layer to fight.
            rx.el.input(
                value=CoinState.global_search_query,
                on_change=CoinState.set_global_search_query,
                placeholder="Search",
                id="global-search-input-field",
                class_name="global-search-input",
                auto_complete="off",
                spell_check=False,
            ),
            debounce_timeout=250,
        ),
        rx.cond(
            CoinState.global_search_query == "",
            # The "/" shortcut only means anything with a physical keyboard
            # — hidden at the smallest breakpoint (phone widths) where it'd
            # otherwise fight the input itself for space, rather than
            # hiding the whole search bar there the way an earlier version
            # of this header did.
            rx.text("/", size="1", class_name="global-search-kbd", display=["none", "flex", "flex", "flex", "flex"]),
            rx.icon(
                "x",
                size=14,
                class_name="global-search-clear-icon",
                on_click=CoinState.reset_global_search,
            ),
        ),
        rx.cond(
            CoinState.global_search_query != "",
            _global_search_dropdown(),
            rx.fragment(),
        ),
        # Hidden — clicked from JS (assets/chain_pills.js) on a real click
        # outside .global-search-container, closing the dropdown without
        # the on_blur race described on CoinState.reset_global_search.
        rx.box(id="global-search-close-trigger", on_click=CoinState.reset_global_search, display="none"),
        class_name="global-search-container",
        # Visible at every screen size per explicit request (previously
        # hidden below md/768px) — a narrower-but-usable width at the
        # smallest breakpoints instead of disappearing entirely. 70px at
        # the very smallest breakpoint still fits the icon + a few
        # characters of typed input (it's a real, focusable, typeable
        # field at every width, just visually cropped) — chosen along with
        # the logo-text hiding above so the header's fixed-content columns
        # leave the nav-links column a real, usable width on a phone
        # instead of squeezing it to ~0.
        width=["70px", "110px", "170px", "210px", "240px"],
        flex_shrink="0",
        position="relative",
    )
