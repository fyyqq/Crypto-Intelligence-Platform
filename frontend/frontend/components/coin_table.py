"""The main coin-list data table, with market-cap descending order and
pagination baked into CoinState.paged_coins."""

import reflex as rx

from frontend.state import CoinState


def _change_cell(text: rx.Var[str], color: rx.Var[str], display: list[str] | None = None) -> rx.Component:
    return rx.table.cell(
        rx.text(text, color=color),
        vertical_align="middle",
        **({"display": display} if display else {}),
    )


def _sort_icon(sort_key: str) -> rx.Component:
    is_active_col = CoinState.sort_key == sort_key
    up_active = is_active_col & (CoinState.sort_direction == "desc")
    down_active = is_active_col & (CoinState.sort_direction == "asc")
    return rx.vstack(
        rx.icon(
            "chevron-up",
            size=11,
            color=rx.cond(up_active, "var(--accent-9)", "var(--gray-8)"),
        ),
        rx.icon(
            "chevron-down",
            size=11,
            color=rx.cond(down_active, "var(--accent-9)", "var(--gray-8)"),
        ),
        spacing="0",
        align="center",
        margin_top="-2px",
        margin_bottom="-2px",
    )


_STICKY_HEADER_STYLE = {
    "position": "sticky",
    "top": "0",
    "z_index": "2",
    "background_color": "var(--gray-2)",
    # Forces each sticky header cell onto its own GPU compositing layer.
    # Without this, Safari has a known rendering bug where a `position:
    # sticky` element inside a horizontally-scrolling container (this
    # table, since .coin-table-scroll-fix went overflow-x: scroll) leaves a
    # stale/ghosted partial repaint of the header behind while scrolling,
    # until something forces a full repaint — visible as a translucent
    # overlay patch covering part of the header/rows.
    "transform": "translateZ(0)",
}

# Responsive column visibility, [base, sm, md, lg, xl] (iPhone-4-width up to
# desktop) — Rank/Name/Price/24H always show; everything else drops off at
# progressively wider breakpoints so a phone-width table isn't crushed to
# unreadable columns instead of just showing fewer of them. Same array is
# applied to a column's header cell and every row's matching body cell so
# they hide/show in sync.
_COL_ALWAYS = ["table-cell"] * 5
_COL_FROM_SM = ["none", "table-cell", "table-cell", "table-cell", "table-cell"]
_COL_FROM_MD = ["none", "none", "table-cell", "table-cell", "table-cell"]
# Volume/1H/the two trend charts used to hide below various breakpoints to
# keep the table narrow enough to fit next to the 300px sidebar without
# forcing horizontal scroll. Per explicit instruction, these are real data
# columns, not decoration — they always render now, at every viewport width
# down to iPhone 4, and .coin-table-scroll-fix's local horizontal scroll
# (styles.css, active up to 1440px — comfortably covers every width these
# columns need it at) is the only mechanism handling widths they don't fit,
# rather than ever hiding them.
_COL_FROM_LG = _COL_ALWAYS


def _sortable_header(label: str, sort_key: str, display: list[str] = _COL_ALWAYS) -> rx.Component:
    return rx.table.column_header_cell(
        rx.hstack(
            rx.text(label),
            _sort_icon(sort_key),
            spacing="1",
            align="center",
            cursor="pointer",
        ),
        on_click=CoinState.set_sort(sort_key),
        display=display,
        **_STICKY_HEADER_STYLE,
    )


def _trend_cell(
    data: rx.Var[list], color: rx.Var[str], shine_class: rx.Var[str], display: list[str] = _COL_ALWAYS
) -> rx.Component:
    return rx.table.cell(
        rx.box(
            rx.recharts.line_chart(
                rx.recharts.line(
                    data_key="v",
                    stroke=color,
                    dot=False,
                    active_dot=False,
                    stroke_width=2,
                    is_animation_active=False,
                ),
                data=data,
                width=80,
                height=32,
            ),
            class_name=shine_class.to(str),
        ),
        vertical_align="middle",
        display=display,
    )


# rx.icon's tag must be a literal string, not a Var, so the icon name computed
# server-side (CoinState._narrative_icon) is resolved to a component here via
# rx.match instead of passed straight through.
_NARRATIVE_ICON_NAMES = (
    "smile",
    "cpu",
    "gamepad-2",
    "dollar-sign",
    "image",
    "eye-off",
    "arrow-left-right",
    "database",
    "radio",
    "credit-card",
    "landmark",
    "layers",
)


def _narrative_icon_component(icon_name: rx.Var[str]) -> rx.Component:
    return rx.match(
        icon_name,
        *[(name, rx.icon(name, size=11)) for name in _NARRATIVE_ICON_NAMES],
        rx.icon("tag", size=11),
    )


def _narrative_badge(row: dict) -> rx.Component:
    return rx.badge(
        _narrative_icon_component(row["primary_narrative_icon"]),
        rx.text(row["primary_narrative"]),
        variant="outline",
        size="1",
        color_scheme="gray",
    )


def _chain_badge(row: dict) -> rx.Component:
    chain_label = rx.hstack(
        rx.icon("link", size=11),
        rx.text(row["main_chain"]),
        spacing="1",
        align="center",
    )
    return rx.cond(
        row["has_other_chains"],
        rx.popover.root(
            rx.popover.trigger(
                rx.badge(
                    chain_label,
                    rx.icon("chevron-down", size=11),
                    variant="surface",
                    size="1",
                    color_scheme="gray",
                    cursor="pointer",
                )
            ),
            rx.popover.content(
                rx.vstack(
                    rx.text("Also deployed on", size="1", color_scheme="gray"),
                    rx.text(row["other_chains_display"], white_space="pre-line", size="2"),
                    spacing="1",
                ),
                size="1",
            ),
        ),
        rx.badge(chain_label, variant="surface", size="1", color_scheme="gray"),
    )


def _row(row: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(row["rank"], vertical_align="middle"),
        rx.table.cell(
            rx.vstack(
                rx.hstack(
                    rx.image(
                        src=row["icon_url"],
                        width="22px",
                        height="22px",
                        border_radius="50%",
                    ),
                    rx.text(row["name"], weight="bold"),
                    rx.text(row["symbol"], color_scheme="gray"),
                    spacing="2",
                    align="center",
                ),
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
    )


_PAGE_SIZE_OPTIONS = ["50", "100", "200", "500"]


def _page_number(page_str: rx.Var[str]) -> rx.Component:
    return rx.cond(
        page_str == "...",
        rx.text("...", size="2", color_scheme="gray", padding_x="0.3em"),
        rx.box(
            rx.text(page_str, size="2"),
            on_click=CoinState.go_to_page(page_str),
            class_name=rx.cond(
                CoinState.active_page_str == page_str,
                "page-number page-number-active",
                "page-number",
            ),
        ),
    )


def _pagination_controls() -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon("chevron-left", size=16),
            on_click=CoinState.prev_page,
            class_name="page-arrow-btn",
        ),
        rx.foreach(CoinState.page_window, _page_number),
        rx.box(
            rx.icon("chevron-right", size=16),
            on_click=CoinState.next_page,
            class_name="page-arrow-btn",
        ),
        spacing="1",
        align="center",
        justify="center",
        wrap="wrap",
    )


def _rows_per_page_selector() -> rx.Component:
    return rx.hstack(
        rx.text("Rows", size="2", color_scheme="gray"),
        rx.select(
            _PAGE_SIZE_OPTIONS,
            value=CoinState.page_size_str,
            on_change=CoinState.set_page_size,
            size="2",
        ),
        spacing="2",
        align="center",
    )


def _pagination_bar(pill: bool = False) -> rx.Component:
    # wrap (not the old rx.spacer()-based layout) so this degrades to a
    # multi-line stack instead of overflowing once "Showing ... results" +
    # up to 7 page numbers + the rows selector no longer fit one row (phone
    # widths). justify="between" keeps the original 3-group spread on desktop
    # where everything still fits on one line.
    return rx.hstack(
        rx.text(
            "Showing ",
            CoinState.showing_start,
            " to ",
            CoinState.showing_end,
            " of ",
            CoinState.total_shown,
            " results",
            size="2",
            color_scheme="gray",
            white_space="nowrap",
            # Hidden below "sm" (480px) — on an iPhone-4-width screen there
            # isn't room for this text alongside the page controls too.
            display=["none", "flex", "flex", "flex", "flex"],
        ),
        _pagination_controls(),
        _rows_per_page_selector(),
        align="center",
        justify="between",
        wrap="wrap",
        width="100%",
        style={"row-gap": "0.5em"},
        class_name="pagination-pill" if pill else "",
        # Matches the plain bottom-bar's padding on mobile even for the
        # pill=True (top) bar, since its rounded/bordered look is itself
        # disabled below 768px (see styles.css's .pagination-pill media
        # query) — otherwise the pill's own padding would look mismatched
        # once the border/background it was designed for is gone.
        padding=(
            ["0.75em 0", "0.75em 0", "0.6em 1.4em", "0.6em 1.4em", "0.6em 1.4em"]
            if pill
            else "0.75em 0"
        ),
    )


def _skeleton_name_cell() -> rx.Component:
    return rx.table.cell(
        rx.vstack(
            rx.skeleton(height="1.2em", width="70%"),
            rx.skeleton(height="1em", width="50%"),
            rx.skeleton(height="1em", width="55%"),
            spacing="2",
            align="start",
        ),
        vertical_align="middle",
    )


# Same display array, in the same column order, as the real header/row cells
# below — otherwise the skeleton would show more columns than the table it's
# about to be replaced by, and the page width would jump once real rows land.
_SKELETON_COL_DISPLAYS = (
    _COL_ALWAYS,  # Price
    _COL_FROM_MD,  # Market Cap
    _COL_FROM_LG,  # 24H Volume
    _COL_FROM_LG,  # 1H
    _COL_ALWAYS,  # 24H
    _COL_FROM_SM,  # 7D
    _COL_FROM_LG,  # 24H Price chart
    _COL_FROM_LG,  # 7D Price chart
)


def _skeleton_row(_: rx.Var) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.skeleton(height="1em", width="60%")),
        _skeleton_name_cell(),
        *[
            rx.table.cell(rx.skeleton(height="1em", width="80%"), display=display)
            for display in _SKELETON_COL_DISPLAYS
        ],
    )


def _skeleton_body() -> rx.Component:
    # Shown while CoinState.is_filtering is true (narrative/chain/search
    # filter changes, pagination, rows-per-page) — matches
    # CoinState.page_size exactly (not a fixed count) so the skeleton fills
    # the same row count the real table is about to show, instead of the
    # page height jumping when the real rows replace it.
    return rx.table.body(rx.foreach(CoinState.skeleton_rows, _skeleton_row))


def _coin_search() -> rx.Component:
    # Click the magnifying glass to expand it into a debounced search field
    # (name/ticker only) that queries every coin, not just the current
    # page — see CoinState.filtered_coins. Whatever it finds flows through
    # the same pagination/live-sync pipeline as any other filter, so
    # results still refresh every 60s.
    #
    # Both the icon button and the input stay permanently mounted (only a
    # class toggles) instead of being swapped via rx.cond — animating a
    # CSS width/opacity transition needs the same DOM node to persist
    # across the open/closed state, not a full component swap.
    return rx.box(
        rx.icon(
            "search",
            size=16,
            class_name="coin-search-toggle-icon",
            on_click=CoinState.toggle_search,
        ),
        rx.box(
            rx.debounce_input(
                rx.input(
                    rx.input.slot(rx.icon("search", size=14)),
                    placeholder="Search coin name or ticker...",
                    value=CoinState.search_query,
                    on_change=CoinState.set_search_query,
                    size="2",
                    radius="full",
                    variant="surface",
                    class_name="coin-search-input",
                    width=["150px", "180px", "220px", "220px", "220px"],
                ),
                debounce_timeout=300,
            ),
            rx.icon(
                "x",
                size=14,
                class_name="coin-search-clear-icon",
                on_click=CoinState.toggle_search,
            ),
            class_name="coin-search-input-wrap",
        ),
        class_name=rx.cond(
            CoinState.search_open,
            "coin-search-container coin-search-open",
            "coin-search-container",
        ),
    )


def _table_header_bar() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.heading("Top ", CoinState.page_top_n, " Cryptocurrencies", size="5"),
            _coin_search(),
            spacing="3",
            align="center",
            wrap="wrap",
        ),
        rx.hstack(
            rx.text("Total Coins:", size="2", color_scheme="gray"),
            rx.heading(CoinState.total_shown, size="5"),
            spacing="2",
            align="center",
        ),
        display="flex",
        flex_wrap="wrap",
        justify_content="space-between",
        align_items="center",
        width="100%",
        style={"row-gap": "0.5em"},
    )


def coin_table() -> rx.Component:
    return rx.vstack(
        _table_header_bar(),
        _pagination_bar(pill=True),
        rx.box(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        _sortable_header("Rank", "rank"),
                        rx.table.column_header_cell("Name", **_STICKY_HEADER_STYLE),
                        _sortable_header("Price", "price_raw"),
                        _sortable_header("Market Cap", "market_cap_usd", display=_COL_FROM_MD),
                        _sortable_header("24H Volume", "volume_raw", display=_COL_FROM_LG),
                        _sortable_header("1H", "pct_1h_raw", display=_COL_FROM_LG),
                        _sortable_header("24H", "pct_24h_raw"),
                        _sortable_header("7D", "pct_7d_raw", display=_COL_FROM_SM),
                        rx.table.column_header_cell("24H Price", display=_COL_FROM_LG, **_STICKY_HEADER_STYLE),
                        rx.table.column_header_cell("7D Price", display=_COL_FROM_LG, **_STICKY_HEADER_STYLE),
                    )
                ),
                rx.cond(
                    CoinState.is_filtering,
                    _skeleton_body(),
                    rx.table.body(rx.foreach(CoinState.sorted_paged_coins, _row)),
                ),
                variant="surface",
                width="100%",
            ),
            height="max-content",
            width="100%",
            class_name="coin-table-scroll-fix",
        ),
        _pagination_bar(pill=False),
        width="100%",
    )
