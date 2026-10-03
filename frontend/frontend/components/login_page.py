"""Dummy login and signup pages (design only — the forms aren't connected to any backend yet)."""
import asyncio
import os
import sys
from pathlib import Path

import reflex as rx

from frontend.state import CoinState

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Public reCAPTCHA v3 site key (safe to expose); the secret key stays backend-only.
try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except Exception:
    pass
_RECAPTCHA_ENABLED = os.getenv("RECAPTCHA_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
_RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY", "")

_GOOGLE_SVG = (
    '<svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">'
    '<path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z"/>'
    '<path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.4-4.1 7-10.1 7-17.6z"/>'
    '<path fill="#FBBC05" d="M10.5 28.7c-.5-1.4-.8-3-.8-4.7s.3-3.2.8-4.7l-7.9-6.1C.9 16.4 0 20.1 0 24s.9 7.6 2.6 10.8l7.9-6.1z"/>'
    '<path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.6-5.9c-2.1 1.4-4.9 2.3-8.3 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z"/>'
    "</svg>"
)

_INPUT_STYLE = {
    "width": "100%",
    "padding": "0.85em 1em",
    "border_radius": "8px",
    "border": "1px solid rgba(255,255,255,0.12)",
    "background": "rgba(255,255,255,0.05)",
    "color": "#fff",
    "font_size": "14px",
    "outline": "none",
}


class LoginState(rx.State):
    # One flag per password field so each eye only reveals its own field.
    show_password: bool = False
    show_repeat_password: bool = False

    @rx.event
    def reset_visibility(self):
        # State survives full page loads, so a field left on "show" would come back as plain text.
        self.show_password = False
        self.show_repeat_password = False

    @rx.event
    def toggle_password(self):
        self.show_password = not self.show_password

    @rx.event
    def toggle_repeat_password(self):
        self.show_repeat_password = not self.show_repeat_password


class AuthState(CoinState):
    """Log in / sign up handlers. Passwords only ever pass through the submit handler —
    they are never stored in state. Validation runs again on the server."""

    auth_error: str = ""
    auth_loading: bool = False
    _last_submit: float = 0.0

    @rx.event
    def clear_auth_error(self):
        self.auth_error = ""

    def _throttled(self) -> bool:
        import time

        now = time.monotonic()
        if now - self._last_submit < 1.5:
            return True
        self._last_submit = now
        return False

    async def _run(self, fn, *args):
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from app.services import auth_service

        return await asyncio.to_thread(getattr(auth_service, fn), *args)

    def _fail(self, message: str):
        self.auth_error = message
        self.auth_loading = False
        # reCAPTCHA tokens are single-use: recaptcha_init.js fetches a fresh one after every submit.
        return None

    async def _succeed(self, result, remember: bool = False):
        self.is_logged_in = True
        self.user_id = result.user_id
        self.user_name = result.user_name
        self.user_email = result.user_email
        self.auth_error = ""
        self.auth_loading = False
        # Load this account's saved watchlist (replaces anything starred while logged out).
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from app.services import watchlist_service

        self.watchlist_ids = await asyncio.to_thread(watchlist_service.get_watchlist_ids, result.user_id)
        await self._load_user_alerts()
        # Only when "Remember me" was ticked: the cookie lets a later visit (even a new tab)
        # restore the login. Otherwise the login lives only in this tab's session.
        self.session_token = await self._run("create_session", result.user_id) if remember else ""
        return rx.call_script("window.location.assign('/')")

    @rx.event
    async def submit_login(self, form_data: dict):
        if self._throttled():
            return
        self.auth_loading = True
        self.auth_error = ""
        yield
        email = str(form_data.get("email", ""))
        password = str(form_data.get("password", ""))
        if _RECAPTCHA_ENABLED:
            token = str(form_data.get("g-recaptcha-response", ""))
            if not token:
                yield self._fail("Security check not ready yet. Please try again in a moment.")
                return
            if not await self._run("verify_recaptcha", token, "login"):
                yield self._fail("Security check failed. Please try again.")
                return
        result = await self._run("login_user", email, password)
        yield (await self._succeed(result, bool(form_data.get("remember")))) if result.ok else self._fail(result.error)

    @rx.event
    async def submit_signup(self, form_data: dict):
        if self._throttled():
            return
        self.auth_loading = True
        self.auth_error = ""
        yield
        if not form_data.get("terms"):
            yield self._fail("You must agree to the Terms & Conditions.")
            return
        if _RECAPTCHA_ENABLED:
            token = str(form_data.get("g-recaptcha-response", ""))
            if not token:
                yield self._fail("Security check not ready yet. Please try again in a moment.")
                return
            if not await self._run("verify_recaptcha", token, "signup"):
                yield self._fail("Security check failed. Please try again.")
                return
        result = await self._run(
            "register_user",
            str(form_data.get("full_name", "")),
            str(form_data.get("email", "")),
            str(form_data.get("password", "")),
            str(form_data.get("repeat_password", "")),
        )
        yield (await self._succeed(result)) if result.ok else self._fail(result.error)


def _left_panel() -> rx.Component:
    return rx.box(
        rx.box(
            rx.hstack(
                rx.image(src="/floating_logo.png", width="28px", height="28px"),
                rx.text("Repace", size="5", weight="bold", color="#fff"),
                spacing="2",
                align="center",
            ),
            rx.link(
                rx.hstack(
                    rx.text("Back to website", size="1", color="#fff"),
                    rx.icon("arrow-right", size=12, color="#fff"),
                    spacing="2",
                    align="center",
                    padding="0.4em 0.9em",
                    border_radius="9999px",
                    background="rgba(0,0,0,0.35)",
                    backdrop_filter="blur(6px)",
                ),
                href="/",
                underline="none",
            ),
            display="flex",
            justify_content="space-between",
            align_items="center",
            padding="1.5em",
            width="100%",
        ),
        rx.box(
            rx.heading(
                "Every narrative,",
                rx.el.br(),
                "tracked in real time",
                size="6",
                color="#fff",
                text_align="center",
            ),
            width="100%",
            padding="1.5em 1.5em 2.5em",
            background="linear-gradient(to top, rgba(0,0,0,0.75), transparent)",
        ),
        display="flex",
        flex_direction="column",
        justify_content="space-between",
        min_height=rx.breakpoints(initial="220px", xs="100vh"),
        height="100%",
        background_image="url('/login_bg.jpg')",
        background_size="cover",
        background_position="center",
        overflow="hidden",
    )


def _field(placeholder: str, name: str, input_type: str = "text", max_length: int = 254, autocomplete: str = "off") -> rx.Component:
    return rx.el.input(
        placeholder=placeholder,
        name=name,
        type=input_type,
        required=True,
        max_length=max_length,
        auto_complete=autocomplete,
        style=_INPUT_STYLE,
    )


def _password_field(placeholder: str, name: str, show, toggle, autocomplete: str) -> rx.Component:
    return rx.box(
        rx.el.input(
            placeholder=placeholder,
            name=name,
            required=True,
            max_length=128,
            auto_complete=autocomplete,
            type=rx.cond(show, "text", "password"),
            style={**_INPUT_STYLE, "padding_right": "2.8em"},
        ),
        rx.box(
            rx.cond(
                show,
                rx.icon("eye-off", size=16, color="rgba(255,255,255,0.6)"),
                rx.icon("eye", size=16, color="rgba(255,255,255,0.6)"),
            ),
            on_click=toggle,
            position="absolute",
            right="1em",
            top="50%",
            transform="translateY(-50%)",
            cursor="pointer",
            display="flex",
        ),
        position="relative",
        width="100%",
    )


def _divider(label: str) -> rx.Component:
    return rx.hstack(
        rx.box(height="1px", flex="1", background="rgba(255,255,255,0.12)"),
        rx.text(label, size="1", color="rgba(255,255,255,0.5)", white_space="nowrap"),
        rx.box(height="1px", flex="1", background="rgba(255,255,255,0.12)"),
        spacing="3",
        align="center",
        width="100%",
    )


def _google_button() -> rx.Component:
    return rx.button(
        rx.html(_GOOGLE_SVG),
        "Google",
        type="button",
        size="3",
        variant="outline",
        width="100%",
        color="#fff",
        cursor="pointer",
        style={"border": "1px solid rgba(255,255,255,0.25)", "gap": "0.6em", "color": "#fff"},
    )


def _recaptcha(action: str) -> rx.Component:
    """reCAPTCHA v3 is invisible: a hidden field holds the token, which recaptcha_init.js
    keeps fresh (and refreshes after every submit). The server checks score and action."""
    if not _RECAPTCHA_ENABLED:
        return rx.fragment()
    return rx.box(
        rx.el.input(type="hidden", name="g-recaptcha-response", custom_attrs={"data-action": action, "data-sitekey": _RECAPTCHA_SITE_KEY}),
        rx.script(src=f"https://www.google.com/recaptcha/api.js?render={_RECAPTCHA_SITE_KEY}"),
        rx.script(src="/recaptcha_init.js"),
        rx.text("Protected by reCAPTCHA", size="1", color="rgba(255,255,255,0.4)"),
        width="100%",
    )


def _form_panel(mode: str) -> rx.Component:
    login = mode == "login"
    fields = (
        [
            _field("Email", "email", "email", autocomplete="email"),
            _password_field("Enter your password", "password", LoginState.show_password, LoginState.toggle_password, "current-password"),
        ]
        if login
        else [
            _field("Full name", "full_name", "text", max_length=80, autocomplete="name"),
            _field("Email", "email", "email", autocomplete="email"),
            _password_field("Password", "password", LoginState.show_password, LoginState.toggle_password, "new-password"),
            _password_field("Repeat password", "repeat_password", LoginState.show_repeat_password, LoginState.toggle_repeat_password, "new-password"),
        ]
    )
    return rx.vstack(
        rx.heading("Log in to your account" if login else "Create an account", size="6", color="#fff"),
        rx.hstack(
            rx.text("Don't have an account?" if login else "Already have an account?", size="2", color="rgba(255,255,255,0.6)"),
            rx.link("Sign up" if login else "Log in", href="/signup" if login else "/login", size="2", color="#fff"),
            spacing="2",
            wrap="wrap",
        ),
        rx.form(
            rx.vstack(
                *fields,
                rx.cond(
                    login,
                    rx.hstack(
                        rx.hstack(
                            rx.checkbox(name="remember", size="1"),
                            rx.text("Remember me", size="1", color="rgba(255,255,255,0.8)"),
                            spacing="2",
                            align="center",
                        ),
                        rx.link("Forgot password?", href="#", size="1", color="rgba(255,255,255,0.8)"),
                        justify="between",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.checkbox(name="terms", required=True, size="1"),
                        rx.text("I agree to the Terms & Conditions", size="1", color="rgba(255,255,255,0.8)"),
                        spacing="2",
                        align="center",
                    ),
                ),
                _recaptcha("login" if login else "signup"),
                rx.cond(
                    AuthState.auth_error != "",
                    rx.callout(AuthState.auth_error, icon="triangle-alert", color_scheme="red", size="1", width="100%"),
                ),
                rx.button(
                    rx.cond(AuthState.auth_loading, rx.spinner(size="2"), rx.text("Log in" if login else "Create account")),
                    type="submit",
                    size="3",
                    width="100%",
                    color_scheme="blue",
                    cursor="pointer",
                    disabled=AuthState.auth_loading,
                ),
                spacing="3",
                width="100%",
            ),
            on_submit=AuthState.submit_login if login else AuthState.submit_signup,
            reset_on_submit=False,
            # Skip the browser's generic popups: the server returns specific messages instead.
            custom_attrs={"noValidate": True},
            width="100%",
        ),
        _divider("Or log in with" if login else "Or register with"),
        _google_button(),
        spacing="4",
        align="start",
        width="100%",
        max_width="380px",
        margin="0 auto",
        justify="center",
        padding="1em 0",
    )


def _auth_page(mode: str) -> rx.Component:
    # Full-screen split: image half on the left, form half on the right (no card,
    # no popup). Only a phone narrower than 520px stacks them (image banner on top).
    return rx.box(
        rx.script(src="/chain_pills.js"),
        rx.grid(
            _left_panel(),
            rx.box(
                _form_panel(mode),
                display="flex",
                align_items="center",
                justify_content="center",
                padding="2em 1.5em",
                background="#1c1a22",
            ),
            columns=rx.breakpoints(initial="1", xs="2"),
            spacing="0",
            width="100%",
            min_height="100vh",
        ),
        width="100%",
        min_height="100vh",
        background="#0f0e14",
        class_name="login-page",
    )


def login_page() -> rx.Component:
    return _auth_page("login")


def signup_page() -> rx.Component:
    return _auth_page("signup")
