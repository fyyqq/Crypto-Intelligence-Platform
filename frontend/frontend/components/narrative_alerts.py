"""Right column: dummy targeted narrative + coin alerts (static placeholder, no backend)."""

import reflex as rx

ALERTS = [
    {
        "narrative": "REAL-WORLD ASSETS (RWA)",
        "hot": False,
        "coin_symbol": "ONDO",
        "time": "10m ago",
        "headline": "Ondo Finance (ONDO) | BlackRock adds RWA tokenization support",
        "body": "BlackRock's latest filing references Ondo's tokenized treasury rails as a settlement path for RWA products.",
    },
    {
        "narrative": "LAYER 1",
        "hot": True,
        "coin_symbol": "SOL",
        "time": "35m ago",
        "headline": "Solana network TVL hits multi-year high",
        "body": "Layer 1 narrative strength continues as Solana TVL breaks out, with institutional flows reportedly accelerating.",
    },
    {
        "narrative": "REAL-WORLD ASSETS (RWA)",
        "hot": True,
        "coin_symbol": "ONDO",
        "time": "1h ago",
        "headline": "Ondo Finance expands tokenized treasury products across chains",
        "body": "New cross-chain deployment widens RWA narrative exposure beyond the initial Ethereum mainnet launch.",
    },
    {
        "narrative": "AI AGENTS",
        "hot": False,
        "coin_symbol": "RENDER",
        "time": "2h ago",
        "headline": "Render Network narrative gains as AI compute demand rises",
        "body": "Decentralized GPU compute narrative strengthens alongside broader AI agent infrastructure spend.",
    },
]


def _alert_card(item: dict) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.badge(f"NARRATIVE: {item['narrative']}", color_scheme="orange", size="1"),
            rx.spacer(),
            rx.text("🔥" if item["hot"] else item["time"], size="1", color_scheme="gray"),
            width="100%",
            align="center",
        ),
        rx.hstack(
            rx.badge(item["coin_symbol"], color_scheme="indigo", margin_top="0.6em"),
            width="100%",
        ),
        rx.text(item["headline"], weight="bold", size="2", margin_top="0.4em"),
        rx.text(item["body"], size="1", color_scheme="gray", margin_top="0.3em"),
        padding="0.85em",
        border_left="3px solid var(--orange-9)",
        border_radius="8px",
        background="var(--gray-a2)",
        width="100%",
    )


def narrative_alerts() -> rx.Component:
    return rx.vstack(
        rx.text("TARGETED NARRATIVE ALERTS", size="1", color_scheme="gray", weight="bold"),
        rx.heading("Targeted Narrative + Coin", size="5"),
        rx.box(
            rx.vstack(
                *[_alert_card(item) for item in ALERTS],
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
