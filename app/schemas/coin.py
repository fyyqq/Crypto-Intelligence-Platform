from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.category import CategoryRead


class CoinRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cmc_id: int
    symbol: str
    name: str
    slug: str
    cmc_rank: int | None = None
    price_usd: float | None = None
    market_cap_usd: float | None = None
    volume_24h_usd: float | None = None
    percent_change_24h: float | None = None
    last_synced_at: datetime | None = None
    categories: list[CategoryRead] = []
