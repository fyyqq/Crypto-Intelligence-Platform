"""Local storage models for cached CoinMarketCap narrative categories/tags.

Uses SQLModel directly (Reflex's `rx.Model` is deprecated as of 0.9.2) against
the SQLite DB configured via `db_url` in rxconfig.py.
"""

from sqlmodel import Field, Relationship, SQLModel


class CoinCategoryLink(SQLModel, table=True):
    __tablename__ = "coin_category"

    coin_id: int | None = Field(default=None, foreign_key="coin.id", primary_key=True)
    category_id: int | None = Field(
        default=None, foreign_key="category.id", primary_key=True
    )


class Category(SQLModel, table=True):
    __tablename__ = "category"

    id: int | None = Field(default=None, primary_key=True)
    cmc_category_id: str = Field(index=True, unique=True)
    name: str = Field(index=True)
    slug: str = Field(index=True)
    description: str | None = None

    coins: list["Coin"] = Relationship(
        back_populates="categories", link_model=CoinCategoryLink
    )
