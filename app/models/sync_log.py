import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SyncType(str, enum.Enum):
    LISTINGS = "listings"
    CATEGORIES = "categories"


class SyncStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"


class SyncLog(Base):
    """Tracks each 24H sync run so the scheduler can enforce the once-per-24h cost-control rule."""

    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_type: Mapped[SyncType] = mapped_column(Enum(SyncType))
    status: Mapped[SyncStatus] = mapped_column(Enum(SyncStatus), default=SyncStatus.RUNNING)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    records_synced: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
