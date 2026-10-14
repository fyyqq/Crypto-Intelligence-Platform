"""Row of four equal-height cards above the homepage news strip. The first is
the "Market Status" card (Fear & Greed, total market cap, top 20, Altcoin
Season, from MarketStatusState); the other three are still empty placeholders
(Trending Coins / Derivatives / promo)."""

import reflex as rx

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


def market_overview() -> rx.Component:
    return rx.grid(
        _market_status_card(),
        *[_overview_card() for _ in range(3)],
        # 1 column on phones, 2 on tablets, 4 in one row from desktop width.
        columns=rx.breakpoints(initial="1", sm="2", lg="4"),
        spacing="4",
        width="100%",
    )
