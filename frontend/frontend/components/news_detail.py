"""Editorial reader for one persisted /news/[news_category]/[article_slug] record."""

import reflex as rx

from frontend.state import NewsDetailState

# 1 column on mobile, 4 across from tablet/iPad width (768px) up, back to 1 in the narrow desktop rail (1280px+).
_RELATED_GRID_COLUMNS = rx.breakpoints(initial="1", sm="4", lg="1")


def _article_metadata(article: dict) -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.badge(article["source_name"], color_scheme=article["badge_color"], variant="surface", size="1"),
            rx.cond(
                article["is_telegram"],
                rx.badge("Telegram News", color_scheme="blue", variant="solid", size="1"),
            ),
            rx.badge(article["news_type"], color_scheme=article["news_type_color"], variant="soft", size="1"),
            spacing="2",
            flex_wrap="wrap",
        ),
        rx.text(article["published_display"], size="2", color_scheme="gray", white_space="nowrap"),
        width="100%",
        justify="between",
        align="center",
        flex_wrap="wrap",
        row_gap="0.5em",
    )


def _source_link(article: dict) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.text("View original source", size="2", weight="medium"),
            rx.icon("arrow-up-right", size=15),
            spacing="1",
            align="center",
        ),
        href=article["url"],
        is_external=True,
        underline="none",
        color="var(--accent-11)",
    )


def _article_sidebar(article: dict) -> rx.Component:
    return rx.vstack(
        rx.text("Article source", size="2", weight="bold", color_scheme="gray"),
        rx.text(article["source_name"], size="4", weight="bold"),
        _source_link(article),
        rx.vstack(
            rx.heading("Other News Related", size="3"),
            rx.grid(
                rx.foreach(
                    article["related_articles"].to(list[dict]),
                    lambda related: rx.link(
                        rx.vstack(
                            rx.box(
                                rx.image(
                                    src=related["image_url"],
                                    width="100%",
                                    height="100%",
                                    object_fit="cover",
                                    display="block",
                                    custom_attrs={"data-fallback-src": related["fallback_image_url"]},
                                ),
                                width="100%",
                                aspect_ratio="16 / 9",
                                overflow="hidden",
                                background="var(--gray-a3)",
                            ),
                            rx.vstack(
                                rx.text(related["title"], size="2", weight="medium", line_height="1.35"),
                                rx.cond(
                                    related["has_snippet"],
                                    rx.text(
                                        related["snippet"],
                                        size="1",
                                        color_scheme="gray",
                                        line_height="1.4",
                                        style={
                                            "display": "-webkit-box",
                                            "-webkit-line-clamp": "2",
                                            "-webkit-box-orient": "vertical",
                                            "overflow": "hidden",
                                        },
                                    ),
                                ),
                                spacing="1",
                                align="start",
                                min_width="0",
                                width="100%",
                                padding="0.7em",
                            ),
                            spacing="0",
                            align="start",
                            width="100%",
                            overflow="hidden",
                            border="1px solid var(--gray-a4)",
                            border_radius="6px",
                            background="var(--gray-a2)",
                        ),
                        href=related["detail_url"],
                        underline="none",
                        color="var(--gray-12)",
                        width="100%",
                    ),
                ),
                columns=_RELATED_GRID_COLUMNS,
                spacing="3",
                width="100%",
            ),
            rx.button("View More", variant="soft", color_scheme="gray", width="100%"),
            spacing="2",
            align="start",
            width="100%",
            padding_top="1em",
            border_top="1px solid var(--gray-a4)",
        ),
        spacing="3",
        align="start",
        border_left=rx.breakpoints(initial="none", lg="1px solid var(--gray-a5)"),
        padding_left=rx.breakpoints(initial="0", lg="1.5em"),
        margin_top=rx.breakpoints(initial="0", lg="5.4em"),
        width="100%",
    )


def _article_body(article: dict) -> rx.Component:
    return rx.cond(
        article["has_body"],
        rx.vstack(
            rx.foreach(
                article["body_blocks"].to(list[dict]),
                lambda block: rx.cond(
                    block["is_heading"],
                    rx.heading(block["text"], size="4", padding_top="0.7em"),
                    rx.text(
                        block["text"],
                        size="3",
                        line_height="1.8",
                        color="var(--gray-12)",
                    ),
                ),
            ),
            spacing="4",
            align="start",
            width="100%",
        ),
        rx.vstack(
            rx.heading("Original text is unavailable", size="4"),
            rx.text(
                "This publisher did not expose an extractable article body when the archive was scanned.",
                size="3",
                color_scheme="gray",
                line_height="1.65",
            ),
            _source_link(article),
            spacing="3",
            align="start",
            padding_y="1em",
        ),
    )


def _reader(article: dict) -> rx.Component:
    return rx.vstack(
        rx.link(
            rx.hstack(rx.icon("arrow-left", size=16), rx.text("All news", size="2"), spacing="1", align="center"),
            href="/news",
            underline="none",
            color="var(--gray-11)",
        ),
        rx.grid(
            rx.vstack(
                _article_metadata(article),
                rx.heading(
                    article["title"],
                    size="7",
                    line_height="1.08",
                    letter_spacing="0",
                ),
                rx.box(
                    rx.image(
                        src=article["image_url"],
                        width="100%",
                        height="100%",
                        object_fit="cover",
                        display="block",
                        class_name="news-reader-image",
                        custom_attrs={"data-fallback-src": article["fallback_image_url"]},
                    ),
                    width="100%",
                    aspect_ratio="16 / 9",
                    overflow="hidden",
                    border_radius="6px",
                    background="var(--gray-a3)",
                ),
                _article_body(article),
                spacing="5",
                align="start",
                min_width="0",
                width="100%",
            ),
            _article_sidebar(article),
            columns=rx.breakpoints(initial="1", lg="minmax(0, 1fr) 260px"),
            column_gap=rx.breakpoints(initial="2em", lg="3.5em"),
            row_gap="2.5em",
            width="100%",
        ),
        spacing="6",
        width="100%",
        max_width="1120px",
        margin_x="auto",
        padding=["1.25em", "1.5em", "2em", "3em", "4em"],
    )


def _not_found() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon("file-question", size=32, color="var(--gray-8)"),
            rx.heading("Article not found", size="5"),
            rx.text("This news record is not available in the archive.", size="3", color_scheme="gray"),
            rx.link("Back to news", href="/news", color="var(--accent-11)", underline="none"),
            spacing="3",
            align="center",
        ),
        min_height="55vh",
        width="100%",
    )


def news_detail_content() -> rx.Component:
    return rx.cond(
        NewsDetailState.is_loading,
        rx.center(rx.spinner(size="3"), min_height="55vh", width="100%"),
        rx.cond(NewsDetailState.article_found, _reader(NewsDetailState.article), _not_found()),
    )