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
    # Rank bands, not cumulative: "Top 100", then "101–200", "201–300", ...
    return rx.button(
        rx.cond(bucket == 100, "Top 100", rx.fragment(bucket - 99, "–", bucket)),
        on_click=S.set_bucket(bucket),
        variant=rx.cond(active, "solid", "soft"),
        color_scheme=rx.cond(active, "indigo", "gray"),
        size="2",
        cursor="pointer",
    )


def _calendar_button() -> rx.Component:
    """Past days: opens a date picker over the boards saved daily
    (movers_daily). The button reads the picked day, or "Live"."""
    picked = S.selected_day != ""
    return rx.popover.root(
        rx.popover.trigger(
            rx.button(
                rx.icon("calendar", size=16),
                rx.cond(picked, S.selected_day_label, "Live"),
                variant=rx.cond(picked, "solid", "soft"),
                color_scheme=rx.cond(picked, "indigo", "gray"),
                size="2",
                cursor="pointer",
                aria_label="Pick a past day",
            ),
        ),
        rx.popover.content(
            rx.vstack(
                rx.text("Show a past day's board", size="2", weight="bold"),
                rx.input(
                    type="date",
                    value=S.selected_day,
                    min=S.first_day,
                    max=S.last_day,
                    on_change=S.set_day,
                    width="100%",
                    style={"color_scheme": "light dark"},
                ),
                rx.text(
                    rx.cond(
                        S.first_day != "",
                        rx.fragment("Saved daily (UTC) since ", S.first_day_label, "."),
                        "The first daily board is saved within the hour.",
                    ),
                    size="1",
                    color_scheme="gray",
                ),
                rx.cond(
                    picked,
                    rx.popover.close(
                        rx.button("Back to live", on_click=S.show_live, variant="soft", size="1", width="100%", cursor="pointer"),
                    ),
                ),
                spacing="2",
                width="220px",
            ),
            side="bottom",
            align="start",
        ),
    )


def _controls() -> rx.Component:
    return rx.flex(
        rx.hstack(rx.foreach(S.window_options, _window_button), _calendar_button(), spacing="2", wrap="wrap"),
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
    # A coin you hold on MEXC glows (.gl-held-row, styles.css); one that is not among the board's top rows is added
    # at the end with its real #.
    return rx.table.row(
        rx.table.cell(rx.text(row["position"], size="2", color_scheme="gray"), vertical_align="middle"),
        rx.table.cell(
            rx.link(
                rx.hstack(
                    rx.image(src=row["icon_url"], width="22px", height="22px", border_radius="50%", flex_shrink="0"),
                    rx.vstack(
                        rx.hstack(
                            rx.text(row["name"], size="2", weight="medium", class_name="line-clamp-1"),
                            rx.cond(row["held"] != "", rx.badge("Holding", size="1", variant="soft", class_name="gl-held-badge")),
                            spacing="2",
                            align="center",
                            min_width="0",
                        ),
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
        class_name=rx.cond(row["held"] != "", "gl-held-row", ""),
    )


def _refresh_button() -> rx.Component:
    """Re-reads the live prices now and recomputes every board (see
    GainersLosersState.refresh). Spins while it runs; follows the theme."""
    return rx.tooltip(
        rx.icon_button(
            rx.icon("rotate-cw", size=18),
            on_click=S.refresh,
            variant="ghost",
            color_scheme="gray",
            size="2",
            cursor="pointer",
            disabled=S.refreshing,
            aria_label="Refresh prices",
            class_name=rx.cond(S.refreshing, "gl-refresh-spinning", ""),
            style={"color": "var(--gray-12)", "flex_shrink": "0"},
        ),
        content=rx.cond(S.live_at != "", "Refresh prices now · live at " + S.live_at, "Refresh prices now"),
    )


def _change_header(direction: str) -> rx.Component:
    """Change column header: click to flip the sort of this board's rows."""
    desc = S.gainers_desc if direction == "gainers" else S.losers_desc
    return rx.table.column_header_cell(
        rx.hstack(
            rx.text("Change", size="1", weight="bold", color_scheme="gray"),
            rx.cond(
                desc,
                rx.icon("arrow-down-wide-narrow", size=14, color="var(--gray-11)"),
                rx.icon("arrow-up-narrow-wide", size=14, color="var(--gray-11)"),
            ),
            spacing="1",
            align="center",
            justify="end",
        ),
        on_click=S.toggle_sort(direction),
        cursor="pointer",
        text_align="right",
        white_space="nowrap",
        title=rx.cond(desc, "Sorted largest % first. Click for smallest first.", "Sorted smallest % first. Click for largest first."),
    )


def _board(title: str, icon: str, color: str, rows, empty_text: str, direction: str) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.hstack(
                rx.icon(icon, size=18, color=color),
                rx.heading(title, size="4"),
                rx.badge(S.current["label"], " · Rank ", S.bucket - 99, "–", S.bucket, variant="soft", color_scheme="gray", size="1"),
                rx.cond(
                    S.selected_day != "",
                    rx.badge(rx.icon("calendar", size=12), S.selected_day_label, variant="soft", color_scheme="indigo", size="1"),
                ),
                spacing="2",
                align="center",
                wrap="wrap",
            ),
            _refresh_button(),
            justify="between",
            align="center",
            width="100%",
        ),
        rx.cond(
            S.day_saved_at != "",
            rx.text("Saved board, as of ", S.day_saved_at, size="1", color_scheme="gray", margin_top="0.35em"),
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
                            _change_header(direction),
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


def _day_missing() -> rx.Component:
    return rx.vstack(
        rx.icon("calendar-x", size=28, color="var(--gray-11)"),
        rx.heading("No saved ", S.current["label"], " board for ", S.selected_day_label, size="4", text_align="center"),
        rx.text(
            "Boards are saved once a day from our own price snapshots. A window is only saved once it has "
            "enough history, so try another window or day.",
            size="2",
            color_scheme="gray",
            text_align="center",
            max_width="560px",
        ),
        rx.button("Back to live", on_click=S.show_live, variant="soft", size="2", cursor="pointer"),
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
                "Price change = the live price now against the price about 24h / 7d / 1 month ago from our own hourly "
                "price snapshots, not CoinMarketCap's % change. Coins with under $50K 24h volume and stablecoins are left out.",
                size="2",
                color_scheme="gray",
                text_align="center",
                max_width="640px",
            ),
            rx.cond(
                (S.live_at != "") & (S.selected_day == ""),
                rx.hstack(
                    rx.box(class_name="gl-live-dot"),
                    rx.text("Live prices update every 30 s · last update ", S.live_at, size="1", color_scheme="gray"),
                    spacing="2",
                    align="center",
                ),
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
                        _board("Top Gainers", "trending-up", "var(--green-11)", S.gainers, "No coin in this range gained over this window.", "gainers"),
                        _board("Top Losers", "trending-down", "var(--red-11)", S.losers, "No coin in this range lost over this window.", "losers"),
                        columns=rx.breakpoints(initial="1", lg="2"),
                        spacing="4",
                        width="100%",
                    ),
                    rx.cond(S.day_missing, _day_missing(), _collecting()),
                ),
            ),
        ),
        spacing="5",
        width="100%",
        padding=["1em", "1em", "1.5em", "2em", "2em"],
    )
