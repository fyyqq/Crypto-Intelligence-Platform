"""Homepage news strips: real, live articles from one /news category each
(the same rows and 60s live refresh as the /news page — see NewsState).
Replaces the old dummy placeholder feed."""

import reflex as rx

from frontend.components.news_page import _news_card as _real_news_card
from frontend.state import NewsState


def _news_slider(articles: rx.Var) -> rx.Component:
    # Same draggable/arrow-scrollable slider mechanics as the narrative
    # alerts (assets/chain_pills.js — its selectors include these
    # news-slider class names too), but showing the real /news cards (same
    # rows, same live refresh) instead of the old dummy items.
    return rx.box(
        rx.box(
            rx.icon("chevron-left", size=14),
            class_name="news-scroll-btn news-scroll-left",
        ),
        rx.box(
            rx.foreach(
                articles.to(list[dict]),
                lambda article: rx.box(
                    _real_news_card(article),
                    width=["240px", "260px", "280px", "300px", "300px"],
                    flex_shrink="0",
                ),
            ),
            class_name="news-slider-track",
        ),
        rx.box(
            rx.icon("chevron-right", size=14),
            class_name="news-scroll-btn news-scroll-right",
        ),
        class_name="news-slider-wrap",
    )


def _more_news_link(href: str) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.text("More News", size="2", weight="bold"),
            rx.icon("arrow-right", size=14),
            spacing="1",
            align="center",
        ),
        href=href,
        underline="none",
        color_scheme="indigo",
    )


def news_feed(heading: str, articles: rx.Var, more_href: str, eyebrow: bool = True) -> rx.Component:
    """One homepage news strip: real, live articles from one /news category."""
    return rx.vstack(
        rx.text("GLOBAL INTELLIGENCE FEED", size="1", color_scheme="gray", weight="bold") if eyebrow else rx.fragment(),
        rx.box(
            rx.heading(heading, size="5"),
            _more_news_link(more_href),
            display="flex",
            justify_content="space-between",
            align_items="center",
            width="100%",
        ),
        rx.cond(
            NewsState.is_loading,
            rx.hstack(
                *[rx.skeleton(width="280px", height="260px", border_radius="12px", flex_shrink="0") for _ in range(4)],
                spacing="3",
                width="100%",
                overflow_x="hidden",
            ),
            _news_slider(articles),
        ),
        spacing="3",
        width="100%",
        align_items="stretch",
    )
