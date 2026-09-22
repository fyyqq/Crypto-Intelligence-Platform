"""Local storage model for cached CoinMarketCap coin listings."""

from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel

from frontend.models.category import Category, CoinCategoryLink


class Coin(SQLModel, table=True):
    __tablename__ = "coin"

    id: int | None = Field(default=None, primary_key=True)
    cmc_id: int = Field(index=True, unique=True)
    symbol: str = Field(index=True)
    name: str
    slug: str = Field(index=True, unique=True)
    cmc_rank: int | None = None

    price_usd: float | None = None
    market_cap_usd: float | None = None
    volume_24h_usd: float | None = None
    percent_change_1h: float | None = None
    percent_change_24h: float | None = None
    percent_change_7d: float | None = None

    last_synced_at: datetime | None = None

    # JSON-encoded list[float] of ~168 hourly price points (7d), from CoinGecko's
    # free markets endpoint — CMC's Basic tier has no historical-price data.
    # Populated by scripts/fetch_sparklines.py, not the main CMC sync.
    sparkline_7d: str | None = None

    categories: list[Category] = Relationship(
        back_populates="coins", link_model=CoinCategoryLink
    )
