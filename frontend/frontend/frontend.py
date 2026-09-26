"""Repace — Reflex app entrypoint."""

import reflex as rx

from frontend.components import (
    coin_detail_page,
    coin_table,
    filter_bar,
    footer,
    global_search,
    narrative_alerts,
    news_feed,
)
from frontend.state import CoinState


def _watchlist_menu_item() -> rx.Component:
    # Same "star" icon already used (currently unwired) next to a coin's
    # name on its own detail page (coin_detail.py) — kept consistent rather
    # than introducing a second icon for the same "watchlist" concept.
    # Real navigation (an rx.link, not a click handler) to the new blank
    # /watchlist page below; the click still bubbles up to
    # .profile-pill-trigger's own on_click same as every other menu item,
    # so the dropdown is already closed by the time the new page loads.
    return rx.link(
        rx.hstack(
            rx.icon("star", size=16),
            rx.text("Watchlist", size="2"),
            spacing="2",
            align="center",
        ),
        href="/watchlist",
        underline="none",
        # Radix's own rt-Link color rules live in a CSS @layer that
        # outranks .profile-menu-item's plain class color (same @layer-
        # priority issue noted elsewhere this session for rt-TextFieldRoot)
        # — set inline so this row reads as plain menu text, not a
        # hyperlink, matching the Dark Mode row right below it.
        color="var(--gray-12)",
        class_name="profile-menu-item",
    )


def _color_mode_menu_item() -> rx.Component:
    # Dark/light mode now lives here instead of its own always-visible
    # header button — freeing that width is what let the nav links (below)
    # stay visible down to phone widths instead of being hidden there.
    # rx.toggle_color_mode is the same special event rx.color_mode.button
    # itself dispatches internally; the whole row is the click target, not
    # just an icon.
    return rx.hstack(
        rx.color_mode_cond(
            light=rx.icon("moon", size=16),
            dark=rx.icon("sun", size=16),
        ),
        rx.text(rx.color_mode_cond(light="Dark Mode", dark="Light Mode"), size="2"),
        on_click=rx.toggle_color_mode,
        spacing="2",
        align="center",
        class_name="profile-menu-item",
    )


def _profile_dropdown() -> rx.Component:
    return rx.box(
        _watchlist_menu_item(),
        _color_mode_menu_item(),
        class_name="profile-dropdown",
    )


def _profile_pill() -> rx.Component:
    # Hardcoded placeholder (name, plan, avatar) — no real image, since this
    # will become a customizable user profile (background image, name, plan
    # tier) once that's wired up. background uses Radix's own alpha-gray
    # tokens so it recolors automatically with the light/dark toggle instead
    # of a fixed hex value.
    #
    # Now also the dropdown trigger for _profile_dropdown above: click
    # toggles CoinState.profile_menu_open open/closed (a 2nd click closes
    # it, per explicit request), and a real click anywhere outside this
    # pill closes it too — assets/chain_pills.js's click-outside listener,
    # the same pattern the header search dropdown already uses.
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text("Fyqq", size="2", weight="bold"),
                rx.badge("Standard", color_scheme="gray", size="1"),
                spacing="1",
                align="start",
                # Hidden below the iPad-portrait breakpoint (md, 768px) — on
                # a phone-width header there isn't room for this text column
                # too, so the pill collapses to just the avatar there.
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
        ),
        rx.cond(CoinState.profile_menu_open, _profile_dropdown(), rx.fragment()),
        on_click=CoinState.toggle_profile_menu,
        cursor="pointer",
        position="relative",
        class_name="profile-pill-trigger",
    )


# (label, route) — each now its own dedicated (currently blank/placeholder)
# page, per explicit request, rather than anchor-scrolling into a section of
# the homepage the way an earlier version of this nav bar did.
_NAV_LINKS = [
    ("News", "/news"),
    ("Narrative", "/narrative"),
    ("Chains", "/chains"),
    ("Tools", "/tools"),
]


def _nav_link(label: str, href: str) -> rx.Component:
    is_active = CoinState.current_nav_path == href
    return rx.link(
        rx.text(label, size="2", weight="medium"),
        href=href,
        underline="none",
        color=rx.cond(is_active, "var(--accent-9)", rx.color_mode_cond(light="black", dark="white")),
        class_name=rx.cond(is_active, "header-nav-link header-nav-link-active", "header-nav-link"),
        flex_shrink="0",
    )


def _nav_links() -> rx.Component:
    return rx.hstack(
        *[_nav_link(label, href) for label, href in _NAV_LINKS],
        align="center",
        justify="center",
        # Tighter gap at phone/small-tablet widths, where the grid column
        # holding this row is genuinely tight on space (see _header_bar's
        # grid_template_columns) — plain "spacing" tokens are fixed, not
        # responsive, so this uses a real CSS gap instead.
        style={"gap": ["0.65em", "0.85em", "1.25em", "1.25em", "1.25em"]},
        # Visible at every screen size per explicit request (previously
        # hidden below the "lg" breakpoint) — min_width=0 lets this grid
        # column actually shrink instead of forcing the header wider, and
        # overflow_x + .hide-scrollbar (styles.css) turn any width the 4
        # links genuinely don't fit into into a horizontal swipe/scroll
        # instead of clipping or wrapping.
        min_width="0",
        overflow_x="auto",
        flex_wrap="nowrap",
        class_name="hide-scrollbar",
    )


def _header_bar() -> rx.Component:
    # A proper full-bleed nav bar (bottom border + shadow separating it from
    # the scrollable content below) instead of the header just being the
    # first row of the same padded content column — logo/heading/color-mode
    # icon/profile pill are all sized down to fit a nav bar's compact scale
    # rather than the oversized hero-like proportions this had before.
    return rx.box(
        rx.box(
            rx.link(
                rx.hstack(
                    rx.color_mode_cond(
                        light=rx.image(src="/logo_light.png", height="28px"),
                        dark=rx.image(src="/logo_dark.png", height="28px"),
                    ),
                    # White reads fine against the header's dark background
                    # in dark mode, but is invisible against its light-mode
                    # background — needs to flip to black there.
                    #
                    # Hidden below the "sm" breakpoint (480px) — just the
                    # logo mark stays. Freeing this ~90px is what actually
                    # gives the nav-links column (center of the header grid)
                    # a real, non-zero share of the remaining width on a
                    # phone; confirmed live that without this, the fixed-
                    # content logo+search+profile columns alone already
                    # consumed the entire 375px header, squeezing the nav
                    # links column down to ~2px.
                    rx.heading(
                        "Repace",
                        size="6",
                        color=rx.color_mode_cond(light="black", dark="white"),
                        display=["none", "flex", "flex", "flex", "flex"],
                    ),
                    spacing="2",
                    align="center",
                ),
                href="/",
                underline="none",
            ),
            _nav_links(),
            rx.hstack(
                global_search(),
                _profile_pill(),
                # Hidden — clicked from JS (assets/chain_pills.js) on a real
                # click outside .profile-pill-trigger, closing the dropdown
                # (same click-outside-close pattern as the header search's
                # own #global-search-close-trigger). Kept as a *sibling* of
                # _profile_pill(), not nested inside it — that box's own
                # on_click is a toggle covering its entire subtree, so a
                # trigger nested inside it would double-fire on click
                # (close, then immediately re-toggle back open).
                rx.box(id="profile-menu-close-trigger", on_click=CoinState.close_profile_menu, display="none"),
                spacing="3",
                align="center",
                justify="end",
                flex_shrink="0",
            ),
            # A 3-column grid (not hstack + justify="between") so the nav
            # links land at the header's true horizontal center regardless
            # of how wide the logo or the right-side controls are — the two
            # outer 1fr columns stay equal width, and the center column
            # (auto) hugs its own content. Below md/768px this flips to
            # `auto minmax(0, 1fr) auto`: with the outer columns still `1fr`
            # there, the logo and search+profile group's own intrinsic
            # widths already ate the whole 320–375px budget, squeezing the
            # nav-links column to zero rather than merely off-center — an
            # `auto` center column has no guaranteed minimum, so the "auto"
            # track collapsed to nothing instead of becoming the horizontal
            # -scroll strip _nav_links() itself was built to fall back to.
            # `auto` outer columns (natural content width, no stretch) plus
            # a `minmax(0, 1fr)` center (takes whatever's actually left,
            # down to 0, but is a real, positive-width flex track rather
            # than one with no minimum-size floor at all) is what actually
            # leaves it a real width to scroll within on a phone.
            display="grid",
            grid_template_columns=[
                "auto minmax(0, 1fr) auto",
                "auto minmax(0, 1fr) auto",
                "1fr auto 1fr",
                "1fr auto 1fr",
                "1fr auto 1fr",
            ],
            align_items="center",
            width="100%",
            style={"column-gap": "1em"},
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
            rx.box(news_feed(), id="news-feed-section", width="100%"),
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


def _placeholder_page(heading: str) -> rx.Component:
    # Blank/placeholder page for one of the header's nav links (News,
    # Narrative, Chains, Tools) — real content for each is future work, this
    # just gives the nav bar a real destination instead of a dead link, with
    # the same shared header/footer shell every other page uses so it
    # doesn't look like a broken navigation.
    return rx.box(
        _header_bar(),
        rx.center(
            rx.vstack(
                rx.heading(heading, size="7"),
                rx.text("Coming soon", size="3", color_scheme="gray"),
                spacing="2",
                align="center",
            ),
            min_height="60vh",
            width="100%",
        ),
        footer(),
        min_height="100vh",
        width="100%",
    )


def news_page() -> rx.Component:
    return _placeholder_page("News")


def narrative_page() -> rx.Component:
    return _placeholder_page("Narrative")


def chains_page() -> rx.Component:
    return _placeholder_page("Chains")


def tools_page() -> rx.Component:
    return _placeholder_page("Tools")


def watchlist_page() -> rx.Component:
    return _placeholder_page("Watchlist")


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
# Header nav-link destinations (_NAV_LINKS above) — blank/placeholder pages
# today. Each still loads the coin universe so the shared header's own
# search bar works even when one of these is the very first page a session
# visits (a direct/bookmarked link, not navigated to from "/").
for _route, _page_fn in [
    ("/news", news_page),
    ("/narrative", narrative_page),
    ("/chains", chains_page),
    ("/tools", tools_page),
    ("/watchlist", watchlist_page),
]:
    app.add_page(_page_fn, route=_route, title=f"Repace — {_page_fn.__name__.replace('_page', '').title()}", on_load=[CoinState.load_coins])
