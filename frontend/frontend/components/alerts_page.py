"""/alerts — history of triggered price alerts."""

import reflex as rx

from frontend.state import CoinState


def _history_row(entry: rx.Var[dict]) -> rx.Component:
    return rx.hstack(
        rx.image(src=entry["icon_url"], width="32px", height="32px", border_radius="50%", flex_shrink="0"),
        rx.vstack(
            rx.hstack(
                rx.text(entry["name"], size="3", weight="bold"),
                rx.text(entry["symbol"], size="2", color_scheme="gray"),
                spacing="2",
                align="center",
                wrap="wrap",
            ),
            rx.text(
                rx.cond(entry["direction"] == "above", "Rose above ", "Fell below "),
                rx.text.strong(entry["target_display"]),
                " · price then ",
                rx.text.strong(entry["price_display"]),
                size="2",
                color_scheme="gray",
            ),
            spacing="0",
            align="start",
            min_width="0",
            flex="1",
        ),
        rx.icon(
            rx.cond(entry["direction"] == "above", "trending-up", "trending-down"),
            size=18,
            color=rx.cond(entry["direction"] == "above", "var(--green-9)", "var(--red-9)"),
            flex_shrink="0",
        ),
        rx.text(entry["time_display"], size="1", color_scheme="gray", flex_shrink="0"),
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
            rx.badge(CoinState.alert_history.length(), variant="soft", radius="full"),
            spacing="3",
            align="center",
        ),
        rx.text("History of the price alerts that have triggered.", size="2", color_scheme="gray"),
        rx.cond(
            CoinState.is_logged_in,
            rx.fragment(),
            rx.callout.root(
                rx.callout.icon(rx.icon("info", size=16)),
                rx.callout.text(
                    "Log in to keep your alerts and this history across devices and restarts. ",
                    rx.link("Log in", href="/login", weight="medium"),
                ),
                size="1",
                width="100%",
            ),
        ),
        rx.cond(
            CoinState.alert_history.length() > 0,
            rx.vstack(rx.foreach(CoinState.alert_history, _history_row), spacing="2", width="100%"),
            rx.center(
                rx.vstack(
                    rx.icon("bell-off", size=28, color="var(--gray-9)"),
                    rx.text("No triggered alerts yet", weight="medium"),
                    rx.text(
                        "Add a price alert on any coin page; it shows up here once the price reaches it.",
                        size="2",
                        color_scheme="gray",
                        text_align="center",
                    ),
                    align="center",
                    spacing="2",
                ),
                height="40vh",
                width="100%",
            ),
        ),
        spacing="3",
        align="start",
        width="100%",
        max_width="860px",
        margin_x="auto",
    )
