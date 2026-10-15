"""/narrative and /chains: every narrative / chain as pills on one page (no pagination, no search), ranked by its
24h score: the average 24h change of its top 20 coins by market cap (CoinState.load_sector_boards)."""

import reflex as rx

from frontend.state import CoinState


def _pct(item) -> rx.Component:
    return rx.cond(
        item["pct"] != "",
        rx.text(item["pct"], size="1", weight="bold", color=item["color"], class_name="sector-pct"),
    )


def _narrative_link(item: rx.Var[dict]) -> rx.Component:
    # Opens that narrative's news page (/narrative/<slug>).
    return rx.link(
        rx.box(rx.text(item["name"], size="1"), _pct(item), class_name="narrative-pill sector-pill", title=item["title"]),
        href=item["href"],
        underline="none",
        color="inherit",
    )


def _chain_pill(item: rx.Var[dict]) -> rx.Component:
    # Shows that chain's coins on the homepage table.
    return rx.box(
        rx.text(item["name"], size="1"),
        _pct(item),
        on_click=CoinState.open_chain(item["name"]),
        class_name="chain-filter-pill sector-pill",
        title=item["title"],
    )


def _note(kind: str) -> rx.Component:
    return rx.text(
        rx.cond(
            CoinState.sector_status == "ready",
            f"Sorted by 24h performance: the average 24h change of each {kind}'s top 20 coins by market cap "
            "(our own hourly prices of the top 500 coins). Updated hourly, last ",
            f"24h performance appears once a full day of hourly prices is collected; until then {kind}s are listed by size. ",
        ),
        rx.cond(CoinState.sector_status == "ready", CoinState.sector_updated, ""),
        rx.cond(CoinState.sector_status == "ready", " (Kuala Lumpur).", ""),
        size="2",
        color="var(--gray-11)",
    )


def _page(title: str, kind: str, board, pill) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading(title, size="6"),
            rx.badge(board.length(), color_scheme="gray", variant="soft", size="2"),
            align="center",
            spacing="3",
        ),
        _note(kind),
        rx.cond(
            board.length() == 0,
            rx.hstack(*[rx.skeleton(height="26px", width="130px", border_radius="999px") for _ in range(12)], wrap="wrap", spacing="2"),
            rx.box(rx.foreach(board, pill), class_name="filter-pills-wrap", width="100%"),
        ),
        spacing="4",
        width="100%",
        align_items="start",
        padding=["1em", "1em", "1.5em", "2em", "2em"],
    )


def narratives_index_content() -> rx.Component:
    return _page("Narratives", "narrative", CoinState.narrative_board, _narrative_link)


def chains_index_content() -> rx.Component:
    return _page("Chains", "chain", CoinState.chain_board, _chain_pill)
