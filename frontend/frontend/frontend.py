"""Repace — Reflex app entrypoint."""

from pathlib import Path

import reflex as rx
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from frontend.components import (
    coin_detail_page,
    coin_table,
    filter_bar,
    footer,
    global_search,
    market_overview,
    narrative_alerts,
    narrative_page_content,
    news_detail_content,
    news_feed,
    news_category_content,
    news_page_content,
    watchlist_table,
)
from frontend.components.alerts_page import alerts_content
from frontend.components.login_page import AuthState, LoginState, login_page, signup_page
from frontend.state import CoinState, NewsDetailState, NewsState


def _alerts_menu_item() -> rx.Component:
    # Only once logged in (alerts are saved per account).
    return rx.cond(
        CoinState.is_logged_in,
        rx.link(
            rx.hstack(
                rx.icon("bell", size=16),
                rx.text("Alerts", size="2"),
                spacing="2",
                align="center",
                class_name="profile-menu-item",
            ),
            href="/alerts",
            underline="none",
            display="block",
            width="100%",
            color="var(--gray-12)",
        ),
    )


def _watchlist_menu_item() -> rx.Component:
    # Same "star" icon already used (currently unwired) next to a coin's
    # name on its own detail page (coin_detail.py) — kept consistent rather
    # than introducing a second icon for the same "watchlist" concept.
    # Real navigation (an rx.link, not a click handler) to the new blank
    # /watchlist page below; the click still bubbles up to
    # .profile-pill-trigger's own on_click same as every other menu item,
    # so the dropdown is already closed by the time the new page loads.
    # .profile-menu-item goes on the inner hstack (a real block-level flex
    # <div>), not on the rx.link itself — an <a> is inline by default, so
    # the class's padding/hover-highlight only wrapped tightly around the
    # text instead of spanning the dropdown's full width the way the Dark
    # Mode row below (a plain rx.hstack, no wrapping link) already does.
    # The link just becomes a plain full-width block wrapper around it.
    return rx.link(
        rx.hstack(
            rx.icon("star", size=16),
            rx.text("Watchlist", size="2"),
            spacing="2",
            align="center",
            class_name="profile-menu-item",
        ),
        href="/watchlist",
        underline="none",
        display="block",
        width="100%",
        # Radix's own rt-Link color rules live in a CSS @layer that
        # outranks .profile-menu-item's plain class color (same @layer-
        # priority issue noted elsewhere this session for rt-TextFieldRoot)
        # — set inline so this row reads as plain menu text, not a
        # hyperlink, matching the Dark Mode row right below it.
        color="var(--gray-12)",
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


def _nav_menu_items() -> rx.Component:
    """The header's nav links, shown inside the profile dropdown below lg
    (where the centre of the header is taken by the search box instead)."""
    return rx.box(
        *[
            rx.link(
                rx.hstack(rx.text(label, size="2"), align="center", class_name="profile-menu-item"),
                href=href,
                underline="none",
                display="block",
                width="100%",
                color="var(--gray-12)",
            )
            for label, href in _NAV_LINKS
        ],
        rx.divider(margin_y="0.25em"),
        display=["block", "block", "block", "block", "none"],
    )


def _auth_menu_items() -> rx.Component:
    """Log in / Sign up rows, first in the dropdown while logged out (the avatar
    opens the dropdown below lg instead of linking straight to /login)."""
    return rx.cond(
        CoinState.is_logged_in,
        rx.fragment(),
        rx.box(
            *[
                rx.link(
                    rx.hstack(rx.text(label, size="2"), align="center", class_name="profile-menu-item"),
                    href=href,
                    underline="none",
                    display="block",
                    width="100%",
                    color="var(--gray-12)",
                )
                for label, href in [("Log in", "/login"), ("Sign up", "/signup")]
            ],
            rx.divider(margin_y="0.25em"),
        ),
    )


def _profile_dropdown() -> rx.Component:
    return rx.box(
        _auth_menu_items(),
        _nav_menu_items(),
        _watchlist_menu_item(),
        _alerts_menu_item(),
        _color_mode_menu_item(),
        rx.cond(
            CoinState.is_logged_in,
            rx.hstack(
                rx.icon("log-out", size=16),
                rx.text("Log out", size="2"),
                align="center",
                class_name="profile-menu-item",
                on_click=CoinState.logout,
            ),
        ),
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
                rx.text(CoinState.user_name, size="2", weight="bold", max_width="140px", overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
                spacing="1",
                align="start",
                padding_left="0.75em",
                # Hidden below the iPad-portrait breakpoint (md, 768px) — on
                # a phone-width header there isn't room for this text column
                # too, so the pill collapses to just the avatar there.
                display=rx.cond(
                    CoinState.is_logged_in,
                    rx.breakpoints(initial="none", sm="none", md="flex", lg="flex", xl="flex"),
                    "none",
                ),
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
            # Logged in: 5px all round, per explicit request (the old breakpoint-based padding never applied).
            padding=rx.cond(CoinState.is_logged_in, "5px", "0.35em"),
            border="1px solid var(--gray-a6)",
            border_radius="9999px",
            background="var(--gray-a2)",
        ),
        rx.cond(CoinState.profile_menu_open, _profile_dropdown(), rx.fragment()),
        # Logged out: at lg+ the avatar links to /login; below lg it opens the dropdown (Log in / Sign up first).
        on_click=CoinState.profile_pill_click,
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


# News dropdown entries (label, /news/<slug>) — same slugs as the /news sections.
_NEWS_CATEGORIES = [
    ("Cryptocurrency", "cryptocurrency"),
    ("Artificial Intelligence", "artificial-intelligence"),
    ("Markets & Finance", "markets-finance"),
    ("Technology", "technology"),
    ("Memecoins", "memecoins"),
]


def _news_nav_item(label: str, href: str) -> rx.Component:
    """The "News" nav link with a hover dropdown listing the news categories."""
    return rx.box(
        rx.hstack(_nav_link(label, href), rx.icon("chevron-down", size=14, color="var(--gray-10)"), spacing="1", align="center"),
        rx.box(
            rx.box(
                *[
                    rx.link(name, href=f"/news/{slug}", underline="none", class_name="nav-dropdown-item")
                    for name, slug in _NEWS_CATEGORIES
                ],
                class_name="nav-dropdown-inner",
            ),
            class_name="nav-dropdown",
        ),
        class_name="nav-menu",
        flex_shrink="0",
    )


def _nav_link(label: str, href: str) -> rx.Component:
    # Active on the page itself and on any sub-page (e.g. /news/<category>
    # and /news/<category>/<article> keep "News" highlighted).
    is_active = (CoinState.current_nav_path == href) | CoinState.current_nav_path.startswith(href + "/")
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
        *[_news_nav_item(label, href) if href == "/news" else _nav_link(label, href) for label, href in _NAV_LINKS],
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
        # Visible at lg+ so the News dropdown isn't clipped (no swipe strip is needed there).
        overflow_x=["auto", "auto", "auto", "auto", "visible"],
        flex_wrap="nowrap",
        # Below lg (tablet/mobile) the links live in the profile dropdown
        # instead, and the search box takes the centre of the header.
        display=["none", "none", "none", "none", "flex"],
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
                # Below lg this wrapper disappears from layout so the search
                # box and profile pill become direct grid items: search in
                # the centre column, profile on the right.
                display=["contents", "contents", "contents", "contents", "flex"],
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
                "auto minmax(0, 1fr) auto",
                "auto minmax(0, 1fr) auto",
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


def _floating_logo() -> rx.Component:
    # Decorative brand mark, fixed bottom-right on every page — per explicit
    # request. `floating_logo.png` (frontend/assets) is a cleaned-up version
    # of the coin artwork the user supplied: the source PNG had no real
    # alpha channel at all (confirmed via PIL — mode "RGB"), just a
    # checkerboard pattern baked into the pixels themselves to *represent*
    # transparency, which showed through as a faint halo if naively faded
    # out. Re-masked to a real circular alpha cutout instead (see this
    # file's own dated fix entry for the exact radius/edge-color approach),
    # so it floats cleanly against the page rather than carrying a visible
    # square or checkered edge.
    #
    # Reflex's own "Built with Reflex" sticky badge (fixed, bottom:16px/
    # right:16px, 38px tall, z-index 9998 — confirmed live) is now hidden
    # entirely (rxconfig.py's show_built_with_reflex=False), so this badge
    # sits directly in that same corner spot instead of stacked above it.
    return rx.image(
        src="/floating_logo.png",
        alt="Repace",
        width="56px",
        height="56px",
        position="fixed",
        bottom="16px",
        right="16px",
        z_index="9997",
        cursor="pointer",
        on_click=CoinState.toggle_chat_widget,
        style={"filter": "drop-shadow(0 4px 10px rgba(0, 0, 0, 0.35))"},
    )


def _alert_popup_card(alert: rx.Var[dict]) -> rx.Component:
    return rx.hstack(
        rx.image(src=alert["icon_url"], width="34px", height="34px", border_radius="50%", flex_shrink="0"),
        rx.vstack(
            rx.hstack(
                rx.icon("bell-ring", size=14, color="var(--amber-9)"),
                rx.text("Price alert", size="1", weight="bold", color="var(--amber-9)"),
                spacing="1",
                align="center",
            ),
            rx.text(
                rx.text.strong(alert["name"]),
                rx.cond(alert["direction"] == "above", " rose above ", " fell below "),
                rx.text.strong(alert["target_display"]),
                size="2",
            ),
            rx.text("Now ", alert["price_display"], size="1", color_scheme="gray"),
            spacing="0",
            align="start",
            min_width="0",
            flex="1",
        ),
        rx.icon(
            "x",
            size=18,
            color="var(--gray-11)",
            cursor="pointer",
            flex_shrink="0",
            on_click=CoinState.dismiss_alert_popup(alert["id"]),
        ),
        spacing="3",
        align="start",
        width="100%",
        padding="0.85em 1em",
        border_radius="14px",
        background="var(--gray-2)",
        border="1px solid var(--gray-a6)",
        border_left=rx.cond(alert["direction"] == "above", "4px solid var(--green-9)", "4px solid var(--red-9)"),
        box_shadow="0 12px 32px rgba(0, 0, 0, 0.35)",
        pointer_events="auto",
    )


def _alert_popups() -> rx.Component:
    # Triggered price alerts, stacked, centred just under the header. Always
    # rendered so the CSS transition can run: parked at top:-1000px, it slides
    # down to 104px when an alert triggers and back up after ~1 minute
    # (CoinState.start_alert_watch flips alert_popup_visible).
    return rx.box(
        rx.vstack(
            rx.foreach(CoinState.alert_popups, _alert_popup_card),
            spacing="2",
            width="100%",
        ),
        position="fixed",
        top=rx.cond(CoinState.alert_popup_visible, "104px", "-1000px"),
        left="50%",
        transform="translateX(-50%)",
        width="min(380px, calc(100vw - 32px))",
        z_index="10000",
        pointer_events="none",
        transition="top 0.7s cubic-bezier(0.22, 1, 0.36, 1)",
    )


def _watchlist_button() -> rx.Component:
    # Circle with a star, stacked directly above the floating logo (logo is
    # 56px at bottom/right 16px; this is 44px, centred over it 12px higher).
    # Opens _watchlist_widget; the circle turns white while it is open, the star stays amber.
    return rx.box(
        rx.icon("star", size=20, color="var(--amber-9)", fill="var(--amber-9)"),
        width="44px",
        height="44px",
        border_radius="9999px",
        position="fixed",
        bottom="84px",
        right="22px",
        z_index="9997",
        cursor="pointer",
        display="flex",
        align_items="center",
        justify_content="center",
        # Turns white while the popup is open; the stars stay yellow.
        background=rx.cond(CoinState.watchlist_popup_open, "white", "var(--gray-2)"),
        border="1px solid var(--gray-a6)",
        box_shadow="0 4px 12px rgba(0, 0, 0, 0.3)",
        on_click=CoinState.toggle_watchlist_popup,
    )


def _watchlist_popup_row(row: rx.Var[dict]) -> rx.Component:
    # Same layout as the header search results (global_search.py): icon,
    # name + ticker, price over 24h change. The price here is live — see
    # CoinState.watchlist_live_loop. A real <a href> to the coin page.
    return rx.link(
        rx.hstack(
            rx.image(src=row["icon_url"], width="22px", height="22px", border_radius="50%", flex_shrink="0"),
            rx.hstack(
                rx.text(row["name"], size="2", weight="bold", class_name="global-search-result-name"),
                rx.text(row["symbol"], size="2", color_scheme="gray", flex_shrink="0"),
                spacing="1",
                align="center",
                min_width="0",
                flex="1",
            ),
            rx.vstack(
                rx.text(row["price_display"], size="2", weight="medium"),
                rx.text(row["change_24h_display"], size="1", color=row["change_24h_color"]),
                spacing="0",
                align="end",
                flex_shrink="0",
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        href="/coin/" + row["symbol"].to(str).lower(),
        underline="none",
        color="inherit",
        display="block",
        width="100%",
        class_name="global-search-result-row",
    )


def _watchlist_widget() -> rx.Component:
    return rx.cond(
        CoinState.watchlist_popup_open,
        rx.box(
            rx.hstack(
                rx.hstack(
                    rx.icon("star", size=16, color="var(--amber-9)", fill="var(--amber-9)"),
                    rx.text("Watchlist", size="3", weight="bold"),
                    rx.badge(CoinState.watchlist_count, variant="soft", radius="full"),
                    spacing="2",
                    align="center",
                ),
                rx.icon("x", size=18, color="var(--gray-12)", cursor="pointer", on_click=CoinState.close_watchlist_popup),
                align="center",
                justify="between",
                width="100%",
                padding="0.85em 1em",
                background=rx.color_mode_cond(light="white", dark="var(--gray-3)"),
                border_bottom="1px solid var(--gray-a5)",
            ),
            rx.box(
                rx.cond(
                    CoinState.has_watchlist_coins,
                    rx.foreach(CoinState.watchlist_popup_rows, _watchlist_popup_row),
                    rx.center(
                        rx.text(
                            "Your watchlist is empty — click the star on any coin to add it.",
                            size="2",
                            color_scheme="gray",
                            text_align="center",
                        ),
                        padding="2em 1em",
                    ),
                ),
                overflow_y="auto",
                flex="1",
                padding_y="0.25em",
            ),
            rx.link(
                rx.text("View full watchlist", size="2", weight="medium"),
                href="/watchlist",
                underline="none",
                text_align="center",
                padding="0.7em",
                border_top="1px solid var(--gray-a5)",
                background="var(--gray-2)",
                display="block",
            ),
            position="fixed",
            bottom="144px",
            right="16px",
            width=["calc(100vw - 32px)", "320px", "320px", "320px", "320px"],
            max_width="320px",
            max_height=["calc(100vh - 160px)", "420px", "420px", "420px", "420px"],
            display="flex",
            flex_direction="column",
            border_radius="16px",
            border="1px solid var(--gray-a5)",
            background="var(--gray-2)",
            box_shadow="0 12px 32px rgba(0, 0, 0, 0.3)",
            overflow="hidden",
            z_index="9998",
        ),
        rx.fragment(),
    )


def _chat_widget_message(text: str, *, from_user: bool = False) -> rx.Component:
    # Bot avatar/bubble on the left, user bubble/avatar on the right — same
    # two-side layout as the reference screenshot, just recolored (see
    # _chat_widget's own note on why green was dropped for a neutral
    # gray/white scheme instead).
    bubble = rx.box(
        rx.text(text, size="2", style={"white-space": "pre-wrap"}),
        padding="0.55em 0.8em",
        border_radius="14px",
        background=rx.color_mode_cond(light="var(--gray-3)", dark="var(--gray-a4)") if from_user else "var(--gray-a3)",
        max_width="200px",
    )
    avatar = rx.box(
        rx.icon("bot" if not from_user else "user", size=14, color="var(--gray-12)"),
        width="26px",
        height="26px",
        border_radius="9999px",
        background="var(--gray-a4)",
        display="flex",
        align_items="center",
        justify_content="center",
        flex_shrink="0",
    )
    return rx.hstack(
        *([bubble, avatar] if from_user else [avatar, bubble]),
        spacing="2",
        align="end",
        justify="end" if from_user else "start",
        width="100%",
    )


def _chat_widget_typing_indicator() -> rx.Component:
    # Static three-dot "typing" bubble, same spot as the reference image's
    # own trailing bot bubble — this is a UI shell only (no live chatbot
    # backend wired up yet), so it never actually resolves into a message.
    return rx.hstack(
        rx.box(
            rx.icon("bot", size=14, color="var(--gray-12)"),
            width="26px",
            height="26px",
            border_radius="9999px",
            background="var(--gray-a4)",
            display="flex",
            align_items="center",
            justify_content="center",
            flex_shrink="0",
        ),
        rx.hstack(
            rx.box(width="6px", height="6px", border_radius="9999px", background="var(--gray-9)"),
            rx.box(width="6px", height="6px", border_radius="9999px", background="var(--gray-9)"),
            rx.box(width="6px", height="6px", border_radius="9999px", background="var(--gray-9)"),
            spacing="1",
            align="center",
            padding="0.7em 0.8em",
            border_radius="14px",
            background="var(--gray-a3)",
        ),
        spacing="2",
        align="end",
        justify="start",
        width="100%",
    )


def _chat_widget() -> rx.Component:
    # Popup chatbot window, opened/closed by clicking the floating logo
    # (CoinState.toggle_chat_widget) or the "x" in this popup's own header
    # (CoinState.close_chat_widget) — same design as the reference
    # screenshot, but with every green surface swapped for a neutral
    # gray/white one that follows the app's own light/dark mode instead of
    # a fixed brand color. In light mode the header reads as plain white
    # (per explicit request); in dark mode it matches the rest of the app's
    # dark surfaces. UI shell only — static demo messages, no real chatbot
    # backend wired up yet (same "shell first, real content later" pattern
    # as the /news, /narrative, /chains, /tools, /watchlist placeholder
    # pages).
    return rx.cond(
        CoinState.chat_widget_open,
        rx.box(
            # Header
            rx.hstack(
                rx.hstack(
                    rx.box(
                        rx.icon("bot", size=16, color="var(--gray-12)"),
                        width="30px",
                        height="30px",
                        border_radius="9999px",
                        background="var(--gray-a4)",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        flex_shrink="0",
                    ),
                    rx.text("Repace Assistant", size="3", weight="bold"),
                    spacing="2",
                    align="center",
                ),
                rx.icon(
                    "x",
                    size=18,
                    color="var(--gray-12)",
                    cursor="pointer",
                    on_click=CoinState.close_chat_widget,
                ),
                align="center",
                justify="between",
                width="100%",
                padding="0.85em 1em",
                background=rx.color_mode_cond(light="white", dark="var(--gray-3)"),
                border_bottom="1px solid var(--gray-a5)",
            ),
            # Messages
            rx.vstack(
                _chat_widget_message("Hi there! I'm the Repace Assistant. How can I help you today?"),
                _chat_widget_message("How does this work?", from_user=True),
                _chat_widget_message("I can help you look up coins, narratives, and market data once I'm connected."),
                _chat_widget_typing_indicator(),
                spacing="3",
                width="100%",
                padding="1em",
                overflow_y="auto",
                flex="1",
            ),
            # Input row
            rx.hstack(
                rx.el.input(
                    placeholder="Type a message...",
                    disabled=True,
                    width="100%",
                    padding="0.6em 0.9em",
                    border_radius="9999px",
                    border="1px solid var(--gray-a5)",
                    background="var(--gray-a2)",
                    color="var(--gray-12)",
                    style={"outline": "none"},
                ),
                rx.box(
                    rx.icon("send", size=16, color="var(--gray-12)"),
                    width="34px",
                    height="34px",
                    border_radius="9999px",
                    background="var(--gray-a4)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    flex_shrink="0",
                ),
                spacing="2",
                align="center",
                width="100%",
                padding="0.85em 1em",
                border_top="1px solid var(--gray-a5)",
                background="var(--gray-2)",
            ),
            position="fixed",
            bottom="144px",  # above the floating logo and the watchlist star
            right="16px",
            width=["calc(100vw - 32px)", "320px", "320px", "320px", "320px"],
            max_width="320px",
            height="420px",
            max_height="calc(100vh - 160px)",
            display="flex",
            flex_direction="column",
            border_radius="16px",
            border="1px solid var(--gray-a5)",
            background="var(--gray-2)",
            box_shadow="0 12px 32px rgba(0, 0, 0, 0.3)",
            overflow="hidden",
            z_index="9998",
        ),
        rx.fragment(),
    )


def index() -> rx.Component:
    return rx.box(
        _header_bar(),
        rx.vstack(
            market_overview(),
            rx.box(
                news_feed("Cryptocurrency", NewsState.home_crypto_news, "/news/cryptocurrency"),
                id="news-feed-section",
                width="100%",
            ),
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
        _floating_logo(),
        _chat_widget(),
        _watchlist_button(),
        _watchlist_widget(),
        _alert_popups(),
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
        _floating_logo(),
        _chat_widget(),
        _watchlist_button(),
        _watchlist_widget(),
        _alert_popups(),
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
        _floating_logo(),
        _chat_widget(),
        _watchlist_button(),
        _watchlist_widget(),
        _alert_popups(),
        rx.script(src="/chain_pills.js"),
        min_height="100vh",
        width="100%",
    )


def news_page() -> rx.Component:
    # Real content, per explicit request — supersedes the blank
    # _placeholder_page shell every other nav-link page still uses.
    # news_page_content() reads real articles from the news_articles table
    # (app/services/news_pipeline.py) via NewsState, grouped by outlet.
    return rx.box(
        _header_bar(),
        news_page_content(),
        footer(),
        _floating_logo(),
        _chat_widget(),
        _watchlist_button(),
        _watchlist_widget(),
        _alert_popups(),
        # Needed for the header search/profile dropdowns' click-outside
        # handlers (this page has the same header as every other page) and
        # this page's own #<source> anchor-scroll fix — see chain_pills.js's
        # own comment on the latter for why it's needed here specifically.
        rx.script(src="/chain_pills.js"),
        min_height="100vh",
        width="100%",
    )


def news_category_page() -> rx.Component:
    # /news/[news_category] — every category's newest 100 articles ("View All").
    return rx.box(
        _header_bar(),
        news_category_content(),
        footer(),
        _floating_logo(),
        _chat_widget(),
        _watchlist_button(),
        _watchlist_widget(),
        _alert_popups(),
        rx.script(src="/chain_pills.js"),
        min_height="100vh",
        width="100%",
    )


def news_detail_page() -> rx.Component:
    return rx.box(
        _header_bar(),
        news_detail_content(),
        footer(),
        _floating_logo(),
        _chat_widget(),
        _watchlist_button(),
        _watchlist_widget(),
        _alert_popups(),
        rx.script(src="/chain_pills.js"),
        min_height="100vh",
        width="100%",
    )


def narrative_page() -> rx.Component:
    # /narrative — every AI-targeted Cryptocurrency article (Narrative Radar), 100 per page.
    return rx.box(
        _header_bar(),
        narrative_page_content(),
        footer(),
        _floating_logo(),
        _chat_widget(),
        _watchlist_button(),
        _watchlist_widget(),
        _alert_popups(),
        rx.script(src="/chain_pills.js"),
        min_height="100vh",
        width="100%",
    )


def chains_page() -> rx.Component:
    return _placeholder_page("Chains")


def tools_page() -> rx.Component:
    return _placeholder_page("Tools")


def alerts_page() -> rx.Component:
    return rx.box(
        _header_bar(),
        rx.box(
            alerts_content(),
            padding=["1em", "1em", "1.5em", "2em", "2em"],
            width="100%",
            min_height="60vh",
        ),
        footer(),
        _floating_logo(),
        _chat_widget(),
        _watchlist_button(),
        _watchlist_widget(),
        _alert_popups(),
        rx.script(src="/chain_pills.js"),
        min_height="100vh",
        width="100%",
    )


def watchlist_page() -> rx.Component:
    # Real content, per explicit request — supersedes the blank
    # _placeholder_page shell every other nav-link page still uses.
    # watchlist_table() is its own component (not coin_table()) since it's
    # scoped to CoinState.watchlist_coins/watchlist_ids rather than the full
    # homepage browsing pipeline (categories/chains/search/pagination/sort),
    # which don't apply to a small, already-curated personal list.
    return rx.box(
        _header_bar(),
        rx.box(
            watchlist_table(),
            padding=["1em", "1em", "1.5em", "2em", "2em"],
            width="100%",
        ),
        footer(),
        _floating_logo(),
        _chat_widget(),
        _watchlist_button(),
        _watchlist_widget(),
        _alert_popups(),
        rx.script(src="/chain_pills.js"),
        min_height="100vh",
        width="100%",
    )


# app/services/telegram_pipeline.py downloads new post images into
# frontend/assets/telegram_media/ continuously (every scheduled pipeline
# run, not just once) — but Reflex's own asset serving copies frontend/
# assets/ into a build-time snapshot (frontend/.web/public/), so a file
# added there *after* the app was last compiled 404s until the next
# rebuild/restart. Confirmed live: a file dropped in post-startup was
# unreachable even though it existed on disk.
#
# Fixed by mounting a real, live Starlette StaticFiles route directly onto
# Reflex's own backend ASGI app via api_transformer (Reflex's documented
# extension point for exactly this — see api-routes/overview in the
# reflex-docs skill) — StaticFiles serves straight from disk on every
# request, so a newly-downloaded image is reachable immediately, no
# restart needed. Mirrors the same StaticFiles-mount pattern Reflex's own
# app.py already uses internally for rx.upload's uploaded-files route.
_telegram_media_dir = Path(__file__).resolve().parent.parent / "assets" / "telegram_media"
_telegram_media_dir.mkdir(parents=True, exist_ok=True)
_api_transformer = Starlette(
    routes=[Mount("/telegram_media", app=StaticFiles(directory=str(_telegram_media_dir)), name="telegram_media")]
)

app = rx.App(stylesheets=["/styles.css"], api_transformer=_api_transformer)
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
        CoinState.restore_session, CoinState.load_coins, CoinState.start_alert_watch,
        CoinState.detail_sync_loop,
        CoinState.refresh_coin_description,
        CoinState.refresh_business_summary,
        CoinState.refresh_market_pairs,
        CoinState.refresh_tradingview_dex_symbol,
        CoinState.refresh_defillama_unlocks_slug,
    ],
)
app.add_page(
    news_category_page,
    route="/news/[news_category]",
    title=NewsState.view_all_title,
    on_load=[CoinState.restore_session, CoinState.load_coins, CoinState.start_alert_watch, NewsState.load_news, NewsState.reset_view_all_page, NewsState.watch_new_articles],
)
app.add_page(
    alerts_page,
    route="/alerts",
    title="Repace — Alerts",
    on_load=[CoinState.restore_session, CoinState.require_login, CoinState.load_coins, CoinState.start_alert_watch, CoinState.load_alert_history],
)
app.add_page(login_page, route="/login", title="Repace — Log in", on_load=[CoinState.restore_session, AuthState.clear_auth_error, LoginState.reset_visibility])
app.add_page(signup_page, route="/signup", title="Repace — Sign up", on_load=[CoinState.restore_session, AuthState.clear_auth_error, LoginState.reset_visibility])
app.add_page(
    news_detail_page,
    route="/news/[news_category]/[article_slug]",
    title=NewsDetailState.page_title,
    on_load=[CoinState.restore_session, CoinState.load_coins, CoinState.start_alert_watch, NewsDetailState.load_article],
)
app.add_page(
    index,
    title="Repace",
    description="Tracking crypto markets in real time, mapping every asset into dynamic narratives, with AI-powered news correlation on the way.",
    image="/favicon_logo.png",
    # `image=` above only sets the og:image social-preview meta tag — the
    # actual browser-tab favicon needs its own <link rel="icon"> tag.
    meta=[rx.el.link(rel="icon", href="/favicon_logo.png", type="image/png")],
    on_load=[CoinState.restore_session, CoinState.load_coins, CoinState.start_alert_watch, CoinState.live_sync_loop, NewsState.load_news, NewsState.watch_new_articles],
)
# /news has real content (news_page_content(), NewsState) — registered on
# its own so it can add NewsState.load_news to the shared on_load list below
# rather than going through the still-blank-placeholder loop.
app.add_page(
    news_page,
    route="/news",
    title="Repace — News",
    on_load=[CoinState.restore_session, CoinState.load_coins, CoinState.start_alert_watch, NewsState.load_news, NewsState.watch_new_articles],
)
# Remaining header nav-link destinations (_NAV_LINKS above) — blank/
# placeholder pages today. Each still loads the coin universe so the shared
# header's own search bar works even when one of these is the very first
# page a session visits (a direct/bookmarked link, not navigated to from "/").
app.add_page(
    narrative_page,
    route="/narrative",
    title="Repace — Narrative Radar",
    on_load=[CoinState.restore_session, CoinState.load_coins, CoinState.start_alert_watch, NewsState.load_news, NewsState.reset_narrative_page, NewsState.watch_new_articles],
)
for _route, _page_fn in [
    ("/chains", chains_page),
    ("/tools", tools_page),
    ("/watchlist", watchlist_page),
]:
    app.add_page(_page_fn, route=_route, title=f"Repace — {_page_fn.__name__.replace('_page', '').title()}", on_load=[CoinState.restore_session, CoinState.load_coins, CoinState.start_alert_watch])
