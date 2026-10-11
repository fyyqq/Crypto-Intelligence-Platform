from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MoversDaily(Base):
    """One coin's % change for one window on one UTC day: the saved
    /gainers-losers board, so past days can be looked up from the page's
    calendar after the price snapshots behind them are pruned.

    Written by price_snapshot_service.record_daily_movers after each hourly
    sync: the current day's rows are replaced each time, so once a day is
    over its rows are that day's last (closing) board. Holds every
    qualifying top-500 coin (not just the 30 shown), so any rank band or
    direction can be cut from it with rank_movers. Kept indefinitely."""

    __tablename__ = "movers_daily"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date)
    window: Mapped[str] = mapped_column(String(8))
    coin_id: Mapped[int] = mapped_column()
    symbol: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    cmc_rank: Mapped[int] = mapped_column()
    price_now: Mapped[float] = mapped_column(Numeric(38, 18))
    price_then: Mapped[float] = mapped_column(Numeric(38, 18))
    pct_change: Mapped[float] = mapped_column(Float)
    volume_24h: Mapped[float] = mapped_column(Numeric(24, 2))
    # UTC, naive: the two snapshot times the change was computed between.
    then_at: Mapped[datetime] = mapped_column(DateTime)
    now_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("day", "window", "coin_id", name="uq_movers_daily_day_window_coin"),
        Index("ix_movers_daily_day_window", "day", "window"),
    )
