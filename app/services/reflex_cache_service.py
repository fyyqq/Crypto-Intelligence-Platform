"""Mirrors the Postgres CMC cache (app/) into the Reflex SQLite cache
(frontend/reflex.db) after every successful 24h sync, so the dashboard's
7d Trend line (and its gold >100% tier) reflects fresh data automatically
instead of needing scripts/port_to_reflex_sqlite.py run by hand.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_FRONTEND_PATH = str(ROOT / "frontend")
if _FRONTEND_PATH not in sys.path:
    sys.path.insert(0, _FRONTEND_PATH)

from sqlalchemy import create_engine, select as sa_select  # noqa: E402
from sqlalchemy.orm import Session, selectinload  # noqa: E402
from sqlmodel import Session as SQLModelSession, select as sqlmodel_select  # noqa: E402

from app.core.database import SessionLocal as OldSessionLocal  # noqa: E402
from app.models.category import Category as OldCategory  # noqa: E402
from app.models.coin import Coin as OldCoin  # noqa: E402

from frontend.models.category import Category as NewCategory  # noqa: E402
from frontend.models.coin import Coin as NewCoin  # noqa: E402
from frontend.models.coin_contract import CoinContract as NewCoinContract  # noqa: E402


def sync_reflex_cache() -> tuple[int, int]:
    """Overwrites frontend/reflex.db's coin/category tables from the current
    Postgres cache. Returns (categories_ported, coins_ported).
    """
    new_engine = create_engine(f"sqlite:///{ROOT / 'frontend' / 'reflex.db'}")

    old_db: Session = OldSessionLocal()
    try:
        old_categories = old_db.scalars(sa_select(OldCategory)).all()
        old_coins = old_db.scalars(
            sa_select(OldCoin).options(
                selectinload(OldCoin.categories), selectinload(OldCoin.contracts)
            )
        ).all()
    finally:
        old_db.close()

    with SQLModelSession(new_engine) as new_db:
        for contract in new_db.exec(sqlmodel_select(NewCoinContract)).all():
            new_db.delete(contract)
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
                circulating_supply=float(old_coin.circulating_supply) if old_coin.circulating_supply is not None else None,
                total_supply=float(old_coin.total_supply) if old_coin.total_supply is not None else None,
                max_supply=float(old_coin.max_supply) if old_coin.max_supply is not None else None,
                fully_diluted_market_cap=float(old_coin.fully_diluted_market_cap) if old_coin.fully_diluted_market_cap is not None else None,
                website_url=old_coin.website_url,
                whitepaper_url=old_coin.whitepaper_url,
                twitter_url=old_coin.twitter_url,
                telegram_url=old_coin.telegram_url,
                source_code_url=old_coin.source_code_url,
                explorer_url=old_coin.explorer_url,
                reddit_url=old_coin.reddit_url,
                facebook_url=old_coin.facebook_url,
                description=old_coin.description,
                x_username=old_coin.x_username,
                cached_tweets=old_coin.cached_tweets,
                last_social_update=old_coin.last_social_update,
                last_synced_at=old_coin.last_synced_at,
                categories=[category_map[c.id] for c in old_coin.categories],
                contracts=[
                    NewCoinContract(
                        platform_name=contract.platform_name,
                        platform_symbol=contract.platform_symbol,
                        contract_address=contract.contract_address,
                        sort_order=contract.sort_order,
                        is_primary=contract.is_primary,
                    )
                    for contract in old_coin.contracts
                ],
            )
            new_db.add(new_coin)
        new_db.commit()

    return len(old_categories), len(old_coins)
