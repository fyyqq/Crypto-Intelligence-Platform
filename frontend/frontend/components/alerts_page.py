"""/alerts — the account's active price alerts (a triggered alert is deleted; its notification is the record)."""

import reflex as rx

from frontend.state import CoinState


def _active_row(alert: rx.Var[dict]) -> rx.Component:
    return rx.hstack(
        rx.link(
            rx.hstack(
                rx.image(src=alert["icon_url"], width="32px", height="32px", border_radius="50%", flex_shrink="0"),
                rx.vstack(
                    rx.hstack(
                        rx.text(alert["name"], size="3", weight="bold"),
                        rx.text(alert["symbol"], size="2", color_scheme="gray"),
                        spacing="2",
                        align="center",
                        wrap="wrap",
                    ),
                    rx.text(
                        rx.cond(alert["direction"] == "above", "Alert when price rises above ", "Alert when price falls below "),
                        rx.text.strong(alert["display"]),
                        " · now ",
                        alert["current_display"],
                        size="2",
                        color_scheme="gray",
                    ),
                    spacing="0",
                    align="start",
                    min_width="0",
                ),
                spacing="3",
                align="center",
            ),
            href=alert["coin_url"],
            underline="none",
            color="inherit",
            flex="1",
            min_width="0",
        ),
        rx.icon(
            rx.cond(alert["direction"] == "above", "trending-up", "trending-down"),
            size=18,
            color=rx.cond(alert["direction"] == "above", "var(--green-9)", "var(--red-9)"),
            flex_shrink="0",
        ),
        rx.icon(
            "x",
            size=18,
            color="var(--gray-9)",
            cursor="pointer",
            flex_shrink="0",
            on_click=CoinState.delete_alert_by_id(alert["cmc_id"], alert["id"]),
        ),
        spacing="3",
        align="center",
        width="100%",
        padding="0.85em 1em",
        border_radius="10px",
        background="var(--gray-a2)",
        border="1px solid var(--gray-a4)",
    )


def alerts_content() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("bell", size=22),
            rx.heading("Alerts", size="6"),
            spacing="3",
            align="center",
        ),
        rx.hstack(
            rx.heading("Active alerts", size="4"),
            rx.badge(CoinState.active_alerts_all.length(), variant="soft", radius="full"),
            spacing="2",
            align="center",
        ),
        rx.cond(
            CoinState.active_alerts_all.length() > 0,
            rx.vstack(rx.foreach(CoinState.active_alerts_all, _active_row), spacing="2", width="100%"),
            rx.text(
                "No active alerts. Open a coin page and press Add New Alert to create one.",
                size="2",
                color_scheme="gray",
            ),
        ),
        spacing="3",
        align="start",
        width="100%",
        max_width="860px",
        margin_x="auto",
    )
