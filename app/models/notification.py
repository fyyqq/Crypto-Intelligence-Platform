from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Notification(Base):
    """One entry in an account's notification list (the header bell and
    /notifications). Created through app/services/notification_service.py
    (`notify`), never directly, so every feature adds notifications the same
    way. `kind` says what produced it (see notification_service.KINDS) and
    `tone` picks the icon colour in the list; the title/body strings are
    stored ready to display (prices already formatted by the caller)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_url: Mapped[str | None] = mapped_column(String(300), nullable=True)  # where a click goes
    image_url: Mapped[str | None] = mapped_column(String(300), nullable=True)  # e.g. a coin icon
    tone: Mapped[str] = mapped_column(String(10), nullable=False, default="info")  # up | down | info
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)
