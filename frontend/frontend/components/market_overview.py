"""Row of four equal-height cards above the homepage news strip:
1. Market Status (Fear & Greed, total market cap, top 20, Altcoin Season; MarketStatusState)
2. Gainers & Losers (top 5 gainers / top 5 losers of the Top 100 over 24h, two pages; HomeMoversState)
3. still an empty placeholder
4. Incoming News (sample items for now: static dummy data, no real accounts; was titled "Community").

Layout spec (matched to CoinMarketCap's cards, 2026-10-14): every card is 244px
tall with 16px padding and a one-line, 24px title row. Market Status is a 2 x 3
grid of equal columns and equal rows with 8px gaps; every cell has its label
top-left (12px grey) and its content below; Fear & Greed spans two rows and
Altcoin Season spans both columns. The movers card has five equal rows."""

import reflex as rx

from frontend.state.home_movers_state import HomeMoversState as H
from frontend.state.market_status_state import MarketStatusState as M

_CARD_HEIGHT = "244px"
_CARD = dict(
    display="flex",
    flex_direction="column",
    height=_CARD_HEIGHT,
    width="100%",
    padding="16px",
    border_radius="12px",
    border="1px solid var(--gray-a5)",
    background="var(--gray-a2)",
    overflow="hidden",
)
_CELL = dict(
    padding="8px 10px",
    border_radius="10px",
    border="1px solid var(--gray-a5)",
    background="var(--gray-a2)",
    min_width="0",
    overflow="hidden",
)


def _overview_card() -> rx.Component:
    return rx.box(class_name="market-overview-card", **_CARD)


def _card_title(text, href: str | None = None) -> rx.Component:
    """One-line card title with a chevron, 24px tall."""
    title = rx.hstack(
        rx.heading(text, size="3", color="var(--gray-12)", white_space="nowrap"),
        rx.icon("chevron-right", size=16, color="var(--gray-11)"),
        spacing="1",
        align="center",
        height="24px",
    )
    return rx.link(title, href=href, underline="none") if href else title


# ---- Market Status ------------------------------------------------------------------------------

def _label(text: str) -> rx.Component:
    return rx.text(text, size="1", color="var(--gray-11)", white_space="nowrap", line_height="16px")


def _figure(value: rx.Var, change: rx.Var, color: rx.Var) -> rx.Component:
    # Value and change on one line; wraps only on a very narrow card.
    return rx.cond(
        M.loaded,
        rx.hstack(
            rx.text(value, size="3", weight="bold", color="var(--gray-12)", white_space="nowrap", line_height="20px"),
            rx.cond(change != "", rx.text(change, size="1", weight="medium", color=color, white_space="nowrap")),
            spacing="2",
            align="baseline",
            wrap="wrap",
            row_gap="0",
        ),
        rx.skeleton(height="20px", width="70%"),
    )


def _stat(label: str, value: rx.Var, change: rx.Var, color: rx.Var) -> rx.Component:
    return rx.vstack(_label(label), _figure(value, change, color), spacing="0", align="start", justify="center", **_CELL)


def _fear_greed() -> rx.Component:
    return rx.vstack(
        _label("Fear & Greed"),
        rx.cond(
            M.has_fng,
            rx.vstack(
                rx.box(rx.html(M.fng_svg), width="100%", max_width="104px"),
                rx.badge(
                    M.fng_label,
                    variant="solid",
                    radius="full",
                    size="1",
                    style={"background": M.fng_color, "color": M.fng_text_color},
                ),
                spacing="1",
                align="center",
                justify="center",
                width="100%",
                flex="1",
                min_height="0",
            ),
            rx.cond(
                M.loaded,
                rx.text("—", size="3", color="var(--gray-11)"),
                rx.skeleton(height="64px", width="100%", border_radius="8px"),
            ),
        ),
        spacing="0",
        align="start",
        grid_row="span 2",
        **_CELL,
    )


def _altcoin_season() -> rx.Component:
    # Orange = Bitcoin season (0-25), blue = Altcoin season (75-100).
    bar = rx.box(
        rx.box(
            position="absolute",
            top="50%",
            left=M.season_left,
            width="12px",
            height="12px",
            border_radius="50%",
            background="#ffffff",
            border="1.5px solid rgba(0, 0, 0, 0.35)",
            transform="translateY(-50%)",
            box_shadow="0 1px 3px rgba(0, 0, 0, 0.35)",
        ),
        position="relative",
        flex="1",
        min_width="0",
        height="6px",
        border_radius="999px",
        background="linear-gradient(90deg, #ef8f3a 0 25%, #fbd5b0 25% 50%, #c7d1f7 50% 75%, #3f5bf2 75% 100%)",
    )
    return rx.vstack(
        _label("Altcoin Season"),
        rx.cond(
            M.has_season,
            rx.hstack(
                rx.text(M.season_value, size="3", weight="bold", color="var(--gray-12)", line_height="20px"),
                bar,
                spacing="3",
                align="center",
                width="100%",
                title=M.season_label,
            ),
            rx.cond(
                M.loaded,
                rx.text("—", size="3", color="var(--gray-11)"),
                rx.skeleton(height="20px", width="100%"),
            ),
        ),
        spacing="0",
        align="start",
        justify="center",
        grid_column="1 / -1",
        **_CELL,
    )


def _market_status_card() -> rx.Component:
    return rx.box(
        _card_title("Market Status", "/tools/market-indicators"),
        rx.grid(
            _fear_greed(),
            _stat("Market Cap", M.mcap, M.mcap_change, M.mcap_color),
            _stat("Top 20", M.top20, M.top20_change, M.top20_color),
            _altcoin_season(),
            columns="repeat(2, minmax(0, 1fr))",
            rows="repeat(3, minmax(0, 1fr))",
            spacing="2",
            width="100%",
            flex="1",
            min_height="0",
            margin_top="10px",
        ),
        class_name="market-overview-card market-status-card",
        **_CARD,
    )


# ---- Gainers & Losers (top 5, two pages) ------------------------------------------------------

def _mover_row(row: rx.Var[dict]) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.text(row["position"], size="2", color="var(--gray-10)", width="1.1em", flex_shrink="0"),
            rx.image(src=row["icon_url"], width="24px", height="24px", border_radius="50%", flex_shrink="0"),
            rx.text(row["symbol"], size="2", weight="medium", color="var(--gray-12)", class_name="line-clamp-1", min_width="0"),
            rx.spacer(),
            rx.text(row["price"], size="2", color="var(--gray-12)", white_space="nowrap"),
            rx.text(row["change"], size="2", weight="medium", color=row["color"], white_space="nowrap", min_width="4.6em", text_align="right"),
            spacing="2",
            align="center",
            width="100%",
        ),
        href=row["href"],
        underline="none",
        color="inherit",
        display="flex",
        align_items="center",
        flex="1",
        min_height="0",
        width="100%",
        padding_x="4px",
        margin_x="-4px",
        border_radius="8px",
        _hover={"background": "var(--gray-a3)"},
    )


def _pager() -> rx.Component:
    arrow = dict(variant="ghost", color_scheme="gray", size="1", cursor="pointer", on_click=H.flip_page, padding="0")
    return rx.hstack(
        rx.icon_button(rx.icon("chevron-left", size=14), aria_label="Previous page", **arrow),
        rx.text(H.page_label, size="1", color="var(--gray-11)", min_width="2em", text_align="center"),
        rx.icon_button(rx.icon("chevron-right", size=14), aria_label="Next page", **arrow),
        spacing="1",
        align="center",
        height="24px",
    )


def _movers_body() -> rx.Component:
    return rx.cond(
        ~H.loaded,
        rx.vstack(*[rx.skeleton(height="100%", width="100%", border_radius="8px", flex="1") for _ in range(5)], spacing="2", width="100%", flex="1"),
        rx.cond(
            H.collecting != "",
            rx.center(
                rx.vstack(
                    rx.icon("hourglass", size=22, color="var(--gray-9)"),
                    rx.text("Collecting data for the 24h board", size="2", weight="medium"),
                    rx.text("Ready in ", H.collecting, size="1", color="var(--gray-11)"),
                    spacing="1",
                    align="center",
                ),
                flex="1",
            ),
            rx.cond(
                H.rows.length() > 0,
                rx.vstack(rx.foreach(H.rows, _mover_row), spacing="0", width="100%", flex="1", min_height="0"),
                rx.center(rx.text("No data yet", size="2", color="var(--gray-11)"), flex="1"),
            ),
        ),
    )


def _movers_card() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.hstack(
                _card_title(H.title, "/gainers-losers"),
                rx.badge("24H", variant="soft", color_scheme="gray", size="1", title="Top 100 coins by rank, 24h change"),
                spacing="2",
                align="center",
                min_width="0",
            ),
            _pager(),
            justify="between",
            align="center",
            width="100%",
            margin_bottom="6px",
        ),
        _movers_body(),
        class_name="market-overview-card movers-card",
        **_CARD,
    )


# ---- Incoming News (sample items) -------------------------------------------------------------------
# Placeholder content: invented handles and headlines, no real accounts. Replace with real data later.
_POSTS = [
    {"name": "CryptoNova", "initial": "C", "color": "#7c5cff", "time": "2h", "score": "101.78", "coin": "$BTC",
     "text": "Is Holding $83K, But Traders Are Preparing for Volatility. 👀…", "mood": ""},
    {"name": "BlockSage", "initial": "B", "color": "#1f9d8b", "time": "2h", "score": "132.73", "coin": "",
     "text": "🏦 A Major Bank Brings Bitcoin and ETH Trading to New Clients…", "mood": "Bullish"},
]


def _post(p: dict) -> rx.Component:
    head = [
        rx.text(p["name"], size="2", weight="bold", color="var(--gray-12)", white_space="nowrap", overflow="hidden", text_overflow="ellipsis", min_width="0"),
        rx.icon("badge-check", size=14, color="var(--accent-10)", flex_shrink="0"),
        rx.text(f"· {p['time']}", size="1", color="var(--gray-10)", white_space="nowrap"),
    ]
    if p["mood"]:
        head += [
            rx.icon("trending-up", size=13, color="var(--green-10)", flex_shrink="0"),
            rx.text(p["mood"], size="1", weight="medium", color="var(--green-10)", white_space="nowrap"),
        ]
    text = rx.text(
        *([rx.text(p["coin"] + " ", as_="span", color="var(--accent-11)")] if p["coin"] else []),
        p["text"],
        size="1",
        color="var(--gray-12)",
        class_name="line-clamp-2",
        line_height="1.4",
    )
    return rx.hstack(
        rx.center(
            rx.text(p["initial"], size="2", weight="bold", color="#ffffff"),
            width="30px",
            height="30px",
            border_radius="50%",
            background=p["color"],
            flex_shrink="0",
        ),
        rx.vstack(
            rx.hstack(*head, spacing="1", align="center", flex_wrap="nowrap", width="100%", min_width="0"),
            rx.text(f"{p['score']} Influence Score", size="1", color="var(--gray-10)"),
            text,
            spacing="0",
            align="start",
            min_width="0",
            flex="1",
        ),
        spacing="2",
        align="center",
        width="100%",
        flex="1",
        min_height="0",
        **_CELL,
    )


def _community_card() -> rx.Component:
    return rx.box(
        _card_title("Incoming News"),
        rx.vstack(*[_post(p) for p in _POSTS], spacing="2", width="100%", margin_top="8px", flex="1", min_height="0"),
        class_name="market-overview-card community-card",
        **_CARD,
    )


def market_overview() -> rx.Component:
    return rx.grid(
        _market_status_card(),
        _movers_card(),
        _overview_card(),
        _community_card(),
        # 1 column on phones, 2 on tablets, 4 in one row from desktop width.
        columns=rx.breakpoints(initial="1", sm="2", lg="4"),
        spacing="4",
        width="100%",
    )
