"""Editorial reader for one persisted /news/[news_category]/[article_slug] record."""

import reflex as rx

from frontend.components.coin_detail import _ai_provider_icon
from frontend.state import NewsDetailState

# 1 column on mobile, 3 across at tablet/iPad width (768px+), back to 1 in the narrow desktop rail (1280px+).
_RELATED_GRID_COLUMNS = rx.breakpoints(initial="1", sm="3", lg="1")


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
        rx.vstack(
            rx.text("Article source", size="1", weight="bold", color_scheme="gray", margin_bottom="5px"),
            rx.text(article["source_name"], size="4", weight="bold", line_height="1.2"),
            spacing="0",
            align="start",
        ),
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
                            height="100%",
                            overflow="hidden",
                            border="1px solid var(--gray-a4)",
                            border_radius="6px",
                            background="var(--gray-a2)",
                        ),
                        href=related["detail_url"],
                        underline="none",
                        color="var(--gray-12)",
                        width="100%",
                        display="block",
                        height="100%",
                    ),
                ),
                columns=_RELATED_GRID_COLUMNS,
                spacing="3",
                width="100%",
            ),
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


def _body_segment(segment: dict) -> rx.Component:
    """One piece of a body line: plain text, or a URL as a real link that
    opens in a new tab, with an external-link icon."""
    return rx.cond(
        segment["is_link"],
        rx.link(
            segment["text"],
            rx.icon("external-link", size=14, style={"display": "inline", "vertical_align": "-2px", "margin_left": "4px"}),
            href=segment["url"],
            is_external=True,
            word_break="break-all",
        ),
        rx.el.span(segment["text"]),
    )


def _body_segments(block: dict) -> rx.Component:
    return rx.foreach(block["segments"].to(list[dict]), _body_segment)


def _ai_provider_badge() -> rx.Component:
    badge = NewsDetailState.summary_model_badge.to(dict)
    return rx.cond(
        badge["model_display"] != "",
        rx.badge(
            _ai_provider_icon(badge["provider"], 12),
            rx.text(badge["model_display"], size="1"),
            color_scheme="gray",
            variant="surface",
            radius="full",
        ),
    )


def _ai_summary() -> rx.Component:
    """AI summary card above the article body (same look as the coin page's
    "AI Summarizations" card)."""
    heading = rx.hstack(
        rx.heading("AI Summarizations", size="4"),
        rx.icon("sparkles", size=16, color="var(--gray-9)"),
        spacing="2",
        align="center",
    )
    return rx.cond(
        NewsDetailState.summary_status == "loading",
        rx.vstack(
            heading,
            rx.box(
                rx.vstack(
                    rx.skeleton(height="14px", width="35%"),
                    rx.skeleton(height="12px", width="100%"),
                    rx.skeleton(height="12px", width="92%"),
                    rx.skeleton(height="12px", width="70%"),
                    spacing="2",
                    width="100%",
                ),
                padding="1.25em",
                border_radius="10px",
                background="var(--gray-a2)",
                width="100%",
                border="2px solid royalblue",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        rx.cond(
            NewsDetailState.summary_status == "ready",
            rx.vstack(
                heading,
                rx.box(
                    rx.vstack(
                        rx.foreach(
                            NewsDetailState.summary_sections,
                            lambda section: rx.vstack(
                                rx.cond(section["title"] != "", rx.text(section["title"], size="2", weight="bold")),
                                rx.text(section["text"], size="2", line_height="1.6", color="white"),
                                spacing="1",
                                width="100%",
                                align="start",
                            ),
                        ),
                        spacing="3",
                        width="100%",
                        align="start",
                    ),
                    rx.divider(margin_y="0.75em"),
                    rx.hstack(
                        rx.text("Generated by AI", size="1", color_scheme="gray", style={"font-style": "italic"}),
                        _ai_provider_badge(),
                        width="100%",
                        justify="between",
                        align="center",
                        wrap="wrap",
                    ),
                    padding="1.25em",
                    border_radius="10px",
                    background="var(--gray-a2)",
                    width="100%",
                    border="2px solid royalblue",
                ),
                spacing="3",
                align="start",
                width="100%",
            ),
        ),
    )


def _article_body(article: dict) -> rx.Component:
    return rx.cond(
        article["has_body"],
        rx.vstack(
            rx.foreach(
                article["body_blocks"].to(list[dict]),
                lambda block: rx.cond(
                    block["is_heading"],
                    rx.heading(_body_segments(block), size="4", padding_top="0.7em"),
                    rx.text(
                        _body_segments(block),
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


def _media_cell(item: dict, article: dict) -> rx.Component:
    """One cell of the media grid: a playable video, a video too large to
    download (its thumbnail linking to the post on Telegram), or a photo."""
    frame = {
        "grid_column": item["col"],
        "aspect_ratio": item["ratio"],
        "overflow": "hidden",
        "border_radius": "6px",
        "background": "var(--gray-a3)",
        "position": "relative",
        "min_width": "0",
    }
    thumbnail = rx.image(
        src=item["poster"],
        width="100%",
        height="100%",
        object_fit="cover",
        display="block",
    )
    return rx.cond(
        item["is_video"],
        rx.cond(
            item["playable"],
            rx.box(
                rx.el.video(
                    src=item["src"],
                    poster=item["poster"],
                    controls=True,
                    preload="metadata",
                    plays_inline=True,
                    style={"width": "100%", "height": "100%", "object_fit": "contain", "background": "#000", "display": "block"},
                ),
                **frame,
            ),
            rx.link(
                rx.box(
                    thumbnail,
                    rx.hstack(
                        rx.icon("play", size=14),
                        rx.text("Watch on Telegram", size="1"),
                        rx.icon("external-link", size=12),
                        spacing="1",
                        align="center",
                        position="absolute",
                        bottom="8px",
                        left="8px",
                        padding="4px 8px",
                        border_radius="4px",
                        background="rgba(0, 0, 0, 0.65)",
                        color="white",
                    ),
                    **frame,
                ),
                href=article["url"],
                is_external=True,
                underline="none",
                display="block",
                grid_column=item["col"],
            ),
        ),
        rx.box(
            rx.image(src=item["src"], width="100%", height="100%", object_fit="cover", display="block"),
            **frame,
        ),
    )


def _media_grid(article: dict) -> rx.Component:
    return rx.grid(
        rx.foreach(article["media_grid_items"].to(list[dict]), lambda item: _media_cell(item, article)),
        columns=article["media_grid_columns"],
        gap="8px",
        width="100%",
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
                rx.cond(
                    article["has_media_grid"],
                    _media_grid(article),
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
                ),
                _ai_summary(),
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