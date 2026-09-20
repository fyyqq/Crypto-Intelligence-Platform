"""Crypto Intelligence Platform — Reflex app entrypoint."""

import reflex as rx

from frontend.components import coin_table, narrative_filter
from frontend.state import CoinState


def index() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.heading("📊 Crypto Intelligence Platform", size="8"),
            rx.text(
                "All coins listed on CoinMarketCap, cached locally and synced once every 24 hours.",
                color_scheme="gray",
            ),
            rx.hstack(
                narrative_filter(),
                rx.box(coin_table(), flex="1", overflow_x="auto"),
                spacing="4",
                align="start",
                width="100%",
            ),
            spacing="4",
            padding="2em",
            width="100%",
        ),
        min_height="100vh",
        width="100%",
    )


app = rx.App()
app.add_page(index, on_load=CoinState.load_coins)
