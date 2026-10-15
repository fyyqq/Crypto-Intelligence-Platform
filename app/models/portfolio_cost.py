from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PortfolioCost(Base):
    """An average buy price typed in by hand on /portfolio for one coin of the MEXC portfolio (e.g. coins bought
    before the API's one-month trade history, or deposited from elsewhere). Wins over the price worked out from
    the trade history until it is cleared. See app/services/mexc_service.py."""

    __tablename__ = "portfolio_costs"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # users.id
    asset: Mapped[str] = mapped_column(String(30), primary_key=True)  # MEXC asset code, e.g. "SUI"
    avg_price: Mapped[float] = mapped_column(Float, nullable=False)  # USD(T) per coin
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
