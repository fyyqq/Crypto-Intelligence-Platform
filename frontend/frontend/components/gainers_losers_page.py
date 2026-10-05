"""/gainers-losers: top gainers and top losers by rank bucket and window,
computed from the app's own price snapshots (GainersLosersState)."""

import reflex as rx

from frontend.state.gainers_losers_state import GainersLosersState as S

_CARD = dict(
    width="100%",
    padding="1.1em",
    border_radius="12px",
    border="1px solid var(--gray-a5)",
    background="var(--gray-a2)",
)


def _window_button(option: rx.Var) -> rx.Component:
    active = S.window == option["key"]
    return rx.button(
        option["label"],
        on_click=S.set_window(option["key"]),
        variant=rx.cond(active, "solid", "soft"),
        color_scheme=rx.cond(active, "indigo", "gray"),
        size="2",
        cursor="pointer",
    )


def _bucket_button(bucket: rx.Var) -> rx.Component:
    active = S.bucket == bucket
    return rx.button(
        "Top ",
        bucket,
        on_click=S.set_bucket(bucket),
        variant=rx.cond(active, "solid", "soft"),
        color_scheme=rx.cond(active, "indigo", "gray"),
        size="2",
        cursor="pointer",
    )


def _controls() -> rx.Component:
    return rx.flex(
        rx.hstack(rx.foreach(S.window_options, _window_button), spacing="2", wrap="wrap"),
        rx.hstack(rx.foreach(S.bucket_options, _bucket_button), spacing="2", wrap="wrap"),
        direction=rx.breakpoints(initial="column", md="row"),
        justify="between",
        align=rx.breakpoints(initial="start", md="center"),
        spacing="3",
        width="100%",
    )


def _header_cell(text: str, align: str = "left") -> rx.Component:
    return rx.table.column_header_cell(
        rx.text(text, size="1", weight="bold", color_scheme="gray"), text_align=align, white_space="nowrap"
    )


def _row(row: rx.Var) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row["position"], size="2", color_scheme="gray"), vertical_align="middle"),
        rx.table.cell(
            rx.link(
                rx.hstack(
                    rx.image(src=row["icon_url"], width="22px", height="22px", border_radius="50%", flex_shrink="0"),
                    rx.vstack(
                        rx.text(row["name"], size="2", weight="medium", class_name="line-clamp-1"),
                        rx.text(row["symbol"], " · #", row["rank"], size="1", color_scheme="gray"),
                        spacing="0",
                        align="start",
                        min_width="0",
                    ),
                    spacing="2",
                    align="center",
                ),
                href=row["href"],
                underline="none",
                color="var(--gray-12)",
            ),
            vertical_align="middle",
            min_width="150px",
        ),
        rx.table.cell(
            rx.vstack(
                rx.text(row["price_now"], size="2"),
                rx.text("was ", row["price_then"], size="1", color_scheme="gray"),
                rx.text(row["then_at"], size="1", color_scheme="gray"),
                spacing="0",
                align="end",
            ),
            text_align="right",
            vertical_align="middle",
            white_space="nowrap",
        ),
        rx.table.cell(
            rx.text(row["pct_change"], size="2", weight="bold", color=row["color"]),
            text_align="right",
            vertical_align="middle",
            white_space="nowrap",
        ),
        rx.table.cell(
            rx.text(row["volume_24h"], size="2", color_scheme="gray"),
            text_align="right",
            vertical_align="middle",
            white_space="nowrap",
            display=["none", "table-cell", "table-cell", "table-cell", "table-cell"],
        ),
    )


def _board(title: str, icon: str, color: str, rows, empty_text: str) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.icon(icon, size=18, color=color),
            rx.heading(title, size="4"),
            rx.badge(S.current["label"], " · Top ", S.bucket, variant="soft", color_scheme="gray", size="1"),
            spacing="2",
            align="center",
            wrap="wrap",
        ),
        rx.cond(
            rows.length() > 0,
            rx.box(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            _header_cell("#"),
                            _header_cell("Coin"),
                            _header_cell("Price", "right"),
                            _header_cell("Change", "right"),
                            rx.table.column_header_cell(
                                rx.text("Volume 24h", size="1", weight="bold", color_scheme="gray"),
                                text_align="right",
                                white_space="nowrap",
                                display=["none", "table-cell", "table-cell", "table-cell", "table-cell"],
                            ),
                        )
                    ),
                    rx.table.body(rx.foreach(rows, _row)),
                    size="1",
                    width="100%",
                ),
                overflow_x="auto",
                width="100%",
                margin_top="0.75em",
            ),
            rx.text(empty_text, size="2", color_scheme="gray", margin_top="1em"),
        ),
        **_CARD,
    )


def _collecting() -> rx.Component:
    return rx.vstack(
        rx.icon("hourglass", size=28, color="var(--amber-9)"),
        rx.heading("Collecting data for the ", S.current["label"], " board", size="4", text_align="center"),
        rx.text(
            "This board compares each coin's price now with its price about ",
            S.current["label"],
            " ago, from our own hourly price snapshots. There isn't enough history yet: ready in about ",
            S.current["days_remaining"],
            " day(s) (",
            S.current["hours_remaining"],
            " hours).",
            size="2",
            color_scheme="gray",
            text_align="center",
            max_width="560px",
        ),
        rx.cond(
            S.current["since"] != "",
            rx.text("History started ", S.current["since"], ".", size="1", color_scheme="gray"),
        ),
        spacing="3",
        align="center",
        justify="center",
        min_height="260px",
        **_CARD,
    )


def gainers_losers_content() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.heading("Top Gainers & Losers", size="6"),
            rx.text(
                "Price change measured from our own hourly price snapshots, not CoinMarketCap's % change. "
                "Coins with under $50K 24h volume are left out.",
                size="2",
                color_scheme="gray",
                text_align="center",
                max_width="640px",
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        _controls(),
        rx.cond(
            S.loading,
            rx.grid(
                rx.skeleton(height="420px", width="100%", border_radius="12px"),
                rx.skeleton(height="420px", width="100%", border_radius="12px"),
                columns=rx.breakpoints(initial="1", lg="2"),
                spacing="4",
                width="100%",
            ),
            rx.cond(
                S.error != "",
                rx.text(S.error, size="2", color_scheme="red"),
                rx.cond(
                    S.is_ready,
                    rx.grid(
                        _board("Top Gainers", "trending-up", "var(--green-11)", S.gainers, "No coin in this range gained over this window."),
                        _board("Top Losers", "trending-down", "var(--red-11)", S.losers, "No coin in this range lost over this window."),
                        columns=rx.breakpoints(initial="1", lg="2"),
                        spacing="4",
                        width="100%",
                    ),
                    _collecting(),
                ),
            ),
        ),
        spacing="5",
        width="100%",
        padding=["1em", "1em", "1.5em", "2em", "2em"],
    )
