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

# Real platform links (still dummy hrefs — no real accounts wired up yet).
# Lucide dropped every brand/logo icon except "x" (instagram/youtube/
# linkedin/github all 404 in this version — verified against
# reflex.components.lucide.icon.LUCIDE_ICON_LIST), so those four render from
# raw SVG path data below instead of rx.icon.
_SOCIAL_LINKS: tuple[tuple[str, str], ...] = (
    ("instagram", "#instagram"),
    ("x", "#x"),
    ("youtube", "#youtube"),
    ("linkedin", "#linkedin"),
    ("github", "#github"),
)

# Simple Icons' (CC0) path data for each brand mark, 24x24 viewBox.
_BRAND_ICON_PATHS: dict[str, str] = {
    "instagram": (
        "M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919."
        "058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-"
        "1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-"
        "4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-"
        "4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 "
        "1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947."
        "072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 "
        "3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 "
        "1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-"
        "2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-"
        ".072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-"
        "4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 "
        "6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-"
        "6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 "
        "4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s."
        "645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-"
        "1.44z"
    ),
    "youtube": (
        "M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 "
        "12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 "
        "12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 "
        "9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-"
        "2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L"
        "15.818 12l-6.273 3.568z"
    ),
    "linkedin": (
        "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 "
        "0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 "
        "1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 "
        "7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 "
        "1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 "
        "13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 "
        "1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 "
        "22.271V1.729C24 .774 23.2 0 22.222 0h.003z"
    ),
    "github": (
        "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6."
        "113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-"
        "4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729."
        "084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 "
        "3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-"
        "5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 "
        "1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 "
        ".405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176."
        "765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 "
        "1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20."
        "565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"
    ),
}


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
        # Centered below 768px (mobile), left-aligned from iPad-portrait up
        # — matches the outer link-columns row's own mobile-centering below.
        align=rx.breakpoints(initial="center", sm="start"),
    )


def _footer_social_icon(name: str, href: str) -> rx.Component:
    icon = (
        rx.icon("x", size=16, color="var(--gray-11)")
        if name == "x"
        else rx.el.svg(
            rx.el.path(d=_BRAND_ICON_PATHS[name]),
            width="16",
            height="16",
            view_box="0 0 24 24",
            fill="var(--gray-11)",
        )
    )
    return rx.link(
        rx.box(
            icon,
            width="32px",
            height="32px",
            border_radius="9999px",
            background="var(--gray-a3)",
            display="flex",
            align_items="center",
            justify_content="center",
        ),
        href=href,
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
                            # Same light/dark flip as the header's heading
                            # (frontend.py::_header_bar) — white on the
                            # footer's dark-mode background, black on light.
                            rx.heading(
                                "Repace",
                                size="6",
                                color=rx.color_mode_cond(light="black", dark="white"),
                            ),
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
                        # Centered text below 768px, matching the block's
                        # own mobile-centering below.
                        text_align=["center", "center", "left", "left", "left"],
                    ),
                    rx.hstack(
                        *[_footer_social_icon(name, href) for name, href in _SOCIAL_LINKS],
                        spacing="2",
                        justify=rx.breakpoints(initial="center", sm="start"),
                        width="100%",
                    ),
                    spacing="4",
                    # Centered below 768px (mobile) — left-aligned (the
                    # original design) from iPad-portrait up, where there's
                    # room for the left/right two-block layout below.
                    align=rx.breakpoints(initial="center", sm="start"),
                    width=["100%", "100%", "auto", "auto", "auto"],
                ),
                rx.hstack(
                    *[
                        _footer_link_column(title, links)
                        for title, links in _FOOTER_LINK_COLUMNS
                    ],
                    # named "sm" = 768px (matches the 768px used elsewhere
                    # via plain-list position 2) — named "md" is 992px.
                    spacing=rx.breakpoints(initial="5", sm="8"),
                    align="start",
                    justify=rx.breakpoints(initial="center", sm="start"),
                    wrap="wrap",
                    width=["100%", "100%", "auto", "auto", "auto"],
                ),
                width="100%",
                align=rx.breakpoints(initial="center", sm="start"),
                justify=rx.breakpoints(initial="center", sm="between"),
                wrap="wrap",
                style={"row-gap": "2em"},
            ),
            rx.divider(),
            rx.hstack(
                rx.text(
                    "© 2026 Repace. All rights reserved.",
                    size="1",
                    color_scheme="gray",
                ),
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
                    wrap="wrap",
                    justify=rx.breakpoints(initial="center", sm="start"),
                ),
                width="100%",
                align="center",
                justify=rx.breakpoints(initial="center", sm="between"),
                wrap="wrap",
                style={"row-gap": "0.5em"},
            ),
            spacing="5",
            width="100%",
        ),
        width="100%",
        padding=["1.5em 1em", "1.5em 1.5em", "2em 1.5em", "2.5em 2em", "2.5em 2em"],
        border_top="1px solid var(--gray-a5)",
    )
