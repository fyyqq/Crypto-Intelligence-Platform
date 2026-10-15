from datetime import datetime

from sqlalchemy import DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PortfolioBalance(Base):
    """The MEXC portfolio's total balance (USD), saved every 5 minutes by the server so /portfolio can draw its
    balance chart (MEXC keeps no balance history of its own). One account per server, so no user column.
    See app/services/portfolio_history_service.py."""

    __tablename__ = "portfolio_balance_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    total_usd: Mapped[float] = mapped_column(Float, nullable=False)
