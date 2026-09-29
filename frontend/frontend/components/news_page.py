"""The /news page's real content — replaces frontend.py's old
_placeholder_page("News") shell. Groups real articles (ingested by
app/services/news_pipeline.py into the news_articles table) by normalized
news type, one section per category, each a 4-column x 3-row grid with its
own independent pagination and real-source filter dropdown — see
frontend/state/news_state.py.
"""

import reflex as rx

from frontend.state import NewsState

_GRID_COLUMNS = rx.breakpoints(initial="1", sm="2", md="3", lg="4")


def _news_card(article: dict) -> rx.Component:
    return rx.link(
        rx.vstack(
            rx.cond(
                article["has_image"],
                rx.image(
                    src=article["image_url"],
                    width="100%",
                    height="160px",
                    object_fit="cover",
                    display="block",
                ),
            ),
            rx.vstack(
                rx.hstack(
                    rx.hstack(
                        rx.badge(article["source_name"], color_scheme=article["badge_color"], variant="surface", size="1"),
                        rx.badge(
                            article["news_type"],
                            color_scheme=article["news_type_color"],
                            variant="soft",
                            size="1",
                        ),
                        spacing="2",
                        align="center",
                        min_width="0",
                    ),
                    rx.text(article["time_display"], size="1", color_scheme="gray", white_space="nowrap"),
                    spacing="2",
                    align="center",
                    justify="between",
                    width="100%",
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
            ),
            spacing="0",
            align="start",
            width="100%",
            height="100%",
            border="1px solid var(--gray-a5)",
            border_radius="12px",
            background="var(--gray-a2)",
            overflow="hidden",
            class_name="news-card",
        ),
        href=article["url"],
        is_external=True,
        underline="none",
        color="inherit",
        width="100%",
        height="100%",
    )


def _section_pagination(news_type: str, page: rx.Var, total_pages: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon("chevrons-left", size=16),
            on_click=NewsState.first_page(news_type),
            class_name="page-arrow-btn",
        ),
        rx.box(
            rx.icon("chevron-left", size=16),
            on_click=NewsState.prev_page(news_type),
            class_name="page-arrow-btn",
        ),
        rx.text("Page ", page, " of ", total_pages, size="2", color_scheme="gray", white_space="nowrap"),
        rx.box(
            rx.icon("chevron-right", size=16),
            on_click=NewsState.next_page(news_type),
            class_name="page-arrow-btn",
        ),
        rx.box(
            rx.icon("chevrons-right", size=16),
            on_click=NewsState.last_page(news_type),
            class_name="page-arrow-btn",
        ),
        spacing="2",
        align="center",
        justify="center",
        width="100%",
    )


def _section_source_filter(section: dict) -> rx.Component:
    return rx.select(
        section["sources"].to(list[str]),
        value=section["selected_source"],
        on_change=lambda value: NewsState.set_category_source(section["news_type"], value),
        size="1",
    )


def _news_section(section: dict) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.hstack(
                rx.heading(section["news_type"], size="4"),
                rx.badge(section["article_count"], " articles", color_scheme="gray", variant="soft", size="1"),
                spacing="2",
                align="center",
            ),
            _section_source_filter(section),
            justify="between",
            align="center",
            width="100%",
        ),
        rx.grid(
            rx.foreach(section["articles"].to(list[dict]), _news_card),
            columns=_GRID_COLUMNS,
            spacing="4",
            width="100%",
        ),
        rx.cond(
            section["has_pagination"],
            _section_pagination(section["news_type"], section["page"], section["total_pages"]),
        ),
        id=section["anchor_id"],
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
            *[rx.skeleton(height="320px", width="100%", border_radius="12px") for _ in range(12)],
            columns=_GRID_COLUMNS,
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
