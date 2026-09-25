from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.coin import Coin
from app.schemas.coin import CoinRead
from app.services.social_service import SocialService

router = APIRouter(prefix="/coins", tags=["coins"])


@router.get("", response_model=list[CoinRead])
def list_coins(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[Coin]:
    stmt = select(Coin).order_by(Coin.cmc_rank).offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/{coin_id}", response_model=CoinRead)
def get_coin(coin_id: int, db: Session = Depends(get_db)) -> Coin:
    coin = db.get(Coin, coin_id)
    if coin is None:
        raise HTTPException(status_code=404, detail="Coin not found")
    return coin


@router.get("/{coin_id}/social", response_model=list[dict])
def get_coin_social(coin_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """Returns this coin's cached top-10 X posts, transparently refreshing
    from the scraper API first if the cache is stale (see SocialService) —
    the Reflex frontend doesn't call this directly (it cross-imports
    SocialService the same way it does MarketDataService, see CoinState.
    refresh_social_posts), but it's exposed here too for direct API
    consumers and for testing the caching behavior independent of the UI.
    """
    coin = db.get(Coin, coin_id)
    if coin is None:
        raise HTTPException(status_code=404, detail="Coin not found")
    return SocialService(db).get_tweets(coin)
