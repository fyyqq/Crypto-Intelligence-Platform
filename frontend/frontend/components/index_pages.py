"""/narrative and /chains: a table of every narrative / chain (20 rows a page), ranked by its 24h score (the average 24h
change of its top 20 coins by market cap): # | name | top 10 coins | 3 biggest gainers | 3 biggest losers, the coins as
logo + ticker pills (CoinState.load_sector_boards)."""

import reflex as rx

from frontend.state import CoinState
from frontend.state.coin_state import SECTOR_TABLE_PAGE_SIZES


def _badge(b: rx.Var[dict]) -> rx.Component:
    """A coin pill: logo + ticker (+ its 24h change for the movers); opens that coin's page."""
    return rx.link(
        rx.hstack(
            rx.image(src=b["icon_url"], width="18px", height="18px", border_radius="50%", flex_shrink="0", loading="lazy"),
            rx.text(b["symbol"], size="1", weight="medium"),
            rx.cond(b["pct"] != "", rx.text(b["pct"], size="1", weight="bold", color=b["color"], class_name="sector-pct")),
            spacing="1",
            align="center",
        ),
        href=b["href"],
        title=b["name"],
        underline="none",
        color="inherit",
        class_name="coin-badge",
    )


def _badges(items) -> rx.Component:
    items = items.to(list[dict])
    return rx.cond(
        items.length() > 0,
        rx.box(rx.foreach(items, _badge), class_name="coin-badges"),
        rx.text("–", size="2", color="var(--gray-9)"),
    )


def _score(item) -> rx.Component:
    return rx.cond(
        item["pct"] != "",
        rx.text(item["pct"], size="1", weight="bold", color=item["color"], class_name="sector-pct", title=item["title"]),
        rx.text("n/a", size="1", color="var(--gray-9)", title=item["title"]),
    )


def _narrative_name(item) -> rx.Component:
    return rx.vstack(
        rx.link(rx.text(item["name"], size="2", weight="medium"), href=item["href"], underline="hover", color="inherit"),
        _score(item),
        spacing="1",
        align_items="start",
    )


def _chain_name(item) -> rx.Component:
    return rx.vstack(
        rx.link(rx.text(item["name"], size="2", weight="medium"), href=item["href"], underline="hover", color="inherit"),
        _score(item),
        spacing="1",
        align_items="start",
    )


def _row(item: rx.Var[dict], name_cell) -> rx.Component:
    return rx.table.row(
        rx.table.row_header_cell(item["id"], class_name="sector-id"),
        rx.table.cell(name_cell(item), class_name="sector-name"),
        rx.table.cell(_badges(item["top"]), class_name="sector-top"),
        rx.table.cell(_badges(item["gainers"]), class_name="sector-mover"),
        rx.table.cell(_badges(item["losers"]), class_name="sector-mover"),
        vertical_align="top",
    )


def _note(kind: str) -> rx.Component:
    return rx.text(
        rx.cond(
            CoinState.sector_status == "ready",
            f"Sorted by 24h performance: the average 24h change of each {kind}'s top 20 coins by market cap "
            "(our own hourly prices of the top 500 coins). Biggest gainer / loser: its three coins with the largest 24h rise / fall. Updated hourly, last ",
            f"24h performance appears once a full day of hourly prices is collected; until then {kind}s are listed by size. ",
        ),
        rx.cond(CoinState.sector_status == "ready", CoinState.sector_updated, ""),
        rx.cond(CoinState.sector_status == "ready", " (Kuala Lumpur).", ""),
        size="2",
        color="var(--gray-11)",
    )


def _sort_header(label: str, column: str, sort_var, on_click) -> rx.Component:
    """Column title with an arrow: arrow-down = biggest first (desc), arrow-up = smallest first (asc), both = unsorted."""
    return rx.table.column_header_cell(
        rx.hstack(
            rx.text(label),
            rx.icon(
                rx.cond(sort_var == f"{column}_desc", "arrow-down", rx.cond(sort_var == f"{column}_asc", "arrow-up", "arrow-up-down")),
                size=15,
                color=rx.cond(sort_var.startswith(column), "var(--accent-10)", "var(--gray-9)"),
            ),
            spacing="2",
            align="center",
            cursor="pointer",
            on_click=on_click(column),
            title="Sort: biggest first, smallest first, then back to the 24h ranking",
            class_name="sector-sort",
        )
    )


def _pager(first, prev, nxt, last, page, pages) -> rx.Component:
    from frontend.components.news_page import _pagination_row

    return rx.cond(pages > 1, _pagination_row(first, prev, nxt, last, page, pages))


def _page(title: str, kind: str, label: str, top_label: str, total, rows, name_cell, pager, sort_var, on_sort, search_var, on_search, size_var, on_size) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading(title, size="6"),
            rx.badge(total, color_scheme="gray", variant="soft", size="2"),
            align="center",
            spacing="3",
        ),
        rx.flex(
            _note(kind),
            rx.hstack(
                rx.select.root(
                    rx.select.trigger(class_name="sector-select sector-select-small"),
                    rx.select.content(*[rx.select.item(f"{n} per page", value=str(n)) for n in SECTOR_TABLE_PAGE_SIZES]),
                    value=size_var.to_string(),
                    on_change=on_size,
                    size="2",
                ),
                rx.input(
                value=search_var,
                on_change=on_search,
                placeholder=f"Search {kind}",
                debounce_timeout=250,
                size="2",
                radius="full",
                variant="surface",
                class_name="sector-search",
                ),
                align="center",
                spacing="2",
                flex_shrink="0",
                width=rx.breakpoints(initial="100%", sm="auto"),
            ),
            justify="between",
            align="center",
            gap="1em",
            width="100%",
            direction=rx.breakpoints(initial="column", sm="row"),
        ),
        rx.cond(
            (rows.length() == 0) & (search_var == "") & (total == 0),
            rx.vstack(*[rx.skeleton(height="64px", width="100%", border_radius="8px") for _ in range(6)], spacing="2", width="100%"),
            rx.cond(
                rows.length() == 0,
                rx.text("No ", kind, " matches \"", search_var, "\".", size="2", color="var(--gray-11)"),
            rx.vstack(
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("#"),
                                rx.table.column_header_cell(label),
                                rx.table.column_header_cell(top_label),
                                _sort_header("Biggest gainer", "gainer", sort_var, on_sort),
                                _sort_header("Biggest loser", "loser", sort_var, on_sort),
                            )
                        ),
                        rx.table.body(rx.foreach(rows, lambda item: _row(item, name_cell))),
                        variant="surface",
                        width="100%",
                        class_name="sector-table",
                    ),
                    overflow_x="auto",
                    width="100%",
                ),
                pager,
                spacing="4",
                width="100%",
            ),
            ),
        ),
        spacing="4",
        width="100%",
        align_items="start",
        padding=["1em", "1em", "1.5em", "2em", "2em"],
    )


def narratives_index_content() -> rx.Component:
    return _page(
        "Narratives", "narrative", "Narrative", "Top coins", CoinState.narrative_total, CoinState.narrative_board, _narrative_name,
        _pager(CoinState.narrative_table_first, CoinState.narrative_table_prev, CoinState.narrative_table_next, CoinState.narrative_table_last,
               CoinState.narrative_table_page, CoinState.narrative_table_pages),
        CoinState.narrative_sort, CoinState.cycle_narrative_sort, CoinState.narrative_search, CoinState.set_narrative_search,
        CoinState.narrative_table_size, CoinState.set_narrative_table_size,
    )


def chains_index_content() -> rx.Component:
    return _page(
        "Chains", "chain", "Chain", "Top coins", CoinState.chain_total, CoinState.chain_board, _chain_name,
        _pager(CoinState.chain_table_first, CoinState.chain_table_prev, CoinState.chain_table_next, CoinState.chain_table_last,
               CoinState.chain_table_page, CoinState.chain_table_pages),
        CoinState.chain_sort, CoinState.cycle_chain_sort, CoinState.chain_search, CoinState.set_chain_search,
        CoinState.chain_table_size, CoinState.set_chain_table_size,
    )
