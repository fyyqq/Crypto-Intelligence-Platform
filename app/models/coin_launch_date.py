from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CoinLaunchDate(Base):
    """When a coin started (its age on the coin page). Its own table keyed by CMC id so no coin sync overwrites it.
    launch_date NULL = looked up and not found (checked_at says when; looked up again after a few days).
    source: "coingecko" (genesis date), "cmc_launched", "dex" (its oldest DEX pair), "cmc_added" (when CMC listed it).
    See app/services/coin_age_service.py."""

    __tablename__ = "coin_launch_dates"

    cmc_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
