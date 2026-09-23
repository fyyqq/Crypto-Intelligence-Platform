"""Page footer: logo/description/social icons on the left, dummy link
columns on the right, plus a bottom copyright/legal-links row — same layout
as the header's logo lockup, reused here for brand consistency."""

import reflex as rx

# Dummy placeholder columns — no destinations wired up yet.
_FOOTER_LINK_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Product", ("Features", "Pricing", "Integrations", "Changelog")),
    ("Resources", ("Documentation", "Tutorials", "Blog", "Support")),
    ("Company", ("About", "Careers", "Contact", "Partners")),
)

# Dummy social links — no real accounts wired up yet. Lucide dropped brand/
# logo icons (twitter, instagram, youtube, etc. all 404 in this version), so
# these are generic stand-ins matching the reference design's icon shapes.
_SOCIAL_ICONS: tuple[str, ...] = ("at-sign", "camera", "play", "headphones")


def _footer_link_column(title: str, links: tuple[str, ...]) -> rx.Component:
    return rx.vstack(
        rx.text(title, size="2", weight="bold"),
        *[
            rx.link(
                label,
                href="#",
                underline="none",
                color_scheme="gray",
                size="2",
            )
            for label in links
        ],
        spacing="3",
        align="start",
    )


def _footer_social_icon(icon_name: str) -> rx.Component:
    return rx.link(
        rx.box(
            rx.icon(icon_name, size=16, color="var(--gray-11)"),
            width="32px",
            height="32px",
            border_radius="9999px",
            background="var(--gray-a3)",
            display="flex",
            align_items="center",
            justify_content="center",
        ),
        href="#",
    )


def footer() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.link(
                        rx.hstack(
                            rx.color_mode_cond(
                                light=rx.image(src="/logo_light.png", height="28px"),
                                dark=rx.image(src="/logo_dark.png", height="28px"),
                            ),
                            rx.heading("Repace", size="6", color="white"),
                            spacing="2",
                            align="center",
                        ),
                        href="/",
                        underline="none",
                    ),
                    rx.text(
                        "Tracking crypto markets in real time, mapping every asset into "
                        "dynamic narratives, with AI-powered news correlation on the way.",
                        color_scheme="gray",
                        size="2",
                        max_width="380px",
                    ),
                    rx.hstack(
                        *[_footer_social_icon(name) for name in _SOCIAL_ICONS],
                        spacing="2",
                    ),
                    spacing="4",
                    align="start",
                ),
                rx.spacer(),
                rx.hstack(
                    *[
                        _footer_link_column(title, links)
                        for title, links in _FOOTER_LINK_COLUMNS
                    ],
                    spacing="8",
                    align="start",
                ),
                width="100%",
                align="start",
                justify="between",
                wrap="wrap",
            ),
            rx.divider(),
            rx.hstack(
                rx.text(
                    "© 2026 Repace. All rights reserved.",
                    size="1",
                    color_scheme="gray",
                ),
                rx.spacer(),
                rx.hstack(
                    rx.link(
                        "Privacy Policy", href="#", underline="none", size="1", color_scheme="gray"
                    ),
                    rx.link(
                        "Terms of Service", href="#", underline="none", size="1", color_scheme="gray"
                    ),
                    rx.link(
                        "Cookie Settings", href="#", underline="none", size="1", color_scheme="gray"
                    ),
                    spacing="4",
                ),
                width="100%",
                align="center",
                wrap="wrap",
            ),
            spacing="5",
            width="100%",
        ),
        width="100%",
        padding="2.5em 2em",
        border_top="1px solid var(--gray-a5)",
    )
