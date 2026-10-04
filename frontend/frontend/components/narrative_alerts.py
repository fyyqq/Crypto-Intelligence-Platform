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


def narrative_page_content() -> rx.Component:
    """/narrative: every AI-targeted Cryptocurrency article as cards, 100 per
    page, in the same grid and pagination as a /news/<category> page."""
    from frontend.components.news_page import _GRID_COLUMNS, _pagination_row

    view = NewsState.narrative_view
    return rx.vstack(
        rx.flex(
            rx.heading(rx.cond(view["has_slug"], view["label"], "Narrative Radar"), size="6"),
            rx.text(
                rx.cond(
                    view["has_slug"],
                    "Crypto news in this category, with the coin each story moves, picked by AI.",
                    "Crypto news with the coin and narrative each story moves, picked by AI.",
                ),
                size="2",
                color_scheme="gray",
            ),
            rx.cond(
                view["has_slug"],
                rx.link(rx.text("← All narratives", size="2"), href="/narrative", underline="none", color_scheme="indigo"),
            ),
            rx.badge(view["article_count"], " articles", color_scheme="gray", variant="soft", size="2"),
            direction="column",
            spacing="3",
            align="center",
            text_align="center",
            width="100%",
        ),
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
