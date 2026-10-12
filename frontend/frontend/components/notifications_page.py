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
