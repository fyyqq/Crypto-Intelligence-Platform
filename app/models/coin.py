from datetime import datetime

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.category import coin_category


class Coin(Base):
    __tablename__ = "coins"

    id: Mapped[int] = mapped_column(primary_key=True)
    cmc_id: Mapped[int] = mapped_column(unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    cmc_rank: Mapped[int | None] = mapped_column(nullable=True)

    price_usd: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    market_cap_usd: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    volume_24h_usd: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    percent_change_1h: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    percent_change_24h: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    percent_change_7d: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    categories: Mapped[list["Category"]] = relationship(
        secondary=coin_category, back_populates="coins"
    )
