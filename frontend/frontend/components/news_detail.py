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
            # The category badge links to that category's own page (/news/<category>).
            rx.link(
                rx.badge(article["news_type"], color_scheme=article["news_type_color"], variant="soft", size="1", cursor="pointer"),
                href=article["category_url"],
                underline="none",
            ),
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


def _nav_card(article: dict, prefix: str, label: str) -> rx.Component:
    """The previous / next story as a card that is always shown (no hover): the picture on the left, the title and excerpt on the
    right. The whole card is the link; Previous sits in the left column and Next in the right one."""
    return rx.link(
        rx.box(
            rx.box(
                rx.image(
                    src=article[f"{prefix}_image"],
                    width="100%",
                    height="100%",
                    object_fit="cover",
                    display="block",
                    custom_attrs={"data-fallback-src": article[f"{prefix}_fallback"]},
                ),
                class_name="news-nav-img",
            ),
            rx.vstack(
                rx.text(article[f"{prefix}_title"], size="2", weight="bold", color="var(--gray-12)", line_height="1.3", class_name="news-nav-title"),
                rx.cond(
                    article[f"{prefix}_snippet"] != "",
                    rx.text(article[f"{prefix}_snippet"], size="1", color="var(--gray-11)", line_height="1.45", class_name="news-nav-excerpt"),
                ),
                spacing="1",
                align="start",
                min_width="0",
            ),
            class_name="news-nav-card",
        ),
        href=article[f"{prefix}_url"],
        underline="none",
        aria_label=label + " story",
        title=label + " story",
        class_name="news-nav-link news-nav-" + prefix,
    )


def _prev_next(article: dict, in_sidebar: bool = False) -> rx.Component:
    """The neighbouring stories of the same category as two cards (Previous = the next-newer one on the left, Next = the
    next-older one on the right, like the /news lists): at the top of the article and, stacked, under the article source in the
    sidebar. A side with no neighbour (the newest story has no Previous, the oldest no Next) is simply not there."""
    return rx.cond(
        article["has_prev"] | article["has_next"],
        rx.box(
            rx.cond(article["has_prev"], _nav_card(article, "prev", "Previous")),
            rx.cond(article["has_next"], _nav_card(article, "next", "Next")),
            class_name="news-prev-next news-nav-side" if in_sidebar else "news-prev-next news-nav-main",
        ),
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
        _prev_next(article, in_sidebar=True),  # previous / next in this category, right below the article source section
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


def _lang_tab(code: str, label: str) -> rx.Component:
    return rx.el.button(
        label,
        type="button",
        class_name=rx.cond(NewsDetailState.summary_lang == code, "ai-lang-btn ai-lang-active", "ai-lang-btn"),
        aria_pressed=rx.cond(NewsDetailState.summary_lang == code, "true", "false"),
        title="English" if code == "en" else "Bahasa Malaysia",
        on_click=NewsDetailState.set_summary_lang(code),
    )


def _summary_heading(show_tabs: bool) -> rx.Component:
    """"AI Summarizations" + sparkles on the left (always English), the EN | MY tabs on the right, full width."""
    return rx.hstack(
        rx.hstack(
            rx.heading("AI Summarizations", size="4"),
            rx.icon("sparkles", size=16, color="var(--gray-9)"),
            spacing="2",
            align="center",
        ),
        rx.cond(
            show_tabs,
            rx.box(_lang_tab("en", "EN"), _lang_tab("ms", "MY"), class_name="ai-lang", role="group", aria_label="Summary language"),
        ),
        width="100%",
        justify="between",
        align="center",
    )


def _ai_summary() -> rx.Component:
    """AI summary card above the article body (same look as the coin page's "AI Summarizations" card), with EN | MY tabs:
    MY translates the whole summary to Malay (first use asks the AI and caches it on the article)."""
    skeleton = rx.box(
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
    )
    return rx.cond(
        NewsDetailState.summary_status == "loading",
        rx.vstack(_summary_heading(False), skeleton, spacing="3", align="start", width="100%"),
        rx.cond(
            NewsDetailState.summary_status == "ready",
            rx.vstack(
                _summary_heading(True),
                rx.cond(
                    (NewsDetailState.summary_lang == "ms") & (NewsDetailState.summary_ms_status == "loading"),
                    rx.vstack(
                        rx.text("Translating the summary to Malay…", size="1", color_scheme="gray"),
                        skeleton,
                        spacing="2",
                        align="start",
                        width="100%",
                    ),
                    rx.box(
                        rx.cond(
                            (NewsDetailState.summary_lang == "ms") & (NewsDetailState.summary_ms_status == "none"),
                            rx.text(
                                "The Malay translation is not available right now. Showing the English summary.",
                                size="1",
                                color="var(--amber-11)",
                                margin_bottom="0.75em",
                            ),
                        ),
                        rx.vstack(
                            rx.foreach(
                                NewsDetailState.summary_shown,
                                lambda section: rx.vstack(
                                    rx.cond(section["title"] != "", rx.text(section["title"], size="2", weight="bold")),
                                    rx.text(section["text"], size="2", line_height="1.6", color="var(--gray-12)"),
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
                            rx.text(
                                "Generated by AI",
                                size="1",
                                color_scheme="gray",
                                style={"font-style": "italic"},
                            ),
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
            rx.image(src=item["src"], width="100%", height="100%", object_fit="cover", display="block", class_name="news-photo", alt="Article photo"),
            **frame,
        ),
    )


def _video_embed(article: dict) -> rx.Component:
    """Telegram's own public post widget (<url>?embed=1), a real iframe —
    not rx.html, which would tear the widget down on every background state
    update (see .claude/rules/reflex-frontend.md). Plays the video inline,
    streamed straight from Telegram's CDN; nothing is stored on our side.
    A generous fixed height since the widget's own content (caption,
    reactions, footer) varies in height and we can't resize to it from a
    cross-origin iframe."""
    return rx.box(
        rx.el.iframe(
            src=article["video_embed_url"],
            title="Telegram post",
            custom_attrs={"frameborder": "0", "allowfullscreen": "true"},
            width="100%",
            height="100%",
            style={"border": "0", "display": "block"},
        ),
        width="100%",
        height="620px",
        border_radius="6px",
        overflow="hidden",
        background="var(--gray-a3)",
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
        rx.grid(
            rx.vstack(
                _prev_next(article),
                _article_metadata(article),
                rx.heading(
                    article["title"],
                    size="7",
                    line_height="1.08",
                    letter_spacing="0",
                ),
                rx.cond(
                    article["has_video_embed"],
                    _video_embed(article),
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
                                class_name="news-reader-image news-photo",
                                custom_attrs={"data-fallback-src": article["fallback_image_url"]},
                            ),
                            width="100%",
                            aspect_ratio="16 / 9",
                            overflow="hidden",
                            border_radius="6px",
                            background="var(--gray-a3)",
                        ),
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