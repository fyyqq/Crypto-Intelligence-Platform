"""/tools and its two sub-pages (2026-10-14 split):

- /tools: a landing page with one card per tool (TOOL_PAGES, also the list
  behind the header's "Tools" dropdown): the two sub-pages below and Gainers & Losers.
- /tools/market-indicators: Fear & Greed gauge, Altcoin/Bitcoin Season index
  (data via ToolsState; each has a "data source" popup that also asks for an
  API key when needed) and the BTC / ETH rainbow chart (log-regression bands
  drawn server-side as SVG).
- /tools/crypto-calendar: the monthly @layergg events calendar (see calendar_state / crypto_calendar_service).
- /tools/market-charts: TradingView embeds: DXY, total crypto market cap,
  Bitcoin dominance, ETH/BTC, total market cap excluding BTC.
"""

from urllib.parse import urlencode

import reflex as rx

from frontend.components.tradingview_controls import timeframe_controls
from frontend.state.calendar_state import CalendarState as Cal
from frontend.state.tools_state import ToolsState

_CARD = dict(
    width="100%",
    padding="1.1em",
    border_radius="12px",
    border="1px solid var(--gray-a5)",
    background="var(--gray-a2)",
)



def _fallback_note(note) -> rx.Component:
    """Shown when the chosen CoinMarketCap source failed and the free one was used."""
    return rx.cond(
        note != "",
        rx.hstack(
            rx.icon("info", size=14, color="var(--amber-11)", flex_shrink="0"),
            rx.text(note, size="1", color="var(--amber-11)"),
            spacing="1",
            align="center",
        ),
    )

def _source_button(tool: str) -> rx.Component:
    return rx.button(
        rx.icon("settings-2", size=14),
        "Data source",
        on_click=ToolsState.open_source_dialog(tool),
        variant="soft",
        color_scheme="gray",
        size="1",
        cursor="pointer",
    )


def _section_header(title: str, subtitle: str, right: rx.Component | None = None) -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.heading(title, size="4"),
            rx.text(subtitle, size="1", color_scheme="gray"),
            spacing="1",
            align="start",
        ),
        right if right is not None else rx.fragment(),
        justify="between",
        align="start",
        width="100%",
        spacing="3",
    )


def _key_card(tool: str, env_var) -> rx.Component:
    """Shown instead of the data while the chosen source's key is missing."""
    return rx.vstack(
        rx.icon("key-round", size=26, color="var(--amber-9)"),
        rx.text("API key needed", weight="bold", size="3"),
        rx.text(
            "Add ", rx.code(env_var), " to the .env file, then choose a data source.",
            size="2",
            color_scheme="gray",
            text_align="center",
        ),
        rx.button("Open data source options", on_click=ToolsState.open_source_dialog(tool), size="2", cursor="pointer"),
        spacing="2",
        align="center",
        justify="center",
        min_height="220px",
        width="100%",
    )


def _error_card(message) -> rx.Component:
    return rx.vstack(
        rx.icon("triangle-alert", size=26, color="var(--gray-a9)"),
        rx.text(message, size="2", color_scheme="gray", text_align="center"),
        spacing="2",
        align="center",
        justify="center",
        min_height="220px",
        width="100%",
    )


def _history_item(label: str, value) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="1", color_scheme="gray"),
        rx.text(value, size="2", weight="medium"),
        spacing="0",
        align="center",
    )


def _fng_body() -> rx.Component:
    return rx.vstack(
        rx.box(rx.html(ToolsState.fng_gauge), width="100%", max_width="340px"),
        rx.vstack(
            rx.text(ToolsState.fng_value, size="8", weight="bold", color=ToolsState.fng_color, line_height="1"),
            rx.text(ToolsState.fng_label, size="4", weight="medium", color=ToolsState.fng_color),
            spacing="1",
            align="center",
            margin_top="-0.4em",
        ),
        rx.hstack(
            _history_item("Yesterday", ToolsState.fng_yesterday),
            _history_item("Last week", ToolsState.fng_week),
            _history_item("Last month", ToolsState.fng_month),
            justify="between",
            width="100%",
            wrap="wrap",
            spacing="3",
            margin_top="0.5em",
        ),
        rx.text(
            "Source: ", ToolsState.fng_source_name, " · ", ToolsState.fng_updated,
            size="1",
            color_scheme="gray",
        ),
        _fallback_note(ToolsState.fng_fallback_note),
        spacing="3",
        align="center",
        width="100%",
    )


def fear_greed_section() -> rx.Component:
    return rx.box(
        _section_header("Fear & Greed Index", "Crypto market sentiment, 0 (extreme fear) to 100 (extreme greed).", _source_button("fng")),
        rx.box(
            rx.cond(
                ToolsState.fng_key_missing,
                _key_card("fng", ToolsState.fng_key_env),
                rx.cond(
                    ToolsState.fng_loading,
                    rx.skeleton(height="280px", width="100%", border_radius="8px"),
                    rx.cond(ToolsState.fng_error != "", _error_card(ToolsState.fng_error), _fng_body()),
                ),
            ),
            margin_top="1em",
            width="100%",
        ),
        **_CARD,
    )


def _season_bar() -> rx.Component:
    return rx.vstack(
        rx.box(
            rx.box(
                width="4px",
                height="22px",
                border_radius="2px",
                background="var(--gray-12)",
                position="absolute",
                top="-5px",
                left=ToolsState.season_marker_left,
                transform="translateX(-50%)",
                box_shadow="0 0 0 2px var(--gray-1)",
            ),
            position="relative",
            width="100%",
            height="12px",
            border_radius="6px",
            background="linear-gradient(90deg, #f7931a 0%, #f7931a 25%, var(--gray-a6) 25%, var(--gray-a6) 75%, #16c784 75%, #16c784 100%)",
        ),
        rx.hstack(
            rx.text("Bitcoin Season (0–25)", size="1", color_scheme="gray"),
            rx.text("Altcoin Season (75–100)", size="1", color_scheme="gray"),
            justify="between",
            width="100%",
        ),
        spacing="1",
        width="100%",
    )


def _best_chip(item: dict) -> rx.Component:
    return rx.badge(item["symbol"], " ", item["change"], variant="soft", color_scheme="green", size="2")


def _season_body() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text(ToolsState.season_index, size="8", weight="bold", line_height="1"),
            rx.text("/ 100", size="3", color_scheme="gray", margin_top="1.2em"),
            rx.badge(ToolsState.season_label, size="3", variant="soft"),
            align="center",
            spacing="2",
            wrap="wrap",
        ),
        _season_bar(),
        rx.text(
            ToolsState.season_beat, " of the top ", ToolsState.season_total, " coins beat Bitcoin over ",
            ToolsState.season_window, " (Bitcoin ", ToolsState.season_btc_change, ").",
            size="2",
        ),
        rx.vstack(
            rx.text("Best performers vs Bitcoin", size="1", color_scheme="gray"),
            rx.hstack(
                rx.foreach(ToolsState.season_best, _best_chip),
                wrap="wrap",
                spacing="2",
            ),
            spacing="1",
            align="start",
        ),
        rx.text("Source: ", ToolsState.season_source_name, " · stablecoins and wrapped tokens excluded", size="1", color_scheme="gray"),
        _fallback_note(ToolsState.season_fallback_note),
        spacing="4",
        align="start",
        width="100%",
    )


def altcoin_season_section() -> rx.Component:
    return rx.box(
        _section_header(
            "Altcoin / Bitcoin Season",
            "75%+ of the top 50 coins beating Bitcoin means Altcoin Season; 25% or less means Bitcoin Season.",
            _source_button("season"),
        ),
        rx.box(
            rx.cond(
                ToolsState.season_key_missing,
                _key_card("season", ToolsState.season_key_env),
                rx.cond(
                    ToolsState.season_loading,
                    rx.skeleton(height="240px", width="100%", border_radius="8px"),
                    rx.cond(ToolsState.season_error != "", _error_card(ToolsState.season_error), _season_body()),
                ),
            ),
            margin_top="1em",
            width="100%",
        ),
        **_CARD,
    )


def _legend_chip(item: dict) -> rx.Component:
    return rx.hstack(
        rx.box(width="12px", height="12px", border_radius="3px", background=item["color"], flex_shrink="0"),
        rx.text(item["label"], size="1"),
        spacing="1",
        align="center",
    )


def _asset_tab(asset: str) -> rx.Component:
    active = ToolsState.rainbow_asset == asset
    return rx.button(
        asset,
        on_click=ToolsState.set_rainbow_asset(asset),
        variant=rx.cond(active, "solid", "soft"),
        color_scheme=rx.cond(active, "indigo", "gray"),
        size="1",
        cursor="pointer",
    )


def rainbow_section() -> rx.Component:
    return rx.box(
        _section_header(
            "Rainbow Chart",
            "BTC: the standard logarithmic-growth curve with bands of +/-0.6 decades; ETH: fitted to its own history. Drawn from 2010 and extended about 1.5 years ahead. A guide, not financial advice.",
            rx.hstack(_asset_tab("BTC"), _asset_tab("ETH"), spacing="2"),
        ),
        rx.box(
            rx.cond(
                ToolsState.rainbow_loading,
                rx.skeleton(height="420px", width="100%", border_radius="8px"),
                rx.cond(
                    ToolsState.rainbow_error != "",
                    _error_card(ToolsState.rainbow_error),
                    rx.vstack(
                        rx.hstack(
                            rx.text(ToolsState.rainbow_asset, " ", ToolsState.rainbow_price, size="5", weight="bold"),
                            rx.badge(
                                ToolsState.rainbow_band,
                                size="2",
                                style={"background": ToolsState.rainbow_band_color, "color": "#111827"},
                            ),
                            rx.cond(
                                ToolsState.rainbow_live,
                                rx.hstack(
                                    rx.box(class_name="rainbow-live-dot"),
                                    rx.text(
                                        "Live · ", ToolsState.rainbow_asof, " · ", ToolsState.rainbow_price_source,
                                        size="1",
                                        color_scheme="gray",
                                    ),
                                    spacing="1",
                                    align="center",
                                ),
                                rx.text("as of ", ToolsState.rainbow_asof, " (daily close)", size="1", color_scheme="gray"),
                            ),
                            align="center",
                            spacing="3",
                            wrap="wrap",
                        ),
                        # Static chart + the live overlay (same viewBox, stacked
                        # exactly on top). .rainbow-chart + data-rainbow feed the
                        # hover tooltip in assets/rainbow_hover.js.
                        rx.box(
                            rx.html(ToolsState.rainbow_svg),
                            rx.box(rx.html(ToolsState.rainbow_overlay), class_name="rainbow-overlay"),
                            class_name="rainbow-chart",
                            custom_attrs={"data-rainbow": ToolsState.rainbow_hover},
                            width="100%",
                        ),
                        rx.hstack(
                            rx.foreach(ToolsState.rainbow_legend, _legend_chip),
                            wrap="wrap",
                            spacing="3",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                ),
            ),
            margin_top="1em",
            width="100%",
        ),
        **_CARD,
    )


def _tv_src(symbol: str, theme: str, interval: str = "D") -> str:
    pane = "#000000" if theme == "dark" else "#ffffff"
    params = {
        "symbol": symbol,
        "interval": interval,
        "theme": theme,
        "style": "1",
        "locale": "en",
        "timezone": "Asia/Kuala_Lumpur",
        "toolbarbg": "131722" if theme == "dark" else "f1f3f6",
        "backgroundColor": pane,
        "gridColor": pane,
        "hide_side_toolbar": "1",
        "saveimage": "0",
        "withdateranges": "1",
        "studies": "[]",
        "hideideas": "1",
        "allow_symbol_change": "0",
    }
    return f"https://www.tradingview.com/widgetembed/?{urlencode(params)}"


def _tv_section(title: str, subtitle: str, symbol: str) -> rx.Component:
    return rx.box(
        _section_header(title, subtitle, rx.badge(symbol, variant="soft", color_scheme="gray", size="1")),
        timeframe_controls("D"),
        rx.box(
            rx.el.iframe(
                src=rx.color_mode_cond(light=_tv_src(symbol, "light"), dark=_tv_src(symbol, "dark")),
                custom_attrs={"allowtransparency": "true", "frameborder": "0"},
                title=title,
                width="100%",
                height="100%",
                style={"border": "0", "borderRadius": "8px"},
            ),
            margin_top="1em",
            height=["340px", "380px", "420px", "420px", "420px"],
            width="100%",
        ),
        custom_attrs={"data-tv-chart": "true"},
        **_CARD,
    )


def _dialog_option(option: dict) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.text(option["label"], weight="bold", size="3"),
                    rx.cond(option["selected"], rx.badge("Selected", color_scheme="green", variant="soft", size="1")),
                    rx.cond(
                        option["needs_key"],
                        rx.cond(
                            option["key_present"],
                            rx.badge("Key found in .env", color_scheme="green", variant="outline", size="1"),
                            rx.badge("Key missing", color_scheme="amber", variant="soft", size="1"),
                        ),
                        rx.badge("No key needed", color_scheme="gray", variant="soft", size="1"),
                    ),
                    spacing="2",
                    align="center",
                    wrap="wrap",
                ),
                rx.text(option["desc"], size="2", color_scheme="gray"),
                rx.cond(
                    option["needs_key"] & ~option["key_present"].to(bool),
                    rx.text(
                        "Add ", rx.code(option["env"], "=your_key"),
                        " to the .env file in the project root, then press Re-check.",
                        size="2",
                        color="var(--amber-11)",
                    ),
                ),
                spacing="1",
                align="start",
                flex="1",
                min_width="0",
            ),
            rx.cond(
                option["key_present"] & ~option["selected"].to(bool),
                rx.button("Use this", on_click=ToolsState.choose_source(option["id"]), size="2", cursor="pointer"),
            ),
            justify="between",
            align="center",
            spacing="3",
            width="100%",
        ),
        padding="0.9em",
        border_radius="10px",
        border=rx.cond(option["selected"], "1px solid var(--accent-8)", "1px solid var(--gray-a5)"),
        width="100%",
    )


def _source_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.dialog.title(ToolsState.dialog_title, ": data source", margin="0"),
                rx.dialog.close(rx.icon_button(rx.icon("x", size=18), variant="ghost", color_scheme="gray", cursor="pointer")),
                justify="between",
                align="center",
                width="100%",
            ),
            rx.dialog.description(
                "Pick where this widget gets its data. Sources that need an API key read it from the .env file.",
                size="2",
                color_scheme="gray",
                margin_y="0.5em",
            ),
            rx.vstack(rx.foreach(ToolsState.dialog_options, _dialog_option), spacing="3", width="100%"),
            rx.hstack(
                rx.button(
                    rx.icon("refresh-cw", size=14),
                    "Re-check .env",
                    on_click=ToolsState.recheck_keys,
                    variant="soft",
                    color_scheme="gray",
                    size="2",
                    cursor="pointer",
                ),
                justify="end",
                width="100%",
                margin_top="1em",
            ),
            max_width="560px",
            width="92vw",
        ),
        open=ToolsState.dialog_open,
        on_open_change=ToolsState.dialog_open_change,
    )


# One entry per tool: the landing cards and the header's Tools dropdown are both built from this
# (Gainers & Losers is its own page at /gainers-losers and also keeps its own nav link).
TOOL_PAGES = [
    {
        "title": "Market Indicators",
        "href": "/tools/market-indicators",
        "icon": "gauge",
        "description": "Sentiment and cycle gauges: how fearful or greedy the market is, who is winning (Bitcoin or altcoins), and where Bitcoin sits on its long-term curve.",
        "chips": ["Fear & Greed", "Altcoin Season", "Rainbow Chart"],
    },
    {
        "title": "Market Charts",
        "href": "/tools/market-charts",
        "icon": "chart-line",
        "description": "Live macro and market-structure charts with your own timeframe: dollar strength, total market cap, Bitcoin dominance and more.",
        "chips": ["DXY", "Total Market Cap", "BTC Dominance", "ETH / BTC", "TOTAL2"],
    },
    {
        "title": "Gainers & Losers",
        "href": "/gainers-losers",
        "icon": "arrow-up-down",
        "description": "The biggest movers by rank band over 24 hours, 7 days and 1 month, with saved daily boards you can browse by date.",
        "chips": ["Top Gainers", "Top Losers", "24h · 7d · 1 Month", "Top 100 - 500"],
    },
    {
        "title": "Crypto Calendar",
        "href": "/tools/crypto-calendar",
        "icon": "calendar-days",
        "description": "A month-by-month calendar of token unlocks, launches, macro releases and earnings, taken from the Layergg calendar posts.",
        "chips": ["Crypto", "Macro", "Earnings", "2026"],
    },
]


def _tool_card(page: dict) -> rx.Component:
    """A whole-card link (a real <a>, so middle-click / new tab work)."""
    return rx.link(
        rx.vstack(
            rx.hstack(
                rx.center(
                    rx.icon(page["icon"], size=26),
                    width="52px",
                    height="52px",
                    border_radius="14px",
                    background="var(--accent-a3)",
                    color="var(--accent-11)",
                ),
                rx.spacer(),
                rx.icon("arrow-up-right", size=20, color="var(--gray-10)", class_name="tool-card-arrow"),
                width="100%",
                align="start",
            ),
            rx.heading(page["title"], size="5", color="var(--gray-12)", margin_top="0.4em"),
            rx.text(page["description"], size="2", color="var(--gray-11)", line_height="1.55"),
            rx.hstack(
                *[rx.badge(c, variant="soft", color_scheme="gray", size="1") for c in page["chips"]],
                wrap="wrap",
                spacing="2",
                margin_top="0.4em",
            ),
            rx.spacer(),
            rx.hstack(
                rx.text("Open", size="2", weight="medium"),
                rx.icon("arrow-right", size=16, class_name="tool-card-go"),
                spacing="1",
                align="center",
                color="var(--accent-11)",
                margin_top="0.6em",
            ),
            spacing="2",
            align="start",
            height="100%",
        ),
        href=page["href"],
        underline="none",
        color="inherit",
        class_name="tool-card",
        display="block",
        width="100%",
    )


def _page_header(title: str, subtitle: str, back: bool = True) -> rx.Component:
    return rx.vstack(
        *(
            [
                rx.link(
                    rx.hstack(rx.icon("arrow-left", size=14), rx.text("Market Tools", size="2"), spacing="1", align="center"),
                    href="/tools",
                    underline="none",
                    color="var(--gray-11)",
                    _hover={"color": "var(--gray-12)"},
                )
            ]
            if back
            else []
        ),
        rx.heading(title, size="6"),
        rx.text(subtitle, size="2", color_scheme="gray"),
        spacing="2",
        align="center" if not back else "start",
        text_align="center" if not back else "left",
        width="100%",
    )


_PAGE_PADDING = ["1em", "1em", "1.5em", "2em", "2em"]


def tools_home_content() -> rx.Component:
    """/tools: just the way into the sub-pages."""
    return rx.vstack(
        _page_header("Market Tools", "Sentiment, season and macro indicators, grouped by what you need.", back=False),
        rx.grid(
            *[_tool_card(p) for p in TOOL_PAGES],
            columns=rx.breakpoints(initial="1", sm="2"),  # two columns from tablet width
            spacing="4",
            width="100%",
            max_width="980px",
        ),
        spacing="6",
        align="center",
        width="100%",
        padding=_PAGE_PADDING,
    )


def market_indicators_content() -> rx.Component:
    """/tools/market-indicators: Fear & Greed + Altcoin Season side by side, then the rainbow chart."""
    return rx.vstack(
        _page_header("Market Indicators", "Fear & Greed, Altcoin / Bitcoin Season and the Bitcoin rainbow chart."),
        rx.grid(
            fear_greed_section(),
            altcoin_season_section(),
            columns=rx.breakpoints(initial="1", lg="2"),
            spacing="4",
            width="100%",
        ),
        rainbow_section(),
        _source_dialog(),
        spacing="5",
        width="100%",
        padding=_PAGE_PADDING,
    )


def market_charts_content() -> rx.Component:
    """/tools/market-charts: the five TradingView embeds."""
    return rx.vstack(
        _page_header("Market Charts", "Dollar index, total market cap, Bitcoin dominance, ETH/BTC and TOTAL2, with your own timeframe."),
        rx.grid(
            _tv_section("US Dollar Index (DXY)", "Dollar strength against a basket of major currencies.", "CAPITALCOM:DXY"),
            _tv_section("Total Crypto Market Cap", "Value of the whole crypto market.", "CRYPTOCAP:TOTAL"),
            _tv_section("Bitcoin Dominance", "Bitcoin's share of the total crypto market cap.", "CRYPTOCAP:BTC.D"),
            _tv_section("ETH / BTC", "Ether priced in bitcoin; rises when ETH outperforms.", "BINANCE:ETHBTC"),
            _tv_section("Total Market Cap excl. BTC", "The whole crypto market without Bitcoin (TOTAL2).", "CRYPTOCAP:TOTAL2"),
            columns=rx.breakpoints(initial="1", lg="2"),
            spacing="4",
            width="100%",
        ),
        spacing="5",
        width="100%",
        padding=_PAGE_PADDING,
    )


def _chip(chip: rx.Var[dict]) -> rx.Component:
    """A month chip (Jan, Feb ...): accent when it is the open month, dimmed when it has no events."""
    return rx.box(
        rx.text(chip["label"], size="2", weight="medium"),
        class_name="cal-chip",
        custom_attrs={"data-active": chip["active"], "data-data": chip["has_data"]},
        on_click=Cal.go(chip["index"]),
    )


def crypto_calendar_content() -> rx.Component:
    """/tools/crypto-calendar: the @layergg monthly calendar, a month at a time (full width)."""
    arrow = dict(variant="soft", color_scheme="gray", size="2", cursor="pointer")
    legend = rx.hstack(
        *[
            rx.hstack(rx.box(class_name=f"cal-dot cal-dot-{k}"), rx.text(label, size="1", color="var(--gray-11)"), spacing="1", align="center")
            for k, label in (("crypto", "Crypto"), ("macro", "Macro"), ("earnings", "Stocks & earnings"))
        ],
        spacing="3",
        wrap="wrap",
    )
    return rx.vstack(
        _page_header("Crypto Calendar", "Dated crypto, macro and earnings events from the monthly calendar post of @layergg."),
        rx.hstack(
            rx.hstack(
                rx.icon_button(rx.icon("chevron-left", size=18), on_click=Cal.prev_month, disabled=Cal.index <= 0, aria_label="Previous month", **arrow),
                rx.heading(Cal.month_title, size="5", min_width="9em", text_align="center"),
                rx.icon_button(rx.icon("chevron-right", size=18), on_click=Cal.next_month, disabled=Cal.index >= Cal.keys.length() - 1, aria_label="Next month", **arrow),
                spacing="3",
                align="center",
            ),
            rx.spacer(),
            legend,
            align="center",
            width="100%",
            wrap="wrap",
            spacing="3",
        ),
        rx.box(
            rx.hstack(rx.foreach(Cal.chips, _chip), spacing="2", class_name="cal-chips"),
            width="100%",
            overflow_x="auto",
            class_name="hide-scrollbar",
        ),
        rx.cond(
            Cal.loaded,
            rx.cond(
                Cal.keys.length() > 0,
                rx.html(Cal.month_html, width="100%"),
                rx.center(rx.text("No calendar yet.", size="2", color="var(--gray-11)"), min_height="30vh", width="100%"),
            ),
            rx.skeleton(height="520px", width="100%", border_radius="12px"),
        ),
        rx.cond(
            Cal.post_url != "",
            rx.link(
                rx.hstack(rx.icon("send", size=14), rx.text("Source: this month's post on t.me/layergg", size="1"), spacing="1", align="center"),
                href=Cal.post_url,
                is_external=True,
                color="var(--gray-11)",
                underline="hover",
            ),
        ),
        spacing="4",
        width="100%",
        padding=_PAGE_PADDING,
    )
