"""Left column: dummy global news feed (static placeholder content, no backend)."""

import reflex as rx

_SOURCE_COLORS = {
    "Bloomberg": "blue",
    "Cointelegraph": "green",
    "Reuters": "orange",
    "CoinDesk": "purple",
}

NEWS_ITEMS = [
    {
        "source": "Bloomberg",
        "time": "10m ago",
        "headline": "BlackRock consolidates aggregate headlines in Tier-1 Fed coverage",
        "tags": ["Fed", "Regulation"],
    },
    {
        "source": "Cointelegraph",
        "time": "1h ago",
        "headline": "BlackRock adds RWA tokenization support to broader ecosystem coverage",
        "tags": ["RWA", "BlackRock"],
    },
    {
        "source": "Bloomberg",
        "time": "1h ago",
        "headline": "BlackRock adds RWA narrative to institutional treasury reporting",
        "tags": ["Fed", "Regulation"],
    },
    {
        "source": "Cointelegraph",
        "time": "2h ago",
        "headline": "BlackRock adds target perimeter to counter route liquidity risk",
        "tags": ["Risk", "Liquidity"],
    },
    {
        "source": "Reuters",
        "time": "3h ago",
        "headline": "Solana ecosystem TVL climbs as Layer 1 narrative gains momentum",
        "tags": ["Layer 1", "Solana"],
    },
    {
        "source": "CoinDesk",
        "time": "4h ago",
        "headline": "Ondo Finance expands tokenized treasury products across chains",
        "tags": ["RWA", "Ondo"],
    },
]


def _news_card(item: dict) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.badge(item["source"], color_scheme=_SOURCE_COLORS.get(item["source"], "gray")),
            rx.spacer(),
            rx.text(item["time"], size="1", color_scheme="gray"),
            width="100%",
            align="center",
        ),
        rx.text(item["headline"], weight="medium", size="2", margin_top="0.5em"),
        rx.hstack(
            *[rx.badge(tag, variant="outline", size="1", color_scheme="gray") for tag in item["tags"]],
            spacing="1",
            margin_top="0.5em",
            wrap="wrap",
        ),
        padding="0.85em",
        border="1px solid var(--gray-a5)",
        border_radius="8px",
        width="100%",
    )


def news_feed() -> rx.Component:
    return rx.vstack(
        rx.text("GLOBAL INTELLIGENCE FEED", size="1", color_scheme="gray", weight="bold"),
        rx.heading("All News", size="5"),
        rx.box(
            rx.vstack(
                *[_news_card(item) for item in NEWS_ITEMS],
                spacing="2",
                width="100%",
            ),
            height="calc(100vh - 300px)",
            overflow="auto",
            width="100%",
        ),
        spacing="3",
        width="100%",
        align_items="stretch",
    )
