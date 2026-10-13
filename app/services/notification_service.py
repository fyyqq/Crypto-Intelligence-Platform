"""Per-account notifications: the header bell's unread count and the
/notifications list. Every call is scoped by the server-side user_id (from the
logged-in session state, never from the browser).

To add a new kind of notification later: add a row to KINDS (a label and a
default lucide icon for the list), then call `notify(...)` from wherever the
event happens. Nothing else (table, bell, page) needs to change."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.notification import Notification

# kind -> (label shown in the list, lucide icon used when there is no image_url)
KINDS: dict[str, tuple[str, str]] = {
    "price_alert": ("Price alert", "bell-ring"),
    "system": ("Announcement", "megaphone"),
}
TONES = ("up", "down", "info")

# Delivery beyond the in-app list (the bell). A channel is a function
# fn(user_id, {"kind", "title", "body", "link_url", "image_url", "tone"})
# called after the notification is saved; e.g. a Telegram bot sender or a
# WhatsApp Cloud API sender, registered once at start-up with
# register_channel(). A failing channel is logged and never blocks the others
# or the saved notification. None are registered yet.
_CHANNELS: list = []


def register_channel(fn) -> None:
    if fn not in _CHANNELS:
        _CHANNELS.append(fn)


def deliver_external(user_id: int, payload: dict) -> None:
    import logging

    for fn in list(_CHANNELS):
        try:
            fn(user_id, payload)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception("notification channel %r failed", fn)
RETENTION_DAYS = 90
MAX_PER_USER = 500


def kind_label(kind: str) -> str:
    return KINDS.get(kind, (kind.replace("_", " ").capitalize(), "bell"))[0]


def kind_icon(kind: str) -> str:
    return KINDS.get(kind, ("", "bell"))[1]


def add_in_session(
    db: Session,
    user_id: int,
    kind: str,
    title: str,
    body: str | None = None,
    link_url: str | None = None,
    image_url: str | None = None,
    tone: str = "info",
) -> Notification:
    """Adds (does not commit) a notification, so a caller can create it in the
    same transaction as the event that caused it. Raises on an unknown kind or
    tone: a typo should fail loudly rather than create an unlabelled entry."""
    if kind not in KINDS:
        raise ValueError(f"Unknown notification kind '{kind}'. Add it to notification_service.KINDS first.")
    if tone not in TONES:
        raise ValueError(f"Unknown tone '{tone}'. Use one of: {', '.join(TONES)}.")
    note = Notification(
        user_id=user_id, kind=kind, title=title[:200], body=body,
        link_url=(link_url or None) and link_url[:300], image_url=(image_url or None) and image_url[:300], tone=tone,
    )
    db.add(note)
    return note


def notify(user_id: int, kind: str, title: str, body: str | None = None, link_url: str | None = None,
           image_url: str | None = None, tone: str = "info") -> int:
    """Creates one notification for an account and returns its id. Also prunes
    that account's list (older than RETENTION_DAYS, then beyond MAX_PER_USER)."""
    db = SessionLocal()
    try:
        note = add_in_session(db, user_id, kind, title, body, link_url, image_url, tone)
        db.flush()
        _prune(db, user_id)
        db.commit()
        note_id = note.id
    finally:
        db.close()
    deliver_external(user_id, {"kind": kind, "title": title, "body": body, "link_url": link_url, "image_url": image_url, "tone": tone})
    return note_id



def _prune(db: Session, user_id: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    db.query(Notification).filter(Notification.user_id == user_id, Notification.created_at < cutoff).delete(
        synchronize_session=False
    )
    overflow = (
        db.query(Notification.id).filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).offset(MAX_PER_USER).all()
    )
    if overflow:
        db.query(Notification).filter(Notification.id.in_([r[0] for r in overflow])).delete(synchronize_session=False)


def unread_count(user_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(func.count(Notification.id)).filter(
            Notification.user_id == user_id, Notification.read_at.is_(None)
        ).scalar() or 0
    finally:
        db.close()


def list_for_user(user_id: int, limit: int = 200) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Notification).filter(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()
        )
        return [
            {
                "id": r.id, "kind": r.kind, "kind_label": kind_label(r.kind), "icon": kind_icon(r.kind),
                "title": r.title, "body": r.body or "", "link_url": r.link_url or "", "image_url": r.image_url or "",
                "tone": r.tone, "at": r.created_at, "read": r.read_at is not None,
            }
            for r in rows
        ]
    finally:
        db.close()


def mark_read(user_id: int, notification_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(Notification).filter(
            Notification.user_id == user_id, Notification.id == notification_id, Notification.read_at.is_(None)
        ).update({"read_at": datetime.now(timezone.utc)})
        db.commit()
    finally:
        db.close()


def mark_all_read(user_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(Notification).filter(Notification.user_id == user_id, Notification.read_at.is_(None)).update(
            {"read_at": datetime.now(timezone.utc)}
        )
        db.commit()
    finally:
        db.close()


def delete(user_id: int, notification_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(Notification).filter(Notification.user_id == user_id, Notification.id == notification_id).delete()
        db.commit()
    finally:
        db.close()


def clear_all(user_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(Notification).filter(Notification.user_id == user_id).delete()
        db.commit()
    finally:
        db.close()
