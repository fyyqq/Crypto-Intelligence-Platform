"""Homepage "Targeted Narrative + Coin": real Cryptocurrency news, each tied by
AI to one coin and its narrative (app/services/news_targeting_service.py).
Same slider mechanics as the news strip above it (drag, arrows, autoplay —
the news-slider-* classes in assets/chain_pills.js); text-only cards."""

import reflex as rx

from frontend.state import NewsState


def _alert_card(article: rx.Var, *, in_grid: bool = False) -> rx.Component:
    return rx.link(
        rx.box(
            rx.hstack(
                rx.badge(article["target_symbol"], color_scheme="indigo", size="1"),
                rx.badge(article["target_narrative"], color_scheme="orange", size="1"),
                rx.spacer(),
                rx.text(article["time_display"], size="1", color_scheme="gray", flex_shrink="0"),
                width="100%",
                align="center",
                direction="row-reverse",
                # A long narrative name plus the coin badge doesn't fit on one
                # line at the card's narrowest width; let it wrap.
                wrap="wrap",
            ),
            rx.text(article["title"], weight="bold", size="2", margin_top="0.4em", class_name="line-clamp-3"),
            rx.cond(
                article["has_snippet"],
                rx.text(article["snippet"], size="1", color_scheme="gray", margin_top="0.3em", class_name="line-clamp-3"),
            ),
            padding="0.85em",
            border_radius="8px",
            background="var(--gray-a2)",
            height="100%",
            color="var(--gray-12)",
        ),
        href=article["detail_url"],
        underline="none",
        display="block",
        width="100%" if in_grid else ["270px", "290px", "310px", "340px", "340px"],
        flex_shrink="0",
    )


def _alerts_slider() -> rx.Component:
    return rx.box(
        rx.box(rx.icon("chevron-left", size=14), class_name="news-scroll-btn news-scroll-left"),
        rx.box(
            rx.foreach(NewsState.home_targeted_news, _alert_card),
            class_name="news-slider-track",
        ),
        rx.box(rx.icon("chevron-right", size=14), class_name="news-scroll-btn news-scroll-right"),
        class_name="news-slider-wrap",
    )


def narrative_alerts() -> rx.Component:
    return rx.vstack(
        rx.text("TARGETED NARRATIVE ALERTS", size="1", color_scheme="gray", weight="bold"),
        rx.box(
            rx.heading("Narrative Radar", size=rx.breakpoints(initial="4", sm="5")),
            rx.link(
                rx.hstack(
                    rx.text("More Narratives", size="2", weight="bold"),
                    rx.icon("arrow-right", size=14),
                    spacing="1",
                    align="center",
                ),
                href="/narrative",
                underline="none",
                color_scheme="indigo",
            ),
            display="flex",
            flex_wrap="wrap",
            justify_content="space-between",
            align_items="center",
            width="100%",
            style={"row-gap": "0.25em"},
        ),
        rx.cond(
            NewsState.is_loading,
            rx.hstack(
                *[rx.skeleton(width="320px", height="150px", border_radius="8px", flex_shrink="0") for _ in range(4)],
                spacing="3",
                width="100%",
                overflow_x="hidden",
            ),
            rx.cond(
                NewsState.home_targeted_news.length() > 0,
                _alerts_slider(),
                rx.center(
                    rx.text(
                        "The AI is analysing the latest crypto news — targeted coins appear here shortly.",
                        size="2",
                        color_scheme="gray",
                    ),
                    padding="2em 1em",
                    border_radius="8px",
                    background="var(--gray-a2)",
                    width="100%",
                ),
            ),
        ),
        spacing="3",
        width="100%",
        align_items="stretch",
    )


def _coin_card(c: rx.Var[dict]) -> rx.Component:
    """One coin: logo + star, name, price and 24h change, the table's trend line. The whole card opens the coin page
    (stretched link, assets/styles.css .coin-card); the star toggles the real watchlist (CoinState.toggle_watchlist)."""
    from frontend.state import CoinState

    watched = CoinState.watchlist_ids.contains(c["cmc_id"])
    return rx.box(
        rx.hstack(
            rx.image(src=c["icon_url"], width="32px", height="32px", border_radius="50%", loading="lazy"),
            rx.box(
                rx.icon("star", size=22, color=rx.cond(watched, "var(--amber-9)", "var(--gray-12)"), fill=rx.cond(watched, "var(--amber-9)", "none"), cursor="pointer"),
                on_click=CoinState.toggle_watchlist(c["cmc_id"]),
                class_name="wl-star coin-card-star",
                title="Add to / remove from watchlist",
            ),
            justify="between",
            align="start",
            width="100%",
        ),
        rx.link(rx.text(c["name"], size="3", weight="medium", class_name="coin-card-name"), href=c["href"], underline="none", color="var(--gray-12)", class_name="coin-card-link"),
        rx.hstack(
            rx.text(c["price"], size="4", weight="bold"),
            rx.text(c["arrow"], " ", c["change"], size="2", weight="medium", color=c["color"], white_space="nowrap"),
            align="center",
            spacing="2",
            wrap="wrap",
        ),
        rx.box(
            rx.recharts.line_chart(
                rx.recharts.line(data_key="v", stroke=c["trend_color"], dot=False, active_dot=False, stroke_width=2, is_animation_active=False),
                data=c["trend"],
                width="100%",
                height=70,
            ),
            class_name=c["shine"].to(str) + " coin-card-chart",
            width="100%",
        ),
        class_name="coin-card",
    )


def _sector_controls() -> rx.Component:
    """Sort (market cap / 24h change, high to low or low to high) and how many coins to show per page."""
    from frontend.state import CoinState
    from frontend.state.coin_state import SECTOR_PAGE_SIZES, SECTOR_SORTS

    return rx.flex(
        rx.hstack(
            rx.text("Sort", size="2", color_scheme="gray"),
            rx.select.root(
                rx.select.trigger(class_name="sector-select"),
                rx.select.content(*[rx.select.item(label, value=key) for key, label in SECTOR_SORTS.items()]),
                value=CoinState.sector_sort,
                on_change=CoinState.set_sector_sort,
                size="2",
            ),
            align="center",
            spacing="2",
        ),
        rx.hstack(
            rx.text("Show", size="2", color_scheme="gray"),
            rx.select.root(
                rx.select.trigger(class_name="sector-select sector-select-small"),
                rx.select.content(*[rx.select.item(f"{n} per page", value=str(n)) for n in SECTOR_PAGE_SIZES]),
                value=CoinState.sector_page_size.to_string(),
                on_change=CoinState.set_sector_page_size,
                size="2",
            ),
            align="center",
            spacing="2",
        ),
        gap="1em",
        wrap="wrap",
        align="center",
    )


def _sector_coin_card(view, noun: str) -> rx.Component:
    """The narrative's / chain's coins as cards: every coin, sortable, 10 a page by default (5 columns x 2 rows on
    desktop; 20, 50, 100 or 200 a page can be chosen) with a pager."""
    from frontend.components.news_page import _pagination_row
    from frontend.state import CoinState

    return rx.cond(
        view["coin_count"].to(int) > 0,
        rx.vstack(
            rx.flex(
                rx.hstack(
                    rx.heading("Coins in ", view["label"], size="4"),
                    rx.badge(view["coin_count"], color_scheme="gray", variant="soft", size="2"),
                    align="center",
                    spacing="2",
                    wrap="wrap",
                ),
                _sector_controls(),
                justify="between",
                align="center",
                gap="1em",
                wrap="wrap",
                width="100%",
            ),
            rx.grid(
                rx.foreach(CoinState.sector_cards, _coin_card),
                columns=rx.breakpoints(initial="2", sm="3", md="5"),
                gap="1em",
                width="100%",
            ),
            rx.cond(
                CoinState.sector_card_pages > 1,
                _pagination_row(
                    CoinState.sector_cards_first, CoinState.sector_cards_prev, CoinState.sector_cards_next, CoinState.sector_cards_last,
                    CoinState.sector_card_page_shown, CoinState.sector_card_pages,
                ),
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
    )


def sector_page_content(view, noun: str, back_href: str, back_label: str) -> rx.Component:
    """/narrative/<slug> and /chains/<slug>: title, a card box with the sector's coins, then every story tied to the
    sector or mentioning its biggest coins, 100 per page, same grid and pagination as a /news/<category> page."""
    from frontend.components.news_page import _GRID_COLUMNS, _pagination_row

    return rx.vstack(
        rx.flex(
            rx.heading(view["label"], size="6"),
            rx.text(f"Crypto news about this {noun} and its coins: stories the AI tied to it and any story mentioning one of its biggest coins by name or ticker.", size="2", color_scheme="gray"),
            rx.link(rx.text(back_label, size="2"), href=back_href, underline="none", color_scheme="indigo"),
            rx.badge(view["article_count"], " articles", color_scheme="gray", variant="soft", size="2"),
            direction="column",
            spacing="3",
            align="center",
            text_align="center",
            width="100%",
        ),
        _sector_coin_card(view, noun),
        rx.cond(
            NewsState.is_loading,
            rx.grid(
                *[rx.skeleton(height="150px", border_radius="8px") for _ in range(15)],
                columns=_GRID_COLUMNS,
                spacing="4",
                width="100%",
            ),
            rx.vstack(
                rx.text(
                    "Showing ", view["range_start"], "–", view["range_end"], " of ", view["article_count"], " articles",
                    size="2",
                    color_scheme="gray",
                ),
                rx.grid(
                    rx.foreach(view["articles"].to(list[dict]), lambda a: _alert_card(a, in_grid=True)),
                    columns=_GRID_COLUMNS,
                    spacing="4",
                    width="100%",
                ),
                rx.cond(
                    view["has_pagination"],
                    _pagination_row(
                        NewsState.narrative_first,
                        NewsState.narrative_prev,
                        NewsState.narrative_next,
                        NewsState.narrative_last,
                        view["page"],
                        view["total_pages"],
                    ),
                ),
                spacing="4",
                width="100%",
            ),
        ),
        spacing="5",
        width="100%",
        padding=["1em", "1em", "1.5em", "2em", "2em"],
    )


def narrative_page_content() -> rx.Component:
    return sector_page_content(NewsState.narrative_view, "narrative", "/narrative", "← All narratives")


def chain_page_content() -> rx.Component:
    return sector_page_content(NewsState.chain_view, "chain", "/chains", "← All chains")
