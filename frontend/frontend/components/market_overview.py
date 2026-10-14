"""Row of four equal-height cards above the homepage news strip:
1. Market Status (Fear & Greed, total market cap, top 20, Altcoin Season; MarketStatusState)
2. Gainers & Losers (top 5 gainers / top 5 losers of the Top 100 over 24h, two pages; HomeMoversState)
3. still an empty placeholder
4. Community (sample posts for now: static dummy data, no real accounts)."""

import reflex as rx

from frontend.state.home_movers_state import HomeMoversState as H
from frontend.state.market_status_state import MarketStatusState as M

_CARD_HEIGHT = "300px"
_INNER = dict(
    padding="0.6em 0.8em",
    border_radius="10px",
    border="1px solid var(--gray-a5)",
    background="var(--gray-a2)",
)


def _overview_card() -> rx.Component:
    return rx.box(
        class_name="market-overview-card",
        height=_CARD_HEIGHT,
        width="100%",
        padding="1em",
        border_radius="12px",
        border="1px solid var(--gray-a5)",
        background="var(--gray-a2)",
    )


def _label(text: str) -> rx.Component:
    return rx.text(text, size="2", color="var(--gray-11)", white_space="nowrap")


def _figure(value: rx.Var, change: rx.Var, color: rx.Var) -> rx.Component:
    # Value and change on one line (like the reference); wraps on a very narrow card.
    return rx.cond(
        M.loaded,
        rx.hstack(
            rx.text(value, size="4", weight="bold", color="var(--gray-12)", white_space="nowrap"),
            rx.cond(change != "", rx.text(change, size="2", weight="medium", color=color, white_space="nowrap")),
            spacing="1",
            align="baseline",
            wrap="wrap",
            column_gap="0.5em",
            row_gap="0",
        ),
        rx.skeleton(height="22px", width="70%"),
    )


def _stat(label: str, value: rx.Var, change: rx.Var, color: rx.Var) -> rx.Component:
    return rx.vstack(_label(label), _figure(value, change, color), spacing="1", align="start", justify="center", **_INNER)


def _fear_greed() -> rx.Component:
    return rx.vstack(
        _label("Fear & Greed"),
        rx.cond(
            M.has_fng,
            rx.vstack(
                rx.box(rx.html(M.fng_svg), width="100%", max_width="150px"),
                rx.badge(
                    M.fng_label,
                    variant="solid",
                    radius="full",
                    size="2",
                    style={"background": M.fng_color, "color": M.fng_text_color},
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.cond(
                M.loaded,
                rx.text("—", size="5", color="var(--gray-11)"),
                rx.skeleton(height="80px", width="100%", border_radius="8px"),
            ),
        ),
        spacing="1",
        align="center",
        justify="between",
        grid_row="span 2",
        **_INNER,
    )


def _altcoin_season() -> rx.Component:
    # Orange = Bitcoin season (0-25), blue = Altcoin season (75-100).
    bar = rx.box(
        rx.box(
            position="absolute",
            top="50%",
            left=M.season_left,
            width="16px",
            height="16px",
            border_radius="50%",
            background="#ffffff",
            border="1.5px solid rgba(0, 0, 0, 0.35)",
            transform="translateY(-50%)",
            box_shadow="0 1px 4px rgba(0, 0, 0, 0.35)",
        ),
        position="relative",
        flex="1",
        min_width="0",
        height="8px",
        border_radius="999px",
        background="linear-gradient(90deg, #ef8f3a 0 25%, #fbd5b0 25% 50%, #c7d1f7 50% 75%, #3f5bf2 75% 100%)",
    )
    return rx.vstack(
        _label("Altcoin Season"),
        rx.cond(
            M.has_season,
            rx.hstack(
                rx.text(M.season_value, size="5", weight="bold", color="var(--gray-12)"),
                bar,
                spacing="4",
                align="center",
                width="100%",
                title=M.season_label,
            ),
            rx.cond(
                M.loaded,
                rx.text("—", size="5", color="var(--gray-11)"),
                rx.skeleton(height="24px", width="100%"),
            ),
        ),
        spacing="1",
        align="start",
        justify="center",
        grid_column="1 / -1",
        **_INNER,
    )


def _market_status_card() -> rx.Component:
    return rx.box(
        rx.link(
            rx.hstack(
                rx.heading("Market Status", size="4", color="var(--gray-12)"),
                rx.icon("chevron-right", size=18, color="var(--gray-11)"),
                spacing="1",
                align="center",
            ),
            href="/tools",
            underline="none",
        ),
        rx.grid(
            _fear_greed(),
            _stat("Market Cap", M.mcap, M.mcap_change, M.mcap_color),
            _stat("Top 20", M.top20, M.top20_change, M.top20_color),
            _altcoin_season(),
            columns="minmax(0, 1fr) minmax(0, 1.2fr)",
            rows="repeat(3, minmax(0, 1fr))",
            spacing="2",
            width="100%",
            flex="1",
            min_height="0",
            margin_top="0.6em",
        ),
        class_name="market-overview-card market-status-card",
        display="flex",
        flex_direction="column",
        height=_CARD_HEIGHT,
        width="100%",
        padding="1em",
        border_radius="12px",
        border="1px solid var(--gray-a5)",
        background="var(--gray-a2)",
    )


_CARD = dict(
    display="flex",
    flex_direction="column",
    height=_CARD_HEIGHT,
    width="100%",
    padding="1em",
    border_radius="12px",
    border="1px solid var(--gray-a5)",
    background="var(--gray-a2)",
)


def _card_title(text, href: str | None = None) -> rx.Component:
    title = rx.hstack(
        rx.heading(text, size="4", color="var(--gray-12)", white_space="nowrap"),
        rx.icon("chevron-right", size=18, color="var(--gray-11)"),
        spacing="1",
        align="center",
    )
    return rx.link(title, href=href, underline="none") if href else title


# ---- Gainers & Losers (top 5, two pages) ------------------------------------------------------

def _mover_row(row: rx.Var[dict]) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.text(row["position"], size="3", color="var(--gray-10)", width="1.1em", flex_shrink="0"),
            rx.image(src=row["icon_url"], width="30px", height="30px", border_radius="50%", flex_shrink="0"),
            rx.text(row["symbol"], size="3", weight="medium", color="var(--gray-12)", class_name="line-clamp-1", min_width="0"),
            rx.spacer(),
            rx.text(row["price"], size="3", color="var(--gray-12)", white_space="nowrap"),
            rx.text(row["change"], size="3", weight="medium", color=row["color"], white_space="nowrap", min_width="5.2em", text_align="right"),
            spacing="3",
            align="center",
            width="100%",
        ),
        href=row["href"],
        underline="none",
        color="inherit",
        display="block",
        width="100%",
        padding_y="0.3em",
        border_radius="8px",
        _hover={"background": "var(--gray-a3)"},
    )


def _pager() -> rx.Component:
    arrow = dict(variant="ghost", color_scheme="gray", size="1", cursor="pointer", on_click=H.flip_page)
    return rx.hstack(
        rx.icon_button(rx.icon("chevron-left", size=16), aria_label="Previous page", **arrow),
        rx.text(H.page_label, size="2", color="var(--gray-11)", min_width="2.2em", text_align="center"),
        rx.icon_button(rx.icon("chevron-right", size=16), aria_label="Next page", **arrow),
        spacing="1",
        align="center",
    )


def _movers_body() -> rx.Component:
    return rx.cond(
        ~H.loaded,
        rx.vstack(*[rx.skeleton(height="34px", width="100%", border_radius="8px") for _ in range(5)], spacing="2", width="100%"),
        rx.cond(
            H.collecting != "",
            rx.center(
                rx.vstack(
                    rx.icon("hourglass", size=24, color="var(--gray-9)"),
                    rx.text("Collecting data for the 24h board", size="2", weight="medium"),
                    rx.text("Ready in ", H.collecting, size="2", color="var(--gray-11)"),
                    spacing="2",
                    align="center",
                ),
                flex="1",
            ),
            rx.cond(
                H.rows.length() > 0,
                rx.vstack(rx.foreach(H.rows, _mover_row), spacing="1", width="100%", justify="between", flex="1"),
                rx.center(rx.text("No data yet", size="2", color="var(--gray-11)"), flex="1"),
            ),
        ),
    )


def _movers_card() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                _card_title(H.title, "/gainers-losers"),
                rx.text("24h · Top 100", size="1", color="var(--gray-10)"),
                spacing="0",
                align="start",
            ),
            _pager(),
            justify="between",
            align="start",
            width="100%",
            margin_bottom="0.4em",
        ),
        _movers_body(),
        class_name="market-overview-card movers-card",
        **_CARD,
    )


# ---- Community (sample posts) -------------------------------------------------------------------
# Placeholder content: invented handles and headlines, no real accounts. Replace with real data later.
_POSTS = [
    {"name": "CryptoNova", "initial": "C", "color": "#7c5cff", "time": "2h", "score": "101.78", "coin": "$BTC",
     "text": "Is Holding $83K, But Traders Are Preparing for Volatility. 👀…", "mood": ""},
    {"name": "BlockSage", "initial": "B", "color": "#1f9d8b", "time": "2h", "score": "132.73", "coin": "",
     "text": "🏦 A Major Bank Brings Bitcoin and ETH Trading to New Clients…", "mood": "Bullish"},
]


def _post(p: dict) -> rx.Component:
    head = [
        rx.text(p["name"], size="2", weight="bold", color="var(--gray-12)", white_space="nowrap"),
        rx.icon("badge-check", size=15, color="var(--accent-10)", flex_shrink="0"),
        rx.text(f"· {p['time']}", size="2", color="var(--gray-10)", white_space="nowrap"),
    ]
    if p["mood"]:
        head += [
            rx.icon("trending-up", size=14, color="var(--green-10)", flex_shrink="0"),
            rx.text(p["mood"], size="2", weight="medium", color="var(--green-10)", white_space="nowrap"),
        ]
    text = rx.text(
        *([rx.text(p["coin"] + " ", as_="span", color="var(--accent-11)")] if p["coin"] else []),
        p["text"],
        size="2",
        color="var(--gray-12)",
        class_name="line-clamp-2",
    )
    return rx.hstack(
        rx.center(
            rx.text(p["initial"], size="3", weight="bold", color="#ffffff"),
            width="36px",
            height="36px",
            border_radius="50%",
            background=p["color"],
            flex_shrink="0",
        ),
        rx.vstack(
            rx.hstack(*head, spacing="1", align="center", wrap="wrap"),
            rx.text(f"{p['score']} Influence Score", size="1", color="var(--gray-10)"),
            text,
            spacing="0",
            align="start",
            min_width="0",
            flex="1",
        ),
        spacing="3",
        align="start",
        width="100%",
        padding="0.55em 0.75em",
        border_radius="10px",
        border="1px solid var(--gray-a5)",
        background="var(--gray-a2)",
    )


def _community_card() -> rx.Component:
    return rx.box(
        _card_title("Community"),
        rx.vstack(*[_post(p) for p in _POSTS], spacing="2", width="100%", margin_top="0.6em", flex="1", min_height="0"),
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
