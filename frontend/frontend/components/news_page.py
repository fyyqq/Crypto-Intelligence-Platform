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


def _news_card(article: dict, *, compact: bool = False) -> rx.Component:
    """compact=True (homepage strip): keeps the post image but hides the source and
    category badges (only the Telegram badge and time remain)."""
    return rx.link(
        rx.vstack(
            rx.cond(
                article["has_image"],
                rx.box(
                    rx.image(
                        src=article["image_url"],
                        width="100%",
                        height="100%",
                        object_fit="cover",
                        display="block",
                        class_name="news-card-image",
                        custom_attrs={"data-fallback-src": article["fallback_image_url"]},
                    ),
                    width="100%",
                    height="160px",
                    min_height="160px",
                    max_height="160px",
                    flex_shrink="0",
                    overflow="hidden",
                ),
            ),
            rx.vstack(
                rx.hstack(
                    rx.hstack(
                        rx.fragment() if compact else rx.badge(article["source_name"], color_scheme=article["badge_color"], variant="surface", size="1"),
                        rx.cond(
                            article["is_telegram"],
                            rx.badge("Telegram News", color_scheme="blue", variant="solid", size="1"),
                        ),
                        rx.fragment() if compact else rx.badge(
                            article["news_type"],
                            color_scheme=article["news_type_color"],
                            variant="soft",
                            size="1",
                        ),
                        spacing="2",
                        align="center",
                        min_width="0",
                        flex_wrap="wrap",
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
        href=article["detail_url"],
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


def _source_pill(section: dict, source: rx.Var[str]) -> rx.Component:
    return rx.box(
        rx.text(source, size="1"),
        on_click=NewsState.set_category_source(section["news_type"], source),
        class_name=rx.cond(
            section["selected_source"] == source,
            "narrative-pill narrative-pill-active",
            "narrative-pill",
        ),
    )


def _section_source_filter(section: dict) -> rx.Component:
    """Draggable/arrow-scrollable slider of the top-10 publishers (plus All),
    ending with an "Other" dropdown holding the remaining publishers. Same
    wrap/track/arrow classes and JS as the narrative filter slider
    (assets/chain_pills.js)."""
    return rx.box(
        rx.box(rx.icon("chevron-left", size=12), class_name="narrative-scroll-btn narrative-scroll-left"),
        rx.box(
            _source_pill(section, "All"),
            rx.foreach(section["top_sources"].to(list[str]), lambda source: _source_pill(section, source)),
            rx.cond(
                section["has_other_sources"],
                rx.select(
                    section["other_sources"].to(list[str]),
                    value=section["other_selected"],
                    placeholder="Other",
                    on_change=lambda value: NewsState.set_category_source(section["news_type"], value),
                    size="1",
                    variant="soft",
                    flex_shrink="0",
                    class_name="news-source-other",
                ),
            ),
            class_name="narrative-pills-track",
        ),
        rx.box(rx.icon("chevron-right", size=12), class_name="narrative-scroll-btn narrative-scroll-right"),
        class_name="narrative-pills-wrap",
    )


def _section_search(section: dict) -> rx.Component:
    return rx.debounce_input(
        rx.input(
            rx.input.slot(rx.icon("search", size=18)),
            value=section["search_text"],
            placeholder="Search title",
            # Same (large) size at every width.
            size="3",
            radius="full",
            width="100%",
            on_change=lambda value: NewsState.set_category_search(section["news_type"], value),
        ),
        debounce_timeout=300,
        width="100%",
    )


def _section_header(section: dict) -> rx.Component:
    """Heading + count | source pill slider | title search — shared by the
    /news sections and the /news/<category> page. Lg+: one row; below lg the
    slider gets its own full-width row 2 with the same gap above and below."""
    return rx.grid(
        # Title and count sit side by side from tablet up, stacked on mobile.
        rx.flex(
            rx.heading(section["news_type"], size="4"),
            rx.badge(section["article_count"], " articles", color_scheme="gray", variant="soft", size="1"),
            direction=rx.breakpoints(initial="column", sm="row"),
            spacing="2",
            align=rx.breakpoints(initial="start", sm="center"),
            grid_column="1",
            grid_row="1",
        ),
        rx.box(
            _section_source_filter(section),
            width="100%",
            min_width="0",
            grid_column=rx.breakpoints(initial="1 / -1", lg="2"),
            grid_row=rx.breakpoints(initial="2", lg="1"),
        ),
        rx.box(
            _section_search(section),
            justify_self="end",
            width=rx.breakpoints(initial="100%", sm="280px"),
            max_width="280px",
            grid_column=rx.breakpoints(initial="2", lg="3"),
            grid_row="1",
        ),
        columns=rx.breakpoints(initial="auto minmax(0, 1fr)", lg="auto minmax(0, 1fr) auto"),
        spacing="4",
        align_items="center",
        width="100%",
    )


def _view_all_button(section: dict) -> rx.Component:
    return rx.link(
        rx.button(
            "View All",
            rx.icon("arrow-right", size=14),
            size="2",
            variant="soft",
            cursor="pointer",
        ),
        href=section["view_all_url"],
        underline="none",
    )


def _section_footer(section: dict) -> rx.Component:
    """Pagination centred, with the "View All" button at the right edge (below
    sm the button drops under the pagination)."""
    return rx.grid(
        rx.box(display=rx.breakpoints(initial="none", sm="block")),
        rx.box(
            rx.cond(
                section["has_pagination"],
                _section_pagination(section["news_type"], section["page"], section["total_pages"]),
            ),
            justify_self="center",
        ),
        rx.box(_view_all_button(section), justify_self=rx.breakpoints(initial="center", sm="end")),
        columns=rx.breakpoints(initial="1", sm="1fr auto 1fr"),
        spacing="3",
        align_items="center",
        width="100%",
    )


def _news_section(section: dict) -> rx.Component:
    return rx.vstack(
        # lg+: heading | source slider (fills the space between) | title search on one row.
        # Below lg (tablet/mobile): heading + search share row 1 (search on the
        # right), the slider gets its own full-width row 2 with the same gap
        # above and below it.
        _section_header(section),
        rx.grid(
            rx.foreach(section["articles"].to(list[dict]), _news_card),
            columns=_GRID_COLUMNS,
            spacing="4",
            width="100%",
        ),
        _section_footer(section),
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


def _category_not_found() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon("file-question", size=32, color="var(--gray-8)"),
            rx.heading("Category not found", size="5"),
            rx.link("Back to news", href="/news", color="var(--accent-11)", underline="none"),
            spacing="3",
            align="center",
        ),
        min_height="40vh",
        width="100%",
    )


def news_category_content() -> rx.Component:
    """/news/[news_category]: the category's newest 100 articles in the same
    4-column grid, under the same header (source pills + title search)."""
    view = NewsState.view_all
    return rx.vstack(
        rx.link(
            rx.hstack(rx.icon("arrow-left", size=16), rx.text("All news", size="2"), spacing="1", align="center"),
            href="/news",
            underline="none",
            color="var(--gray-11)",
        ),
        rx.cond(
            NewsState.is_loading,
            _loading_skeleton(),
            rx.cond(
                view["found"],
                rx.vstack(
                    _section_header(view),
                    rx.text(
                        "Showing the ",
                        view["shown_count"],
                        " newest of ",
                        view["article_count"],
                        " articles",
                        size="2",
                        color_scheme="gray",
                    ),
                    rx.cond(
                        view["article_count"].to(int) > 0,
                        rx.grid(
                            rx.foreach(view["articles"].to(list[dict]), _news_card),
                            columns=_GRID_COLUMNS,
                            spacing="4",
                            width="100%",
                        ),
                        rx.center(
                            rx.text("No news matches this filter.", size="3", color_scheme="gray"),
                            min_height="30vh",
                            width="100%",
                        ),
                    ),
                    spacing="4",
                    align="start",
                    width="100%",
                ),
                _category_not_found(),
            ),
        ),
        spacing="4",
        width="100%",
        padding=["1em", "1em", "1.5em", "2em", "2em"],
    )
