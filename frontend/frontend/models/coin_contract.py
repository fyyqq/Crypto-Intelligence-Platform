"""Local storage model for a coin's cross-chain contract deployments, mirrored
from the app/ backend's coin_contracts table (itself sourced from CMC's
/v2/cryptocurrency/info). Native coins (BTC, ETH, SOL...) have no rows here.
"""

from sqlmodel import Field, Relationship, SQLModel


class CoinContract(SQLModel, table=True):
    __tablename__ = "coin_contract"

    id: int | None = Field(default=None, primary_key=True)
    coin_id: int = Field(foreign_key="coin.id", index=True)
    platform_name: str
    platform_symbol: str | None = None
    contract_address: str | None = None
    sort_order: int = 0
    is_primary: bool = False

    coin: "Coin" = Relationship(back_populates="contracts")
