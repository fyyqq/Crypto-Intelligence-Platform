"""State of /profile: the account's contact details and its two pictures (app/services/profile_service.py).
Everything is scoped to the logged-in account's server-side user id; the e-mail is shown, never edited."""

import asyncio
import functools
import sys

import reflex as rx

from frontend.state.coin_state import _ROOT_FOR_APP, CoinState, _login_required


def _service():
    if _ROOT_FOR_APP not in sys.path:
        sys.path.insert(0, _ROOT_FOR_APP)
    from app.services import profile_service

    return profile_service


def _logged_in_only(handler):
    """Like coin_state._login_required, for handlers that yield (that guard awaits its handler, which a generator
    cannot be): a logged-out caller is sent to /login and the handler never runs."""

    @functools.wraps(handler)
    async def wrapper(self, *args, **kwargs):
        if not (self.is_logged_in and self.user_id):
            yield rx.call_script("window.location.assign('/login')")
            return
        async for update in handler(self, *args, **kwargs):
            yield update

    return wrapper


class ProfileState(CoinState):
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    address: str = ""
    email: str = ""
    avatar_url: str = ""
    banner_url: str = ""
    profile_loaded: bool = False
    saving: bool = False
    saved: bool = False
    errors: dict[str, str] = {}
    picture_error: str = ""
    picture_busy: str = ""  # "avatar" | "banner" while one is uploading

    @rx.event
    @_login_required
    async def load_profile(self):
        """/profile on_load (after restore_session and require_login)."""
        data = await asyncio.to_thread(_service().get_profile, self.user_id)
        if data is None:
            return rx.call_script("window.location.assign('/login')")
        self.first_name, self.last_name = data["first_name"], data["last_name"]
        self.phone, self.address, self.email = data["phone"], data["address"], data["email"]
        self.avatar_url, self.banner_url = data["avatar_url"], data["banner_url"]
        self.user_avatar = data["avatar_url"]
        self.errors, self.saved, self.picture_error = {}, False, ""
        self.profile_loaded = True

    @rx.event
    def set_first_name(self, value: str):
        self.first_name, self.saved = value, False

    @rx.event
    def set_last_name(self, value: str):
        self.last_name, self.saved = value, False

    @rx.event
    def set_phone(self, value: str):
        self.phone, self.saved = value, False

    @rx.event
    def set_address(self, value: str):
        self.address, self.saved = value, False

    @rx.event
    @_logged_in_only
    async def save_profile(self):
        self.saving, self.saved = True, False
        yield
        errors = await asyncio.to_thread(
            _service().update_profile, self.user_id, self.first_name, self.last_name, self.phone, self.address
        )
        self.errors = errors
        if not errors:
            self.first_name, self.last_name = self.first_name.strip(), self.last_name.strip()
            self.phone, self.address = self.phone.strip(), self.address.strip()
            self.user_name = f"{self.first_name} {self.last_name}".strip()  # the header shows it
            self.saved = True
        self.saving = False

    async def _store_picture(self, kind: str, files: list[rx.UploadFile]) -> None:
        """Runs while picture_busy is set; the caller clears it."""
        svc = _service()
        try:
            if not files:
                raise svc.ProfileError("No file was received.")
            data = await files[0].read(svc.MAX_BYTES + 1)
            url = await asyncio.to_thread(svc.save_image, self.user_id, kind, data)
        except svc.ProfileError as exc:
            self.picture_error = str(exc)
            return
        except Exception:  # noqa: BLE001  (never show internals; the backend error log has the details)
            self.picture_error = "The picture could not be saved. Try another file."
            raise
        if kind == "avatar":
            self.avatar_url = self.user_avatar = url
        else:
            self.banner_url = url

    @rx.event
    @_logged_in_only
    async def upload_avatar(self, files: list[rx.UploadFile]):
        self.picture_error, self.picture_busy = "", "avatar"
        yield
        try:
            await self._store_picture("avatar", files)
        finally:
            self.picture_busy = ""

    @rx.event
    @_logged_in_only
    async def upload_banner(self, files: list[rx.UploadFile]):
        self.picture_error, self.picture_busy = "", "banner"
        yield
        try:
            await self._store_picture("banner", files)
        finally:
            self.picture_busy = ""
