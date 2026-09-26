"""Repace — Reflex app entrypoint."""

import reflex as rx

from frontend.components import coin_detail_page, coin_table, filter_bar, footer, narrative_alerts, news_feed
from frontend.state import CoinState


def _profile_pill() -> rx.Component:
    # Hardcoded placeholder (name, plan, avatar) — no real image, since this
    # will become a customizable user profile (background image, name, plan
    # tier) once that's wired up. background uses Radix's own alpha-gray
    # tokens so it recolors automatically with the light/dark toggle instead
    # of a fixed hex value.
    return rx.hstack(
        rx.vstack(
            rx.text("Fyqq", size="2", weight="bold"),
            rx.badge("Standard", color_scheme="gray", size="1"),
            spacing="1",
            align="start",
            # Hidden below the iPad-portrait breakpoint (md, 768px) — on a
            # phone-width header there isn't room for both this text column
            # and the color-mode button, so the pill collapses to just the
            # avatar there.
            display=["none", "none", "flex", "flex", "flex"],
        ),
        rx.box(
            rx.icon("user", size=22, color="var(--gray-9)"),
            # Fixed equal width/height (not aspect_ratio + align="stretch")
            # — that combination rendered as an oval in practice, not a
            # circle. A fixed size plus the default center alignment below
            # keeps it a true circle with even spacing on every side.
            width="44px",
            height="44px",
            border_radius="9999px",
            background="var(--gray-a5)",
            display="flex",
            align_items="center",
            justify_content="center",
            flex_shrink="0",
        ),
        spacing="3",
        align="center",
        # Symmetric padding once the text column above is hidden (avatar
        # only), back to the wider left padding once it reappears at md+.
        padding=["0.35em", "0.35em", "0.35em 0.35em 0.35em 1em", "0.35em 0.35em 0.35em 1em", "0.35em 0.35em 0.35em 1em"],
        border="1px solid var(--gray-a6)",
        border_radius="9999px",
        background="var(--gray-a2)",
    )


def _header_bar() -> rx.Component:
    # A proper full-bleed nav bar (bottom border + shadow separating it from
    # the scrollable content below) instead of the header just being the
    # first row of the same padded content column — logo/heading/color-mode
    # icon/profile pill are all sized down to fit a nav bar's compact scale
    # rather than the oversized hero-like proportions this had before.
    return rx.box(
        rx.hstack(
            rx.link(
                rx.hstack(
                    rx.color_mode_cond(
                        light=rx.image(src="/logo_light.png", height="28px"),
                        dark=rx.image(src="/logo_dark.png", height="28px"),
                    ),
                    # White reads fine against the header's dark background
                    # in dark mode, but is invisible against its light-mode
                    # background — needs to flip to black there.
                    rx.heading(
                        "Repace", size="6", color=rx.color_mode_cond(light="black", dark="white")
                    ),
                    spacing="2",
                    align="center",
                ),
                href="/",
                underline="none",
            ),
            rx.hstack(
                rx.color_mode.button(size="2"),
                _profile_pill(),
                spacing="3",
                align="center",
            ),
            justify="between",
            align="center",
            width="100%",
        ),
        width="100%",
        padding=["0.6em 1em", "0.6em 1em", "0.75em 1.5em", "0.85em 2em", "0.85em 2em"],
        border_bottom="1px solid var(--gray-a5)",
        box_shadow="0 2px 6px rgba(0, 0, 0, 0.12)",
        background="var(--gray-2)",
    )


def index() -> rx.Component:
    return rx.box(
        _header_bar(),
        rx.vstack(
            news_feed(),
            narrative_alerts(),
            rx.hstack(
                rx.box(
                    filter_bar(),
                    # Full width and stacked above the table below the "lg"
                    # breakpoint (992px, roughly iPad landscape) — a fixed
                    # 300px sidebar next to a 10-column table has no room to
                    # breathe on an iPad portrait or any phone.
                    width=["100%", "100%", "100%", "300px", "300px"],
                    min_width=["0", "0", "0", "280px", "280px"],
                    flex_shrink="0",
                ),
                rx.box(
                    coin_table(),
                    flex="1",
                    min_width="0",
                    width="100%",
                ),
                # Reflex's named breakpoints don't line up 1:1 with its own
                # plain-list positional breakpoints (named "lg" = 1280px, but
                # list index 3 used for width/min_width above = 992px) — "md"
                # is the named key that actually corresponds to 992px, which
                # is what lines this flip up with the sidebar's own width
                # breakpoint instead of firing 288px later than intended.
                direction=rx.breakpoints(initial="column", md="row"),
                align="stretch",
                width="100%",
                style={"gap": "25px"},
            ),
            spacing="4",
            padding=["1em", "1em", "1.5em", "2em", "2em"],
            width="100%",
        ),
        footer(),
        rx.script(src="/chain_pills.js"),
        min_height="100vh",
        width="100%",
    )


def coin_detail() -> rx.Component:
    # min_height (not height) so the page can grow past one viewport when
    # its content needs it — a hard height="100vh" was tried to make the
    # chart fill the screen, but that clipped the *whole page* into one
    # viewport (forcing every column, footer included, into a fixed budget)
    # instead of just bounding the chart. The chart now keeps its own fixed
    # height independent of page height (see coin_detail.py's
    # _CHART_HEIGHTS), so this root just needs a normal min-height floor.
    return rx.box(
        _header_bar(),
        coin_detail_page(),
        footer(),
        # Needed for the X-posts slider's arrow/drag mechanics
        # (coin_detail.py::_x_posts_slider, assets/chain_pills.js) — was
        # previously only loaded on index()'s page, which happened not to
        # matter before since this page's other scroll boxes (sentiment/
        # news) don't use the arrow-slider pattern. A direct/fresh visit to
        # /coin/[symbol] (not navigated to from "/") would otherwise never
        # load this script at all.
        rx.script(src="/chain_pills.js"),
        min_height="100vh",
        width="100%",
        display="flex",
        flex_direction="column",
    )


app = rx.App(stylesheets=["/styles.css"])
# Dynamic routes must be registered before static ones (Reflex route-matching
# order), so /coin/[symbol] is added ahead of the "/" index page below.
# Ticker-based (not cmc_id-based) per explicit request — CoinState.
# selected_coin breaks ties by market cap since tickers aren't unique on CMC.
app.add_page(
    coin_detail,
    route="/coin/[symbol]",
    # Dynamic — the coin's real name, not its ticker (e.g. "Repace —
    # Fartcoin"), per explicit request. See CoinState.page_title; falls back
    # to a generic title before all_coins has loaded.
    title=CoinState.page_title,
    on_load=[
        CoinState.load_coins,
        CoinState.detail_sync_loop,
        CoinState.refresh_coin_description,
        CoinState.refresh_business_summary,
        CoinState.refresh_market_pairs,
        CoinState.refresh_tradingview_dex_symbol,
    ],
)
app.add_page(
    index,
    title="Repace",
    description="Tracking crypto markets in real time, mapping every asset into dynamic narratives, with AI-powered news correlation on the way.",
    image="/favicon_logo.png",
    # `image=` above only sets the og:image social-preview meta tag — the
    # actual browser-tab favicon needs its own <link rel="icon"> tag.
    meta=[rx.el.link(rel="icon", href="/favicon_logo.png", type="image/png")],
    on_load=[CoinState.load_coins, CoinState.live_sync_loop],
)
