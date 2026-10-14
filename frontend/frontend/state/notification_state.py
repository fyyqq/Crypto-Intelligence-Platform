"""State for the header bell and /notifications: the account's notification
list (app/services/notification_service.py). Every handler takes the user from
CoinState (set at login on the server, never from the browser)."""

import asyncio
import json
import sys
from pathlib import Path

import reflex as rx

from frontend.state.coin_state import CoinState, _fmt_alert_time

_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)


def _service():
    # APPENDED, not inserted first: the notifications page calls this at
    # compile time, and with the repo root first the forked server workers
    # resolve `frontend` to the outer frontend/ folder (see gainers_losers_state).
    if _ROOT not in sys.path:
        sys.path.append(_ROOT)
    from app.services import notification_service

    return notification_service


def _telegram():
    if _ROOT not in sys.path:
        sys.path.append(_ROOT)
    from app.services import telegram_notify_service

    return telegram_notify_service


POPUP_LIMIT = 6


def _row(r: dict) -> dict:
    return {
        "id": r["id"], "kind_label": r["kind_label"], "icon": r["icon"], "title": r["title"], "body": r["body"],
        "link_url": r["link_url"], "image_url": r["image_url"], "tone": r["tone"],
        "time_display": _fmt_alert_time(r["at"]), "read": r["read"],
    }


class NotificationState(rx.State):
    items: list[dict] = []
    unread: int = 0
    loading: bool = True
    # Header bell popup: the latest few notifications.
    bell_open: bool = False
    recent: list[dict] = []
    recent_loading: bool = True
    # Telegram delivery card on /notifications.
    tg_available: bool = False  # bot token configured
    tg_connected: bool = False
    tg_waiting: bool = False  # link opened, waiting for the user to press Start
    tg_link: str = ""
    tg_message: str = ""

    @rx.var
    def unread_badge(self) -> str:
        return "9+" if self.unread > 9 else str(self.unread)

    @rx.var
    def has_unread(self) -> bool:
        return self.unread > 0

    async def _user_id(self) -> int:
        coin = await self.get_state(CoinState)
        return coin.user_id if coin.is_logged_in else 0

    @rx.event
    async def refresh_unread(self):
        """Bell badge: run on page load and by the alert watch (after a
        trigger and every minute, so notifications created elsewhere show up)."""
        uid = await self._user_id()
        self.unread = await asyncio.to_thread(_service().unread_count, uid) if uid else 0
        if self.bell_open and uid:  # keep an open popup current
            rows = await asyncio.to_thread(_service().list_for_user, uid, POPUP_LIMIT)
            self.recent = [_row(r) for r in rows]

    @rx.event
    async def page_loaded(self):
        """First thing the alert watch does on every page load: the popup
        starts closed (state outlives a full page load), badge refreshed."""
        self.bell_open = False
        await self.refresh_unread()

    @rx.event
    async def toggle_popup(self):
        if self.bell_open:
            self.bell_open = False
            return
        uid = await self._user_id()
        if not uid:
            return
        self.bell_open = True
        self.recent_loading = True
        yield  # show the popup (with its skeleton) before the query returns
        rows = await asyncio.to_thread(_service().list_for_user, uid, POPUP_LIMIT)
        self.recent = [_row(r) for r in rows]
        self.recent_loading = False

    @rx.event
    def close_popup(self):
        self.bell_open = False

    @rx.event
    async def load_notifications(self):
        """/notifications on_load."""
        self.loading = True
        self.bell_open = False
        uid = await self._user_id()
        if not uid:
            self.items, self.unread, self.loading = [], 0, False
            return
        svc = _service()
        rows = await asyncio.to_thread(svc.list_for_user, uid)
        self.items = [_row(r) for r in rows]
        self.unread = sum(1 for r in rows if not r["read"])
        self.loading = False
        tg = _telegram()
        self.tg_available = tg.configured()
        self.tg_connected = await asyncio.to_thread(tg.chat_id_for, uid) is not None
        self.tg_waiting, self.tg_link, self.tg_message = False, "", ""

    @rx.event
    async def connect_telegram(self):
        """Makes a one-time link, opens the bot, then watches for Start."""
        uid = await self._user_id()
        if not uid:
            return
        try:
            _code, link = await asyncio.to_thread(_telegram().start_link, uid)
        except Exception:  # noqa: BLE001
            self.tg_message = "Could not reach Telegram. Try again in a moment."
            return
        self.tg_link, self.tg_waiting, self.tg_message = link, True, ""
        yield rx.call_script(f"window.open({json.dumps(link)}, '_blank')")
        yield NotificationState.watch_telegram_link

    @rx.event(background=True)
    async def watch_telegram_link(self):
        """Checks the bot every 3s (up to 2 minutes) for the Start press."""
        for _ in range(40):
            async with self:
                if not self.tg_waiting:
                    return
                uid = await self._user_id()
            if not uid:
                return
            try:
                done = await asyncio.to_thread(_telegram().poll_link, uid)
            except Exception:  # noqa: BLE001
                done = False
            if done:
                async with self:
                    self.tg_connected, self.tg_waiting, self.tg_link = True, False, ""
                    self.tg_message = "Connected. A confirmation was sent to your Telegram."
                return
            await asyncio.sleep(3)
        async with self:
            if self.tg_waiting:
                self.tg_waiting = False
                self.tg_message = "Timed out waiting for Start. Press Connect again."

    @rx.event
    def cancel_telegram_link(self):
        self.tg_waiting, self.tg_link = False, ""

    @rx.event
    async def disconnect_telegram(self):
        uid = await self._user_id()
        if not uid:
            return
        await asyncio.to_thread(_telegram().disconnect, uid)
        self.tg_connected, self.tg_message = False, "Telegram disconnected."

    @rx.event
    async def test_telegram(self):
        uid = await self._user_id()
        if not uid:
            return
        try:
            ok = await asyncio.to_thread(_telegram().send_test, uid)
            self.tg_message = "Test message sent." if ok else "Not connected."
        except Exception:  # noqa: BLE001
            self.tg_message = "Sending failed. Open the bot in Telegram and press Start again."

    @rx.event
    async def mark_read(self, notification_id: int):
        uid = await self._user_id()
        if not uid:
            return
        await asyncio.to_thread(_service().mark_read, uid, notification_id)
        self.items = [{**i, "read": True} if i["id"] == notification_id else i for i in self.items]
        self.recent = [{**i, "read": True} if i["id"] == notification_id else i for i in self.recent]
        self.unread = await asyncio.to_thread(_service().unread_count, uid)

    @rx.event
    async def open_item(self, notification_id: int):
        """A row with a link was clicked: mark it read, then go. The link is
        looked up from this account's own list (never taken from the browser),
        and only same-site paths are followed."""
        await self.mark_read(notification_id)
        item = next((i for i in [*self.items, *self.recent] if i["id"] == notification_id), None)
        url = item["link_url"] if item else ""
        if url.startswith("/") and not url.startswith("//"):
            return rx.call_script(f"window.location.assign({json.dumps(url)})")

    @rx.event
    async def mark_all_read(self):
        uid = await self._user_id()
        if not uid:
            return
        await asyncio.to_thread(_service().mark_all_read, uid)
        self.items = [{**i, "read": True} for i in self.items]
        self.recent = [{**i, "read": True} for i in self.recent]
        self.unread = 0

    @rx.event
    async def delete_one(self, notification_id: int):
        uid = await self._user_id()
        if not uid:
            return
        await asyncio.to_thread(_service().delete, uid, notification_id)
        self.items = [i for i in self.items if i["id"] != notification_id]
        self.recent = [i for i in self.recent if i["id"] != notification_id]
        self.unread = await asyncio.to_thread(_service().unread_count, uid)

    @rx.event
    async def clear_all(self):
        uid = await self._user_id()
        if not uid:
            return
        await asyncio.to_thread(_service().clear_all, uid)
        self.items = []
        self.recent = []
        self.unread = 0
