"""/profile: edit the account's details and pictures — banner on top, profile picture overlapping it, then a
"Personal details" form (first/last name, mobile, e-mail read-only, address). Two columns from the md breakpoint,
one column on phones. An account sidebar (25% of the width, sticky, minimizable) sits beside the page. Colours use the theme tokens so it follows light/dark mode."""

import reflex as rx

from frontend.state import ProfileState

_ACCEPT = {"image/png": [".png"], "image/jpeg": [".jpg", ".jpeg"], "image/webp": [".webp"], "image/gif": [".gif"]}
_MAX_BYTES = 5 * 1024 * 1024


def _edit_button(upload_id: str, handler, label: str) -> rx.Component:
    """A pencil button that opens the computer's file picker; the chosen picture uploads straight away."""
    return rx.upload.root(
        rx.box(rx.icon("pencil", size=15), class_name="profile-edit-btn", title=label, aria_label=label),
        id=upload_id,
        accept=_ACCEPT,
        multiple=False,
        max_files=1,
        max_size=_MAX_BYTES,
        no_drag=True,
        on_drop=handler(rx.upload_files(upload_id=upload_id)),
        padding="0",
        border="none",
        background="transparent",
        class_name="profile-upload",
    )


def _banner() -> rx.Component:
    return rx.box(
        rx.cond(
            ProfileState.banner_url != "",
            rx.image(src=ProfileState.banner_url, alt="Profile banner", class_name="profile-banner-img"),
            rx.box(class_name="profile-banner-empty"),
        ),
        rx.box(
            rx.cond(ProfileState.picture_busy == "banner", rx.spinner(size="2"), _edit_button("profile_banner_upload", ProfileState.upload_banner, "Change banner")),
            class_name="profile-banner-edit",
        ),
        class_name="profile-banner",
    )


def _avatar() -> rx.Component:
    return rx.box(
        rx.box(
            rx.cond(
                ProfileState.avatar_url != "",
                rx.image(src=ProfileState.avatar_url, alt="Profile picture", class_name="profile-avatar-img"),
                rx.icon("user", size=44, color="var(--gray-9)"),
            ),
            class_name="profile-avatar-circle",
        ),
        rx.box(
            rx.cond(ProfileState.picture_busy == "avatar", rx.spinner(size="2"), _edit_button("profile_avatar_upload", ProfileState.upload_avatar, "Change profile picture")),
            class_name="profile-avatar-edit",
        ),
        class_name="profile-avatar",
    )


def _error(key: str) -> rx.Component:
    return rx.cond(ProfileState.errors.contains(key), rx.text(ProfileState.errors[key], size="1", color="var(--red-10)"))


def _field(label: str, control: rx.Component, error_key: str | None = None, hint: str = "") -> rx.Component:
    return rx.vstack(
        rx.text(label, size="2", weight="medium", color="var(--gray-11)"),
        control,
        _error(error_key) if error_key else rx.fragment(),
        rx.text(hint, size="1", color="var(--gray-10)") if hint else rx.fragment(),
        spacing="1",
        align_items="stretch",
        width="100%",
    )


def _input(value, on_change, **kw) -> rx.Component:
    return rx.input(value=value, on_change=on_change, size="3", variant="surface", width="100%", **kw)


def _form() -> rx.Component:
    return rx.grid(
        _field("First name", _input(ProfileState.first_name, ProfileState.set_first_name, max_length=40, placeholder="First name"), "first_name"),
        _field("Last name", _input(ProfileState.last_name, ProfileState.set_last_name, max_length=40, placeholder="Last name"), "last_name"),
        _field("Mobile number", _input(ProfileState.phone, ProfileState.set_phone, max_length=32, placeholder="+60 12 345 6789", input_mode="tel"), "phone"),
        _field(
            "Email ID",
            rx.input(value=ProfileState.email, disabled=True, size="3", variant="surface", width="100%", read_only=True),
            hint="This is your login email and can't be changed here.",
        ),
        rx.box(
            _field(
                "Address",
                rx.text_area(
                    value=ProfileState.address,
                    on_change=ProfileState.set_address,
                    placeholder="Street, city, country",
                    max_length=300,
                    rows="3",
                    size="3",
                    variant="surface",
                    width="100%",
                ),
                "address",
            ),
            grid_column=["auto", "auto", "1 / -1", "1 / -1", "1 / -1"],
        ),
        columns=rx.breakpoints(initial="1", sm="2"),
        gap="1.25em",
        width="100%",
    )


# (label, icon, view, path). The two views live in one page: the sidebar swaps the content and the address bar in
# the browser (assets/profile_sidebar.js), so the sidebar never reloads. Each path is also a real route (frontend.py)
# so a refresh or a shared link opens the same view.
_SIDE_LINKS = [
    ("Portfolio", "wallet", "portfolio", "/portfolio"),
    ("Profile", "user", "edit", "/profile/edit-profile"),
]


def _sidebar() -> rx.Component:
    """Account sidebar: 25% of the width next to the page (sticky, never over it). The chevron button at the bottom
    shrinks it to an icon strip and back (assets/profile_sidebar.js flips `profile-collapsed` on .profile-layout and
    remembers the choice); the account (avatar, name, e-mail) sits under the links."""
    return rx.el.aside(
        rx.box(
            rx.el.nav(
                *[
                    rx.link(
                        rx.icon(icon, size=18, flex_shrink="0"),
                        rx.text(label, size="2", class_name="profile-side-label"),
                        href=path,
                        underline="none",
                        title=label,
                        class_name="profile-side-link",
                        custom_attrs={"data-view": view},
                    )
                    for label, icon, view, path in _SIDE_LINKS
                ],
                class_name="profile-side-nav",
            ),
            rx.box(
                rx.box(
                    rx.cond(
                        ProfileState.avatar_url != "",
                        rx.image(src=ProfileState.avatar_url, alt="", class_name="profile-side-avatar"),
                        rx.box(rx.icon("user", size=18, color="var(--gray-10)"), class_name="profile-side-avatar profile-side-avatar-empty"),
                    ),
                    rx.box(
                        rx.text(rx.cond(ProfileState.user_name != "", ProfileState.user_name, "Your account"), size="2", weight="bold", class_name="profile-side-name"),
                        rx.text(ProfileState.email, size="1", color="var(--gray-10)", class_name="profile-side-name"),
                        class_name="profile-side-who profile-side-label",
                    ),
                    class_name="profile-side-user",
                ),
                rx.el.button(
                    rx.icon("chevron-left", size=18, class_name="profile-side-icon-close"),
                    rx.icon("chevron-right", size=18, class_name="profile-side-icon-open"),
                    type="button",
                    title="Minimize / open the sidebar",
                    aria_label="Minimize or open the sidebar",
                    class_name="profile-sidebar-toggle",
                ),
                class_name="profile-side-top",
            ),
            class_name="profile-sidebar-inner",
        ),
        class_name="profile-sidebar",
    )


def _portfolio_view() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.heading("Portfolio", size="7"),
            rx.text("Coming soon", size="3", color_scheme="gray"),
            spacing="2",
            align="center",
        ),
        min_height="60vh",
        width="100%",
        class_name="profile-main profile-view-portfolio",
    )


def profile_content(view: str = "portfolio") -> rx.Component:
    """`view` is the one shown first: "portfolio" (/portfolio) or "edit" (/profile/edit-profile)."""
    return rx.box(_sidebar(), _portfolio_view(), _profile_main(), class_name="profile-layout", custom_attrs={"data-view": view})


def _profile_main() -> rx.Component:
    return rx.box(
        _banner(),
        rx.box(
            rx.flex(
                _avatar(),
                rx.vstack(
                    rx.heading(
                        rx.cond(ProfileState.user_name != "", ProfileState.user_name, "Your profile"),
                        size="5",
                        class_name="profile-name",
                    ),
                    rx.text(ProfileState.email, size="2", color="var(--gray-10)", class_name="profile-email"),
                    spacing="1",
                    align_items="start",
                    min_width="0",
                    flex="1",
                ),
                rx.button(
                    "Save changes",
                    on_click=ProfileState.save_profile,
                    loading=ProfileState.saving,
                    variant="outline",
                    radius="full",
                    size="3",
                    cursor="pointer",
                    class_name="profile-save",
                ),
                direction=rx.breakpoints(initial="column", sm="row"),
                align=rx.breakpoints(initial="start", sm="end"),
                gap="1em",
                width="100%",
            ),
            rx.cond(
                ProfileState.picture_error != "",
                rx.callout(ProfileState.picture_error, icon="triangle_alert", color_scheme="red", size="1", margin_top="1em"),
            ),
            rx.cond(
                ProfileState.saved,
                rx.callout("Your profile was saved.", icon="check", color_scheme="green", size="1", margin_top="1em"),
            ),
            rx.cond(
                ProfileState.errors.contains("form"),
                rx.callout(ProfileState.errors["form"], icon="triangle_alert", color_scheme="red", size="1", margin_top="1em"),
            ),
            rx.heading("Personal details", size="4", color="var(--gray-10)", weight="medium", margin_top="2em"),
            rx.divider(margin_y="0.75em"),
            rx.cond(
                ProfileState.profile_loaded,
                _form(),
                rx.grid(*[rx.skeleton(height="64px", border_radius="8px") for _ in range(4)], columns=rx.breakpoints(initial="1", sm="2"), gap="1.25em", width="100%"),
            ),
            class_name="profile-body",
        ),
        class_name="profile-page profile-main profile-view-edit",
    )
