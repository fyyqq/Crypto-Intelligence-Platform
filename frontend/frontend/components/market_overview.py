"""Row of four equal-height, empty cards above the homepage news strip
(placeholders for Market Status / Trending Coins / Derivatives / promo)."""

import reflex as rx

_CARD_HEIGHT = "260px"


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


def market_overview() -> rx.Component:
    return rx.grid(
        *[_overview_card() for _ in range(4)],
        # 1 column on phones, 2 on tablets, 4 in one row from desktop width.
        columns=rx.breakpoints(initial="1", sm="2", lg="4"),
        spacing="4",
        width="100%",
    )
