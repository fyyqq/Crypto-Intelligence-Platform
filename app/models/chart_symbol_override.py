from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChartSymbolOverride(Base):
    """A coin's TradingView chart symbol chosen by hand on its coin page (the
    red report icon next to "<Coin> Live Chart"), e.g. "KCEX:CYBERLEEKUSDT".
    Wins over the automatic pick (cached CEX pairs, then TradingView search)
    for that coin until reset. Its own table, keyed by CMC id, so no coin
    sync ever overwrites it. See app/services/chart_override_service.py."""

    __tablename__ = "chart_symbol_overrides"

    cmc_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # users.id
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
