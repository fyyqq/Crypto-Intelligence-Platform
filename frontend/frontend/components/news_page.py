"""The /news page's real content — replaces frontend.py's old
_placeholder_page("News") shell. Groups real articles (ingested by
app/services/news_pipeline.py into the news_articles table) by their real
outlet name, one section per outlet, each a 3-column x 2-row grid with its
own independent pagination — see frontend/state/news_state.py.
"""

import reflex as rx

from frontend.state import NewsState


def _news_card(article: dict) -> rx.Component:
    return rx.link(
        rx.vstack(
            rx.hstack(
                rx.badge(article["source_name"], color_scheme=article["badge_color"], variant="surface", size="1"),
                rx.text(article["time_display"], size="1", color_scheme="gray"),
                spacing="2",
                align="center",
            ),
            rx.text(article["title"], weight="bold", size="3", style={"display": "-webkit-box", "-webkit-line-clamp": "3", "-webkit-box-orient": "vertical", "overflow": "hidden"}),
            rx.cond(
                article["has_snippet"],
                rx.text(
                    article["snippet"],
                    size="2",
                    color_scheme="gray",
                    style={"display": "-webkit-box", "-webkit-line-clamp": "3", "-webkit-box-orient": "vertical", "overflow": "hidden"},
                ),
            ),
            spacing="2",
            align="start",
            width="100%",
            height="100%",
            padding="1em",
            border="1px solid var(--gray-a5)",
            border_radius="12px",
            background="var(--gray-a2)",
            class_name="news-card",
        ),
        href=article["url"],
        is_external=True,
        underline="none",
        color="inherit",
        width="100%",
        height="100%",
    )


def _section_pagination(source_name: str, page: rx.Var, total_pages: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon("chevron-left", size=16),
            on_click=NewsState.prev_page(source_name),
            class_name="page-arrow-btn",
        ),
        rx.text("Page ", page, " of ", total_pages, size="2", color_scheme="gray", white_space="nowrap"),
        rx.box(
            rx.icon("chevron-right", size=16),
            on_click=NewsState.next_page(source_name),
            class_name="page-arrow-btn",
        ),
        spacing="2",
        align="center",
        justify="center",
        width="100%",
    )


def _news_section(section: dict) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading(section["source_name"], size="4"),
            rx.badge(section["article_count"], " articles", color_scheme="gray", variant="soft", size="1"),
            spacing="2",
            align="center",
        ),
        rx.grid(
            rx.foreach(section["articles"].to(list[dict]), _news_card),
            columns=rx.breakpoints(initial="1", sm="2", md="3"),
            spacing="4",
            width="100%",
        ),
        rx.cond(
            section["has_pagination"],
            _section_pagination(section["source_name"], section["page"], section["total_pages"]),
        ),
        spacing="4",
        align="start",
        width="100%",
        padding_bottom="2em",
        border_bottom="1px solid var(--gray-a4)",
    )


def _empty_state() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon("newspaper", size=32, color="var(--gray-8)"),
            rx.text("No news articles yet", size="4", weight="bold"),
            rx.text(
                "Run app/services/news_pipeline.py to ingest real articles from RSS feeds and Google News.",
                size="2",
                color_scheme="gray",
            ),
            spacing="2",
            align="center",
        ),
        min_height="240px",
        width="100%",
    )


def _loading_skeleton() -> rx.Component:
    return rx.vstack(
        rx.grid(
            *[rx.skeleton(height="180px", width="100%", border_radius="12px") for _ in range(6)],
            columns=rx.breakpoints(initial="1", sm="2", md="3"),
            spacing="4",
            width="100%",
        ),
        width="100%",
    )


def news_page_content() -> rx.Component:
    return rx.vstack(
        rx.heading("News", size="6"),
        rx.cond(
            NewsState.is_loading,
            _loading_skeleton(),
            rx.cond(
                NewsState.has_articles,
                rx.foreach(NewsState.news_sections, _news_section),
                _empty_state(),
            ),
        ),
        spacing="5",
        width="100%",
        padding=["1em", "1em", "1.5em", "2em", "2em"],
    )
