"""Repace — Reflex app entrypoint."""

import reflex as rx

from frontend.components import coin_table, filter_bar, narrative_alerts, news_feed
from frontend.state import CoinState


def _profile_pill() -> rx.Component:
    # Hardcoded placeholder (name, plan, avatar) — no real image, since this
    # will become a customizable user profile (background image, name, plan
    # tier) once that's wired up. background uses Radix's own alpha-gray
    # tokens so it recolors automatically with the light/dark toggle instead
    # of a fixed hex value.
    return rx.hstack(
        rx.vstack(
            rx.text("Fyqq", size="4", weight="bold"),
            rx.badge("Standard", color_scheme="gray", size="1"),
            spacing="1",
            align="start",
        ),
        rx.box(
            rx.icon("user", size=20, color="var(--gray-9)"),
            width="48px",
            height="48px",
            border_radius="9999px",
            background="var(--gray-a5)",
            display="flex",
            align_items="center",
            justify_content="center",
            flex_shrink="0",
        ),
        spacing="4",
        align="center",
        padding="0.5em 0.5em 0.5em 1.5em",
        border="1px solid var(--gray-a6)",
        border_radius="9999px",
        background="var(--gray-a2)",
    )


def index() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.hstack(
                    rx.link(
                        rx.color_mode_cond(
                            light=rx.image(src="/logo_light.png", height="2.2em"),
                            dark=rx.image(src="/logo_dark.png", height="2.2em"),
                        ),
                        href="/",
                    ),
                    rx.heading("Repace", size="8"),
                    spacing="3",
                    align="center",
                ),
                rx.hstack(
                    rx.color_mode.button(),
                    _profile_pill(),
                    spacing="3",
                    align="center",
                ),
                justify="between",
                align="center",
                width="100%",
                padding_right="25px",
            ),
            rx.text(
                "Tracking crypto markets in real time, mapping every asset into dynamic narratives, with AI-powered news correlation on the way.",
                color_scheme="gray",
            ),
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
