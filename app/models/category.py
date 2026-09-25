from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Many-to-many link between coins and their narrative categories/tags.
# Populated dynamically from the CMC categories endpoint (see Rule 3: No Hardcoded Narratives).
coin_category = Table(
    "coin_category",
    Base.metadata,
    Column("coin_id", ForeignKey("coins.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    cmc_category_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    # Not unique: CMC's /categories endpoint has no slug field (we derive one from the
    # name, and different categories can derive the same value), and tag-derived
    # categories from listings/latest use the tag string itself, which is unique on its own.
    slug: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    coins: Mapped[list["Coin"]] = relationship(
        secondary=coin_category, back_populates="categories"
    )
