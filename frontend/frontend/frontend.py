"""Crypto Intelligence Platform — Reflex app entrypoint."""

import reflex as rx

from frontend.components import coin_table, filter_bar, narrative_alerts, news_feed
from frontend.state import CoinState


def index() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.heading("📊 Crypto Intelligence Platform", size="8"),
            rx.text(
                "All coins listed on CoinMarketCap, cached locally and synced once every 24 hours.",
                color_scheme="gray",
            ),
            filter_bar(),
            rx.hstack(
                rx.box(
                    rx.vstack(news_feed(), narrative_alerts(), spacing="8", width="100%"),
                    width="300px",
                    min_width="280px",
                    flex_shrink="0",
                ),
                rx.box(coin_table(), flex="1", min_width="0", overflow="hidden", width="100%"),
                spacing="8",
                align="start",
                width="100%",
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
app.add_page(index, on_load=CoinState.load_coins)
