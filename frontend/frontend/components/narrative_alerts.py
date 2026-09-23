"""Right column: dummy targeted narrative + coin alerts (static placeholder, no backend)."""

import reflex as rx

_SOURCE_COLORS = {
    "Bloomberg": "blue",
    "Cointelegraph": "green",
    "Reuters": "orange",
    "CoinDesk": "purple",
}

ALERTS = [
    {
        "narrative": "REAL-WORLD ASSETS (RWA)",
        "source": "Bloomberg",
        "hot": False,
        "coin_symbol": "ONDO",
        "time": "10m ago",
        "headline": "Ondo Finance (ONDO) | BlackRock adds RWA tokenization support",
        "body": "BlackRock's latest filing references Ondo's tokenized treasury rails as a settlement path for RWA products.",
    },
    {
        "narrative": "LAYER 1",
        "source": "Cointelegraph",
        "hot": True,
        "coin_symbol": "SOL",
        "time": "35m ago",
        "headline": "Solana network TVL hits multi-year high",
        "body": "Layer 1 narrative strength continues as Solana TVL breaks out, with institutional flows reportedly accelerating.",
    },
    {
        "narrative": "REAL-WORLD ASSETS (RWA)",
        "source": "Reuters",
        "hot": True,
        "coin_symbol": "ONDO",
        "time": "1h ago",
        "headline": "Ondo Finance expands tokenized treasury products across chains",
        "body": "New cross-chain deployment widens RWA narrative exposure beyond the initial Ethereum mainnet launch.",
    },
    {
        "narrative": "AI AGENTS",
        "source": "CoinDesk",
        "hot": False,
        "coin_symbol": "RENDER",
        "time": "2h ago",
        "headline": "Render Network narrative gains as AI compute demand rises",
        "body": "Decentralized GPU compute narrative strengthens alongside broader AI agent infrastructure spend.",
    },
    {
        "narrative": "DEFI",
        "source": "Bloomberg",
        "hot": False,
        "coin_symbol": "AAVE",
        "time": "45m ago",
        "headline": "Aave v4 proposal targets unified cross-chain liquidity",
        "body": "Governance forum activity spikes as the community debates a unified liquidity layer spanning multiple chains.",
    },
    {
        "narrative": "MEMES",
        "source": "Cointelegraph",
        "hot": True,
        "coin_symbol": "PEPE",
        "time": "1h ago",
        "headline": "PEPE narrative volume reclaims top meme-coin ranking",
        "body": "Renewed retail interest pushes meme-sector trading volume back above prior cycle highs.",
    },
    {
        "narrative": "LAYER 2",
        "source": "Reuters",
        "hot": False,
        "coin_symbol": "ARB",
        "time": "1h ago",
        "headline": "Arbitrum narrative strengthens on new rollup throughput data",
        "body": "Daily transaction throughput hits a fresh high as builders migrate additional volume to the rollup.",
    },
    {
        "narrative": "RESTAKING",
        "source": "CoinDesk",
        "hot": True,
        "coin_symbol": "ETHFI",
        "time": "2h ago",
        "headline": "EtherFi narrative accelerates as restaking TVL climbs",
        "body": "Liquid restaking narrative gains traction with deposits crossing another milestone this week.",
    },
    {
        "narrative": "AI AGENTS",
        "source": "Bloomberg",
        "hot": False,
        "coin_symbol": "FET",
        "time": "2h ago",
        "headline": "Fetch.ai narrative broadens on agent marketplace launch",
        "body": "New agent marketplace integration expands the narrative's addressable use cases beyond compute.",
    },
    {
        "narrative": "GAMING",
        "source": "Cointelegraph",
        "hot": False,
        "coin_symbol": "IMX",
        "time": "3h ago",
        "headline": "Immutable narrative firms up on new studio partnerships",
        "body": "Additional game studios commit to the network, reinforcing the gaming narrative's builder base.",
    },
    {
        "narrative": "STABLECOIN",
        "source": "Reuters",
        "hot": True,
        "coin_symbol": "USDe",
        "time": "3h ago",
        "headline": "Ethena narrative expands as synthetic dollar supply grows",
        "body": "Synthetic stablecoin narrative gains share as yield-bearing demand pulls in fresh supply.",
    },
    {
        "narrative": "ORACLE",
        "source": "CoinDesk",
        "hot": False,
        "coin_symbol": "LINK",
        "time": "4h ago",
        "headline": "Chainlink narrative reinforced by new CCIP integrations",
        "body": "Cross-chain interoperability narrative strengthens as additional protocols adopt the standard.",
    },
    {
        "narrative": "DEPIN",
        "source": "Bloomberg",
        "hot": True,
        "coin_symbol": "HNT",
        "time": "4h ago",
        "headline": "Helium narrative gains as physical infrastructure demand rises",
        "body": "Decentralized wireless narrative accelerates as carrier offload volumes continue climbing.",
    },
    {
        "narrative": "REAL-WORLD ASSETS (RWA)",
        "source": "Cointelegraph",
        "hot": False,
        "coin_symbol": "POLYX",
        "time": "5h ago",
        "headline": "Polymesh narrative widens on institutional tokenization pilot",
        "body": "A new institutional pilot broadens the RWA narrative beyond treasury products into equities.",
    },
    {
        "narrative": "PRIVACY",
        "source": "Reuters",
        "hot": False,
        "coin_symbol": "ZEC",
        "time": "6h ago",
        "headline": "Zcash narrative resurfaces on renewed shielded-pool usage",
        "body": "Shielded transaction volume ticks higher as privacy-focused narrative regains some attention.",
    },
    {
        "narrative": "LAYER 1",
        "source": "CoinDesk",
        "hot": False,
        "coin_symbol": "AVAX",
        "time": "7h ago",
        "headline": "Avalanche narrative broadens on subnet deployment growth",
        "body": "New subnet launches add to the Layer 1 narrative's enterprise and gaming use-case count.",
    },
    {
        "narrative": "DEFI",
        "source": "Bloomberg",
        "hot": True,
        "coin_symbol": "PENDLE",
        "time": "8h ago",
        "headline": "Pendle narrative accelerates as yield-tokenization volume climbs",
        "body": "Yield-tokenization narrative gains momentum as more assets get wrapped into tradable yield markets.",
    },
    {
        "narrative": "BITCOIN ECOSYSTEM",
        "source": "Cointelegraph",
        "hot": False,
        "coin_symbol": "STX",
        "time": "9h ago",
        "headline": "Stacks narrative firms up on Bitcoin L2 activity uptick",
        "body": "Bitcoin-secured smart contract narrative strengthens as layer activity ticks higher this week.",
    },
    {
        "narrative": "TOKENIZED ASSETS",
        "source": "Reuters",
        "hot": False,
        "coin_symbol": "MKR",
        "time": "10h ago",
        "headline": "MakerDAO narrative expands on real-world collateral growth",
        "body": "Tokenized collateral narrative broadens as the protocol's real-world asset allocation increases.",
    },
    {
        "narrative": "INFRASTRUCTURE",
        "source": "CoinDesk",
        "hot": True,
        "coin_symbol": "GRT",
        "time": "11h ago",
        "headline": "The Graph narrative gains on expanded indexing coverage",
        "body": "Data-indexing narrative strengthens as coverage expands across additional major chains.",
    },
]


def _alert_card(item: dict) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.badge(item["source"], color_scheme=_SOURCE_COLORS.get(item["source"], "gray"), size="1"),
            rx.spacer(),
            rx.text(item["time"], size="1", color_scheme="gray"),
            width="100%",
            align="center",
        ),
        rx.hstack(
            rx.badge(item["coin_symbol"], color_scheme="indigo", size="1"),
            rx.badge(item["narrative"], color_scheme="orange", size="1"),
            margin_top="0.5em",
            width="100%",
            direction="row-reverse",
            justify="end",
        ),
        rx.text(item["headline"], weight="bold", size="2", margin_top="0.4em"),
        rx.text(item["body"], size="1", color_scheme="gray", margin_top="0.3em"),
        padding="0.85em",
        border_radius="8px",
        background="var(--gray-a2)",
        # Narrower on phone widths — a 340px card on a 320px-wide iPhone 4
        # viewport would leave no room to see the slider is scrollable.
        width=["250px", "270px", "310px", "340px", "340px"],
        flex_shrink="0",
        height="100%",
        overflow_y="scroll",
    )


def _alerts_slider() -> rx.Component:
    # Same draggable/arrow-scrollable mechanics as the news slider
    # (assets/chain_pills.js — its selectors include these alerts-slider
    # class names too), just alert cards instead of news cards.
    return rx.box(
        rx.box(
            rx.icon("chevron-left", size=14),
            class_name="alerts-scroll-btn alerts-scroll-left",
        ),
        rx.box(
            *[_alert_card(item) for item in ALERTS],
            class_name="alerts-slider-track",
        ),
        rx.box(
            rx.icon("chevron-right", size=14),
            class_name="alerts-scroll-btn alerts-scroll-right",
        ),
        class_name="alerts-slider-wrap",
    )


def _more_impact_link() -> rx.Component:
    # No feature wired up yet — will surface which coins/narratives a news
    # item affects once that correlation feature is built (see
    # news_feed.py's matching link for the same upcoming feature).
    return rx.link(
        rx.hstack(
            rx.text("More Impact", size="2", weight="bold"),
            rx.icon("arrow-right", size=14),
            spacing="1",
            align="center",
        ),
        href="#view-news-impact",
        underline="none",
        color_scheme="indigo",
        margin_left="1.5em",
    )


def narrative_alerts() -> rx.Component:
    return rx.vstack(
        rx.text("TARGETED NARRATIVE ALERTS", size="1", color_scheme="gray", weight="bold"),
        rx.box(
            # named "sm" = 768px (matches the 768px used elsewhere via
            # plain-list position 2) — named "md" is 992px.
            rx.heading("Targeted Narrative + Coin", size=rx.breakpoints(initial="4", sm="5")),
            _more_impact_link(),
            display="flex",
            flex_wrap="wrap",
            justify_content="space-between",
            align_items="center",
            width="100%",
            style={"row-gap": "0.25em"},
        ),
        _alerts_slider(),
        spacing="3",
        width="100%",
        align_items="stretch",
    )
