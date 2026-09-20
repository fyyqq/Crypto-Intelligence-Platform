from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.coin import Coin
from app.schemas.coin import CoinRead

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
