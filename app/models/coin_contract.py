from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CoinContract(Base):
    """One chain a coin's contract is deployed on, from CMC's
    /v2/cryptocurrency/info `contract_address` list. A coin with zero rows
    here is single-chain — its own name is its chain, no dropdown needed.

    is_primary marks the coin's main/native chain: CMC's own declared
    `platform` for token-type coins, or — for root assets with no single
    declared platform (BTC, ETH, BNB, stablecoins...) — whichever entry's
    `platform_symbol` equals the coin's own symbol (that chain's gas token
    IS this coin, e.g. ETH's own entry among its bridged copies elsewhere).
    See MarketDataService._upsert_contracts for the exact resolution order.
    """

    __tablename__ = "coin_contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), index=True)
    platform_name: Mapped[str] = mapped_column(String(255))
    platform_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contract_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    coin: Mapped["Coin"] = relationship(back_populates="contracts")
