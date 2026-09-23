"""The main coin-list data table, with market-cap descending order and
pagination baked into CoinState.paged_coins."""

import reflex as rx

from frontend.state import CoinState


def _change_cell(text: rx.Var[str], color: rx.Var[str]) -> rx.Component:
    return rx.table.cell(rx.text(text, color=color), vertical_align="middle")


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


def _sortable_header(label: str, sort_key: str) -> rx.Component:
    return rx.table.column_header_cell(
        rx.hstack(
            rx.text(label),
            _sort_icon(sort_key),
            spacing="1",
            align="center",
            cursor="pointer",
        ),
        on_click=CoinState.set_sort(sort_key),
    )


def _trend_cell(data: rx.Var[list], color: rx.Var[str], shine_class: rx.Var[str]) -> rx.Component:
    return rx.table.cell(
        rx.box(
            rx.recharts.line_chart(
                rx.recharts.line(
                    data_key="v",
                    stroke=color,
                    dot=False,
                    stroke_width=2,
                    is_animation_active=False,
                ),
                data=data,
                width=90,
                height=32,
            ),
            class_name=shine_class.to(str),
        ),
        vertical_align="middle",
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


_CHAIN_PILL_SLOTS = 10


def _chain_pill(name: rx.Var[str]) -> rx.Component:
    return rx.cond(
        name == "",
        rx.fragment(),
        rx.cond(
            name == "More Chain",
            rx.box(
                rx.text("More Chain", size="1", weight="bold"),
                class_name="chain-pill chain-pill-more",
            ),
            rx.box(rx.text(name, size="1"), class_name="chain-pill"),
        ),
    )


def _chain_carousel(row: dict) -> rx.Component:
    # rx.foreach can't iterate a list nested inside an Any-typed dict value,
    # so CoinState precomputes 10 fixed chain_pill_N slots ("" = unused)
    # instead of a real list here.
    # Drag-to-scroll and the arrow buttons are wired up once, globally, via
    # the delegated listeners in frontend.py's index() (assets/chain_pills.js)
    # so they work for every row's popover without per-row JS.
    return rx.box(
        rx.box(rx.icon("chevron-left", size=14), class_name="chain-scroll-btn chain-scroll-left"),
        rx.box(
            *[_chain_pill(row[f"chain_pill_{i}"]) for i in range(1, _CHAIN_PILL_SLOTS + 1)],
            class_name="chain-pills-track",
        ),
        rx.box(rx.icon("chevron-right", size=14), class_name="chain-scroll-btn chain-scroll-right"),
        class_name="chain-pills-wrap",
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
                    _chain_carousel(row),
                    spacing="2",
                ),
                size="1",
                style={"max-width": "320px"},
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
        rx.table.cell(row["market_cap_display"], vertical_align="middle"),
        rx.table.cell(row["volume_display"], vertical_align="middle"),
        _change_cell(row["change_1h_display"], row["change_1h_color"]),
        _change_cell(row["change_24h_display"], row["change_24h_color"]),
        _change_cell(row["change_7d_display"], row["change_7d_color"]),
        _trend_cell(row["trend_24h_data"], row["trend_24h_color"], row["trend_24h_shine"]),
        _trend_cell(row["trend_7d_data"], row["trend_7d_color"], row["trend_7d_shine"]),
    )


def _pagination() -> rx.Component:
    return rx.hstack(
        rx.button("Prev", on_click=CoinState.prev_page, disabled=CoinState.page <= 1),
        rx.text("Page ", CoinState.page, " / ", CoinState.total_pages),
        rx.button(
            "Next", on_click=CoinState.next_page, disabled=CoinState.page >= CoinState.total_pages
        ),
        spacing="3",
        align="center",
        justify="end",
        width="100%",
        padding_y="0.75em",
    )


_TABLE_COLUMN_COUNT = 10
# Matches CoinState.page_size (always 100) so the skeleton fills the same
# row count — and, via the 3-line Name cell mirroring _row's real stack of
# icon/name row + narrative badge + chain badge, roughly the same per-row
# height — as the real table, instead of collapsing to a handful of thin
# rows while filtering.
_SKELETON_ROW_COUNT = 100


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


def _skeleton_row() -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.skeleton(height="1em", width="60%")),
        _skeleton_name_cell(),
        *[
            rx.table.cell(rx.skeleton(height="1em", width="80%"))
            for _ in range(_TABLE_COLUMN_COUNT - 2)
        ],
    )


def _skeleton_body() -> rx.Component:
    # Shown while CoinState.is_filtering is true (see set_category) — a
    # narrative filter change re-renders up to 100 rows, so this fills the
    # round-trip gap instead of the table looking frozen.
    return rx.table.body(*[_skeleton_row() for _ in range(_SKELETON_ROW_COUNT)])


def _table_header_bar() -> rx.Component:
    return rx.box(
        rx.heading("Top ", CoinState.page_top_n, " Cryptocurrencies", size="5"),
        rx.hstack(
            rx.text("Coins shown", size="2", color_scheme="gray"),
            rx.heading(CoinState.total_shown, size="5"),
            spacing="2",
            align="center",
        ),
        display="flex",
        justify_content="space-between",
        align_items="center",
        width="100%",
    )


def coin_table() -> rx.Component:
    return rx.vstack(
        _table_header_bar(),
        rx.box(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        _sortable_header("Rank", "rank"),
                        rx.table.column_header_cell("Name"),
                        _sortable_header("Price", "price_raw"),
                        _sortable_header("Market Cap", "market_cap_usd"),
                        _sortable_header("24H Volume", "volume_raw"),
                        _sortable_header("1H", "pct_1h_raw"),
                        _sortable_header("24H", "pct_24h_raw"),
                        _sortable_header("7D", "pct_7d_raw"),
                        rx.table.column_header_cell("24H Price"),
                        rx.table.column_header_cell("7D Price"),
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
            height="calc(100vh - 300px)",
            overflow="auto",
            width="100%",
        ),
        _pagination(),
        width="100%",
    )
