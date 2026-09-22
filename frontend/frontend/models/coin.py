"""Local storage model for cached CoinMarketCap coin listings."""

from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel

from frontend.models.category import Category, CoinCategoryLink
from frontend.models.coin_contract import CoinContract


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

    categories: list[Category] = Relationship(
        back_populates="coins", link_model=CoinCategoryLink
    )
    contracts: list[CoinContract] = Relationship(back_populates="coin")
