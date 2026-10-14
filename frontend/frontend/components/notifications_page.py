"""/notifications — the account's notification list (price alerts now; any new
kind added to app/services/notification_service.KINDS shows up here too)."""

import reflex as rx

from frontend.state.notification_state import NotificationState as N
from frontend.state.notification_state import _service


def _kind_icon(icon: rx.Var, tone: rx.Var) -> rx.Component:
    # Reflex needs static icon names, so one case per icon KINDS uses.
    icons = sorted({i for _, i in _service().KINDS.values()})
    return rx.match(
        icon,
        *[(name, rx.icon(name, size=18, color=_tone_color(tone))) for name in icons],
        rx.icon("bell", size=18, color=_tone_color(tone)),
    )


def _tone_color(tone: rx.Var) -> rx.Var:
    return rx.cond(tone == "up", "var(--green-9)", rx.cond(tone == "down", "var(--red-9)", "var(--accent-9)"))


def _avatar(item: rx.Var[dict]) -> rx.Component:
    return rx.cond(
        item["image_url"] != "",
        rx.image(src=item["image_url"], width="36px", height="36px", border_radius="50%", flex_shrink="0"),
        rx.center(
            _kind_icon(item["icon"], item["tone"]),
            width="36px",
            height="36px",
            border_radius="50%",
            background="var(--gray-a3)",
            flex_shrink="0",
        ),
    )


def _popup_row(item: rx.Var[dict]) -> rx.Component:
    """Compact row for the header bell's popup (same layout idea as the
    watchlist popup): small image, title, time. A real link; the click marks
    it read then goes (see NotificationState.open_item)."""
    body = rx.hstack(
        rx.box(
            width="7px",
            height="7px",
            border_radius="50%",
            background=rx.cond(item["read"], "transparent", "var(--accent-9)"),
            flex_shrink="0",
        ),
        rx.cond(
            item["image_url"] != "",
            rx.image(src=item["image_url"], width="28px", height="28px", border_radius="50%", flex_shrink="0"),
            rx.center(
                _kind_icon(item["icon"], item["tone"]),
                width="28px",
                height="28px",
                border_radius="50%",
                background="var(--gray-a3)",
                flex_shrink="0",
            ),
        ),
        rx.vstack(
            rx.text(
                item["title"],
                size="2",
                weight=rx.cond(item["read"], "medium", "bold"),
                color="var(--gray-12)",
                class_name="line-clamp-1",
            ),
            rx.text(item["time_display"], size="1", color="var(--gray-10)"),
            spacing="0",
            align="start",
            min_width="0",
            flex="1",
        ),
        spacing="2",
        align="center",
        width="100%",
    )
    row_style = dict(
        display="block",
        width="100%",
        padding="0.55em 1em",
        class_name="global-search-result-row",
        background=rx.cond(item["read"], "transparent", "var(--accent-a3)"),
    )
    return rx.cond(
        item["link_url"] != "",
        rx.link(
            body,
            href=item["link_url"],
            on_click=N.open_item(item["id"]).prevent_default,
            custom_attrs={"data-own-click": "1"},
            underline="none",
            color="inherit",
            **row_style,
        ),
        rx.box(body, on_click=N.mark_read(item["id"]), cursor="default", **row_style),
    )


def notification_popup() -> rx.Component:
    """The bell's popup: latest notifications, anchored under the bell
    (assets/styles.css `.notification-popup`). Always rendered and shown by
    display, so assets/instant_ui.js can open it instantly on click."""
    return rx.fragment(
        rx.box(
            rx.hstack(
                rx.hstack(
                    rx.icon("bell", size=16),
                    rx.text("Notifications", size="3", weight="bold"),
                    rx.cond(N.has_unread, rx.badge(N.unread, variant="soft", radius="full")),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.cond(
                        N.has_unread,
                        rx.text(
                            "Mark all read",
                            size="1",
                            color="var(--accent-11)",
                            cursor="pointer",
                            on_click=N.mark_all_read,
                            white_space="nowrap",
                        ),
                    ),
                    rx.icon("x", size=18, color="var(--gray-12)", cursor="pointer", on_click=N.close_popup),
                    spacing="3",
                    align="center",
                ),
                align="center",
                justify="between",
                width="100%",
                padding="0.85em 1em",
                border_bottom="1px solid var(--gray-a5)",
            ),
            rx.box(
                rx.cond(
                    N.recent_loading,
                    rx.vstack(
                        rx.skeleton(height="40px", width="100%", border_radius="8px"),
                        rx.skeleton(height="40px", width="100%", border_radius="8px"),
                        rx.skeleton(height="40px", width="100%", border_radius="8px"),
                        spacing="2",
                        padding="0.75em 1em",
                        width="100%",
                    ),
                    rx.cond(
                        N.recent.length() > 0,
                        rx.foreach(N.recent, _popup_row),
                        rx.center(
                            rx.text(
                                "No notifications yet. Price alerts appear here when they trigger.",
                                size="2",
                                color_scheme="gray",
                                text_align="center",
                            ),
                            padding="2em 1em",
                        ),
                    ),
                ),
                overflow_y="auto",
                flex="1",
                padding_y="0.25em",
            ),
            rx.link(
                rx.text("View all notifications", size="2", weight="medium"),
                href="/notifications",
                underline="none",
                text_align="center",
                padding="0.7em",
                border_top="1px solid var(--gray-a5)",
                display="block",
            ),
            class_name="notification-popup",
            style={"display": rx.cond(N.bell_open, "flex", "none")},
        ),
    )


def _row(item: rx.Var[dict]) -> rx.Component:
    content = rx.hstack(
        _avatar(item),
        rx.vstack(
            rx.hstack(
                rx.text(item["title"], size="3", weight=rx.cond(item["read"], "medium", "bold"), color="var(--gray-12)"),
                rx.badge(item["kind_label"], variant="soft", color_scheme="gray", size="1"),
                spacing="2",
                align="center",
                wrap="wrap",
            ),
            rx.cond(item["body"] != "", rx.text(item["body"], size="2", color="var(--gray-11)")),
            rx.text(item["time_display"], size="1", color="var(--gray-10)"),
            spacing="1",
            align="start",
            min_width="0",
            flex="1",
        ),
        spacing="3",
        align="start",
        flex="1",
        min_width="0",
    )
    return rx.hstack(
        rx.box(
            width="8px",
            height="8px",
            border_radius="50%",
            background=rx.cond(item["read"], "transparent", "var(--accent-9)"),
            flex_shrink="0",
            margin_top="0.9em",
            class_name="notification-dot",
        ),
        rx.cond(
            item["link_url"] != "",
            rx.link(
                content,
                href=item["link_url"],
                on_click=N.open_item(item["id"]).prevent_default,
                custom_attrs={"data-own-click": "1"},
                underline="none",
                color="inherit",
                flex="1",
                min_width="0",
            ),
            rx.box(content, on_click=N.mark_read(item["id"]), flex="1", min_width="0", cursor="default"),
        ),
        rx.icon_button(
            rx.icon("x", size=16),
            on_click=N.delete_one(item["id"]),
            variant="ghost",
            color_scheme="gray",
            size="1",
            cursor="pointer",
            aria_label="Delete notification",
            flex_shrink="0",
        ),
        spacing="3",
        align="start",
        width="100%",
        padding="0.85em 1em",
        border_radius="10px",
        background=rx.cond(item["read"], "var(--gray-a2)", "var(--accent-a3)"),
        border="1px solid var(--gray-a4)",
        class_name="notification-row",
    )


def _telegram_card() -> rx.Component:
    """Connect / disconnect the Telegram bot that mirrors every notification."""
    return rx.cond(
        N.tg_available,
        rx.vstack(
            rx.hstack(
                rx.icon("send", size=18, color="var(--accent-11)"),
                rx.vstack(
                    rx.text("Telegram alerts", size="3", weight="bold", color="var(--gray-12)"),
                    rx.text(
                        rx.cond(
                            N.tg_connected,
                            "Connected: triggered price alerts are also sent to your Telegram.",
                            "Get triggered price alerts as a Telegram message.",
                        ),
                        size="2",
                        color="var(--gray-11)",
                    ),
                    spacing="0",
                    align="start",
                    flex="1",
                    min_width="0",
                ),
                rx.cond(
                    N.tg_connected,
                    rx.hstack(
                        rx.button("Send test", on_click=N.test_telegram, variant="soft", size="2", cursor="pointer"),
                        rx.button(
                            "Disconnect", on_click=N.disconnect_telegram, variant="soft", color_scheme="gray",
                            size="2", cursor="pointer",
                        ),
                        spacing="2",
                        wrap="wrap",
                    ),
                    rx.button(
                        rx.cond(N.tg_waiting, "Waiting for Start...", "Connect Telegram"),
                        on_click=N.connect_telegram,
                        disabled=N.tg_waiting,
                        size="2",
                        cursor="pointer",
                    ),
                ),
                spacing="3",
                align="center",
                width="100%",
                wrap="wrap",
            ),
            rx.cond(
                N.tg_waiting,
                rx.hstack(
                    rx.text(
                        "Telegram should have opened. Press Start in the bot. If nothing opened, ",
                        rx.link("open the bot here", href=N.tg_link, is_external=True),
                        ".",
                        size="2",
                        color="var(--gray-11)",
                    ),
                    rx.button("Cancel", on_click=N.cancel_telegram_link, variant="ghost", size="1", cursor="pointer"),
                    spacing="2",
                    align="center",
                    wrap="wrap",
                ),
            ),
            rx.cond(N.tg_message != "", rx.text(N.tg_message, size="2", color="var(--gray-11)")),
            spacing="2",
            align="start",
            width="100%",
            padding="0.9em 1em",
            border_radius="10px",
            background="var(--gray-a2)",
            border="1px solid var(--gray-a4)",
        ),
    )


def notifications_content() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("bell", size=22),
            rx.heading("Notifications", size="6"),
            rx.cond(N.has_unread, rx.badge(N.unread, " new", variant="soft", radius="full")),
            rx.spacer(),
            rx.cond(
                N.items.length() > 0,
                rx.hstack(
                    rx.button(
                        rx.icon("check-check", size=16),
                        "Mark all read",
                        on_click=N.mark_all_read,
                        variant="soft",
                        color_scheme="gray",
                        size="2",
                        cursor="pointer",
                        disabled=~N.has_unread,
                    ),
                    rx.button(
                        rx.icon("trash-2", size=16),
                        "Clear all",
                        on_click=N.clear_all,
                        variant="soft",
                        color_scheme="gray",
                        size="2",
                        cursor="pointer",
                    ),
                    spacing="2",
                    wrap="wrap",
                ),
            ),
            spacing="3",
            align="center",
            width="100%",
            wrap="wrap",
        ),
        rx.cond(~N.loading, _telegram_card()),
        rx.cond(
            N.loading,
            rx.vstack(
                rx.skeleton(height="72px", width="100%", border_radius="10px"),
                rx.skeleton(height="72px", width="100%", border_radius="10px"),
                rx.skeleton(height="72px", width="100%", border_radius="10px"),
                spacing="2",
                width="100%",
            ),
            rx.cond(
                N.items.length() > 0,
                rx.vstack(rx.foreach(N.items, _row), spacing="2", width="100%"),
                rx.center(
                    rx.vstack(
                        rx.icon("bell-off", size=28, color="var(--gray-9)"),
                        rx.text("No notifications yet", weight="medium"),
                        rx.text(
                            "Price alerts you set on a coin page appear here when they trigger.",
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
        ),
        spacing="3",
        align="start",
        width="100%",
        max_width="860px",
        margin_x="auto",
    )
