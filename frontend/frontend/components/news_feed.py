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
    {
        "source": "Bloomberg",
        "time": "5h ago",
        "headline": "Coinbase deepens institutional custody partnerships amid ETF inflows",
        "tags": ["Institutional", "ETF"],
    },
    {
        "source": "Reuters",
        "time": "6h ago",
        "headline": "EU regulators finalize MiCA guidance for stablecoin issuers",
        "tags": ["Regulation", "Stablecoin"],
    },
    {
        "source": "CoinDesk",
        "time": "7h ago",
        "headline": "Restaking protocols surpass $15B in total value locked",
        "tags": ["Restaking", "DeFi"],
    },
    {
        "source": "Cointelegraph",
        "time": "8h ago",
        "headline": "Base network activity surges on new memecoin launches",
        "tags": ["Base", "Memes"],
    },
    {
        "source": "Bloomberg",
        "time": "9h ago",
        "headline": "Grayscale files for spot Solana ETF alongside rivals",
        "tags": ["ETF", "Solana"],
    },
    {
        "source": "Reuters",
        "time": "10h ago",
        "headline": "Hong Kong expands licensed exchange framework for retail investors",
        "tags": ["Regulation", "Asia"],
    },
    {
        "source": "CoinDesk",
        "time": "11h ago",
        "headline": "Arbitrum DAO approves treasury diversification proposal",
        "tags": ["Arbitrum", "DAO"],
    },
    {
        "source": "Cointelegraph",
        "time": "12h ago",
        "headline": "Bitcoin miners accelerate hashrate expansion ahead of halving cycle",
        "tags": ["Mining", "Bitcoin"],
    },
    {
        "source": "Bloomberg",
        "time": "13h ago",
        "headline": "Tether reports record quarterly profit on reserve yield",
        "tags": ["Stablecoin", "Earnings"],
    },
    {
        "source": "Reuters",
        "time": "14h ago",
        "headline": "Singapore central bank pilots wholesale CBDC settlement",
        "tags": ["CBDC", "Regulation"],
    },
    {
        "source": "CoinDesk",
        "time": "15h ago",
        "headline": "Uniswap Labs unveils cross-chain swap aggregation update",
        "tags": ["DeFi", "Uniswap"],
    },
    {
        "source": "Cointelegraph",
        "time": "16h ago",
        "headline": "NFT marketplace volume rebounds on gaming asset demand",
        "tags": ["NFT", "Gaming"],
    },
    {
        "source": "Bloomberg",
        "time": "18h ago",
        "headline": "Fidelity expands crypto custody services for pension clients",
        "tags": ["Institutional", "Custody"],
    },
    {
        "source": "Reuters",
        "time": "20h ago",
        "headline": "South Korea proposes revised digital asset taxation timeline",
        "tags": ["Regulation", "Tax"],
    },
    {
        "source": "CoinDesk",
        "time": "22h ago",
        "headline": "Polygon rolls out zk-rollup upgrade to cut settlement costs",
        "tags": ["Polygon", "Layer 2"],
    },
    {
        "source": "Cointelegraph",
        "time": "1d ago",
        "headline": "Liquid staking derivatives near all-time high market share",
        "tags": ["Staking", "DeFi"],
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
