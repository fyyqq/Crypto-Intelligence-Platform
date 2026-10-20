"""/tools/multichart: a full-width two-column grid of chart cards (state/multichart_state.py).

An empty card is a big + button. Clicking it opens a coin search inside the card (same rows as the header search: icon,
name, ticker, price, 24h change); clicking a coin shows that coin's TradingView chart in the card, with a header that
names the coin and a button to change it. With more than one card every card has an x (top right) that removes it."""

import reflex as rx

from frontend.components.search_form import q, search_form
from frontend.components.tools_page import _PAGE_PADDING, _page_header
from frontend.state.multichart_state import MultichartState as M


def _result_row(row: rx.Var[dict], card_id) -> rx.Component:
    """One coin in a card's search: the same look as a header-search row; a click puts its chart in the card."""
    return rx.el.button(
        rx.hstack(
            rx.image(src=row["icon_url"], width="22px", height="22px", border_radius="50%", flex_shrink="0"),
            rx.hstack(
                rx.text(row["name"], size="2", weight="bold", class_name="global-search-result-name"),
                rx.text(row["symbol"], size="2", color_scheme="gray", flex_shrink="0"),
                spacing="1",
                align="center",
                min_width="0",
                flex="1",
            ),
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
        ),
        type="button",
        class_name="global-search-result-row multichart-result",
        on_click=M.choose_coin(card_id, row["cmc_id"]),
    )


def _search_panel(card: rx.Var[dict]) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.box(
                rx.icon("search", size=15, class_name="search-submit-icon"),
                search_form(
                    # an uncontrolled field: it searches ~0.45 s after the last key or on Enter (components/search_form.py)
                    rx.el.input(
                        name="q",
                        default_value=M.search_query,
                        placeholder="Search a coin name or ticker",
                        class_name="multichart-search-input",
                        auto_complete="off",
                        spell_check=False,
                        auto_focus=True,
                        enter_key_hint="search",
                    ),
                    on_submit=lambda form_data: M.search(q(form_data)),
                ),
                class_name="multichart-search-bar",
            ),
            rx.el.button(
                rx.icon("x", size=16),
                type="button",
                class_name="multichart-search-close",
                title="Cancel",
                aria_label="Cancel",
                on_click=M.close_search,
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        rx.box(
            rx.cond(
                M.search_query == "",
                rx.text("Type a coin name or ticker, then pick it to see its chart here.", size="2", color_scheme="gray", class_name="multichart-hint"),
                rx.cond(
                    M.search_results.length() > 0,
                    rx.foreach(M.search_results, lambda row: _result_row(row, card["id"])),
                    rx.text("No coins found for \"", M.search_query, "\"", size="2", color_scheme="gray", class_name="multichart-hint"),
                ),
            ),
            class_name="multichart-results",
        ),
        class_name="multichart-panel multichart-search",
    )


def _coin_head(card: rx.Var[dict]) -> rx.Component:
    return rx.hstack(
        rx.image(src=card["icon_url"], width="24px", height="24px", border_radius="50%", flex_shrink="0"),
        rx.text(card["name"], size="3", weight="bold", class_name="global-search-result-name"),
        rx.text(card["symbol"], size="2", color_scheme="gray", flex_shrink="0"),
        rx.spacer(),
        rx.el.button(
            rx.icon("search", size=15),
            "Change coin",
            type="button",
            class_name="multichart-change",
            title="Pick another coin",
            on_click=M.open_search(card["id"]),
        ),
        spacing="2",
        align="center",
        class_name="multichart-head",
    )


def _chart_panel(card: rx.Var[dict]) -> rx.Component:
    return rx.box(
        _coin_head(card),
        rx.match(
            card["status"],
            (
                "ready",
                rx.el.iframe(
                    src=rx.color_mode_cond(light=card["iframe_light"], dark=card["iframe_dark"]),
                    title="TradingView chart",
                    custom_attrs={"frameborder": "0", "allowfullscreen": "true"},
                    class_name="multichart-chart",
                ),
            ),
            (
                "loading",
                rx.center(rx.spinner(size="3"), class_name="multichart-chart multichart-state"),
            ),
            rx.center(
                rx.text(card["message"], size="2", color_scheme="gray", text_align="center"),
                class_name="multichart-chart multichart-state",
            ),
        ),
        class_name="multichart-panel",
    )


def _empty_slot(card: rx.Var[dict]) -> rx.Component:
    return rx.el.button(
        rx.center(rx.icon("plus", size=30), class_name="multichart-plus"),
        type="button",
        class_name="multichart-slot",
        title="Add a chart",
        aria_label="Add a chart to this card",
        on_click=M.open_search(card["id"]),
    )


def _card(card: rx.Var[dict]) -> rx.Component:
    """One chart card: the coin search while it is open, else the + (empty) or the chart; plus an x when there are several."""
    return rx.box(
        rx.cond(
            M.search_card == card["id"],
            _search_panel(card),
            rx.cond(card["status"] == "empty", _empty_slot(card), _chart_panel(card)),
        ),
        rx.cond(
            M.can_remove,
            rx.el.button(
                rx.icon("x", size=18),
                type="button",
                class_name="multichart-remove",
                title="Remove this card",
                aria_label="Remove this card",
                on_click=M.remove_card(card["id"]),
            ),
        ),
        class_name="multichart-card",
    )


def multichart_content() -> rx.Component:
    """/tools/multichart: a full-width, two-column grid of chart cards; it starts with one card and the full-width
    "Add more chart" button under the grid adds another."""
    return rx.vstack(
        _page_header("Multichart", "Watch several charts side by side. Click + in a card to pick a coin and see its chart."),
        rx.box(rx.foreach(M.cards, _card), class_name="multichart-grid"),
        rx.cond(
            M.can_add,
            rx.el.button(
                rx.icon("plus", size=18),
                "Add more chart",
                type="button",
                class_name="multichart-add-more",
                on_click=M.add_card,
            ),
        ),
        spacing="5",
        width="100%",
        padding=_PAGE_PADDING,
    )
