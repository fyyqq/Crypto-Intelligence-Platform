"""Repace — Reflex app entrypoint."""

import reflex as rx

from frontend.components import coin_table, filter_bar, footer, narrative_alerts, news_feed
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
        padding="0.35em 0.35em 0.35em 1em",
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
                    rx.heading("Repace", size="6"),
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
        padding="0.85em 2em",
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
                    width="300px",
                    min_width="280px",
                    flex_shrink="0",
                ),
                rx.box(
                    coin_table(),
                    flex="1",
                    min_width="0",
                    width="100%",
                ),
                align="stretch",
                width="100%",
                style={"gap": "25px"},
            ),
            spacing="4",
            padding="2em",
            width="100%",
        ),
        footer(),
        rx.script(src="/chain_pills.js"),
        min_height="100vh",
        width="100%",
    )


app = rx.App(stylesheets=["/styles.css"])
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