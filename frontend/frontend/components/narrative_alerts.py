"""Homepage "Targeted Narrative + Coin": real Cryptocurrency news, each tied by
AI to one coin and its narrative (app/services/news_targeting_service.py).
Same slider mechanics as the news strip above it (drag, arrows, autoplay —
the news-slider-* classes in assets/chain_pills.js); text-only cards."""

import reflex as rx

from frontend.state import NewsState


def _alert_card(article: rx.Var) -> rx.Component:
    return rx.link(
        rx.box(
            rx.hstack(
                rx.badge(article["target_symbol"], color_scheme="indigo", size="1"),
                rx.badge(article["target_narrative"], color_scheme="orange", size="1"),
                rx.spacer(),
                rx.text(article["time_display"], size="1", color_scheme="gray", flex_shrink="0"),
                width="100%",
                align="center",
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
        width=["270px", "290px", "310px", "340px", "340px"],
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
            rx.heading("Targeted Narrative + Coin", size=rx.breakpoints(initial="4", sm="5")),
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
