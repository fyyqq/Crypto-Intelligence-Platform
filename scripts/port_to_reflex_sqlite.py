"""One-time data port: copy the existing CoinMarketCap cache from the old
Postgres DB (app/, SQLAlchemy) into the new Reflex SQLite DB (frontend/,
SQLModel), so the Reflex UI has real data to verify against immediately.

This is a bridge script only — the ongoing 24h sync still writes to Postgres
via the existing app/ backend (kept as-is per human review). Run again any
time to re-sync the Reflex-side cache from the latest Postgres snapshot.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "frontend"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, selectinload  # noqa: E402
from sqlalchemy import select as sa_select  # noqa: E402
from sqlmodel import Session as SQLModelSession, select as sqlmodel_select  # noqa: E402

from app.core.database import SessionLocal as OldSessionLocal  # noqa: E402
from app.models.coin import Coin as OldCoin  # noqa: E402
from app.models.category import Category as OldCategory  # noqa: E402

from frontend.models.coin import Coin as NewCoin  # noqa: E402
from frontend.models.category import Category as NewCategory  # noqa: E402


def main() -> None:
    new_engine = create_engine(f"sqlite:///{ROOT / 'frontend' / 'reflex.db'}")

    old_db: Session = OldSessionLocal()
    try:
        old_categories = old_db.scalars(sa_select(OldCategory)).all()
        old_coins = old_db.scalars(
            sa_select(OldCoin).options(selectinload(OldCoin.categories))
        ).all()
    finally:
        old_db.close()

    with SQLModelSession(new_engine) as new_db:
        # Clear existing rows so this script is safely re-runnable.
        for coin in new_db.exec(sqlmodel_select(NewCoin)).all():
            new_db.delete(coin)
        for category in new_db.exec(sqlmodel_select(NewCategory)).all():
            new_db.delete(category)
        new_db.commit()

        category_map: dict[int, NewCategory] = {}
        for old_cat in old_categories:
            new_cat = NewCategory(
                cmc_category_id=old_cat.cmc_category_id,
                name=old_cat.name,
                slug=old_cat.slug,
                description=old_cat.description,
            )
            new_db.add(new_cat)
            category_map[old_cat.id] = new_cat
        new_db.commit()

        for old_coin in old_coins:
            new_coin = NewCoin(
                cmc_id=old_coin.cmc_id,
                symbol=old_coin.symbol,
                name=old_coin.name,
                slug=old_coin.slug,
                cmc_rank=old_coin.cmc_rank,
                price_usd=float(old_coin.price_usd) if old_coin.price_usd is not None else None,
                market_cap_usd=float(old_coin.market_cap_usd) if old_coin.market_cap_usd is not None else None,
                volume_24h_usd=float(old_coin.volume_24h_usd) if old_coin.volume_24h_usd is not None else None,
                percent_change_1h=float(old_coin.percent_change_1h) if old_coin.percent_change_1h is not None else None,
                percent_change_24h=float(old_coin.percent_change_24h) if old_coin.percent_change_24h is not None else None,
                percent_change_7d=float(old_coin.percent_change_7d) if old_coin.percent_change_7d is not None else None,
                last_synced_at=old_coin.last_synced_at,
                categories=[category_map[c.id] for c in old_coin.categories],
            )
            new_db.add(new_coin)
        new_db.commit()

    print(f"Ported {len(old_categories)} categories and {len(old_coins)} coins into frontend/reflex.db")


if __name__ == "__main__":
    main()
