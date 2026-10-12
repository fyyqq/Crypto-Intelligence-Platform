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


class NotificationState(rx.State):
    items: list[dict] = []
    unread: int = 0
    loading: bool = True

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

    @rx.event
    async def load_notifications(self):
        """/notifications on_load."""
        self.loading = True
        uid = await self._user_id()
        if not uid:
            self.items, self.unread, self.loading = [], 0, False
            return
        svc = _service()
        rows = await asyncio.to_thread(svc.list_for_user, uid)
        self.items = [
            {
                "id": r["id"], "kind_label": r["kind_label"], "icon": r["icon"], "title": r["title"], "body": r["body"],
                "link_url": r["link_url"], "image_url": r["image_url"], "tone": r["tone"],
                "time_display": _fmt_alert_time(r["at"]), "read": r["read"],
            }
            for r in rows
        ]
        self.unread = sum(1 for r in rows if not r["read"])
        self.loading = False

    @rx.event
    async def mark_read(self, notification_id: int):
        uid = await self._user_id()
        if not uid:
            return
        await asyncio.to_thread(_service().mark_read, uid, notification_id)
        self.items = [{**i, "read": True} if i["id"] == notification_id else i for i in self.items]
        self.unread = sum(1 for i in self.items if not i["read"])

    @rx.event
    async def open_item(self, notification_id: int):
        """A row with a link was clicked: mark it read, then go. The link is
        looked up from this account's own list (never taken from the browser),
        and only same-site paths are followed."""
        await self.mark_read(notification_id)
        item = next((i for i in self.items if i["id"] == notification_id), None)
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
        self.unread = 0

    @rx.event
    async def delete_one(self, notification_id: int):
        uid = await self._user_id()
        if not uid:
            return
        await asyncio.to_thread(_service().delete, uid, notification_id)
        self.items = [i for i in self.items if i["id"] != notification_id]
        self.unread = sum(1 for i in self.items if not i["read"])

    @rx.event
    async def clear_all(self):
        uid = await self._user_id()
        if not uid:
            return
        await asyncio.to_thread(_service().clear_all, uid)
        self.items = []
        self.unread = 0
