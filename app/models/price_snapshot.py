from datetime import datetime

from sqlalchemy import DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PriceSnapshot(Base):
    """One coin's price at one sync, kept as history for the /gainers-losers
    page (app/services/price_snapshot_service.py). Insert-only: every
    scheduled listings sync adds a row per coin and old rows are never
    updated, only deleted once they pass the retention window.

    coin_id is the coin's CMC id (the same id `coins.cmc_id` and the rest of
    the app use), not `coins.id`, and has no foreign key so history survives
    any change to the coins table. price_usd keeps 18 decimals because the
    value comes straight from the CMC response: `coins.price_usd` stores only
    8, which would round micro-cap prices to zero and break % change."""

    __tablename__ = "price_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    coin_id: Mapped[int] = mapped_column(index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    price_usd: Mapped[float] = mapped_column(Numeric(38, 18))
    cmc_rank: Mapped[int | None] = mapped_column(nullable=True)
    volume_24h: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    # Added 2026-10-05 for the coin page's 24h market-cap change; rows from
    # before that have NULL here.
    market_cap: Mapped[float | None] = mapped_column(Numeric(36, 2), nullable=True)
    # UTC, naive (same convention as every other timestamp in this app).
    synced_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    __table_args__ = (Index("ix_price_snapshot_coin_synced", "coin_id", "synced_at"),)
