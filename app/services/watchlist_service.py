"""Per-account watchlist persistence. Every call is scoped by the server-side user_id
(taken from the logged-in session state, never from the browser)."""
from sqlalchemy.dialects.postgresql import insert

from app.core.database import SessionLocal
from app.models.user_watchlist import UserWatchlist


def get_watchlist_ids(user_id: int) -> list[int]:
    db = SessionLocal()
    try:
        rows = db.query(UserWatchlist.cmc_id).filter(UserWatchlist.user_id == user_id).order_by(UserWatchlist.created_at).all()
        return [r[0] for r in rows]
    finally:
        db.close()


def set_watched(user_id: int, cmc_id: int, watched: bool) -> None:
    """Idempotent add/remove of one coin for one account."""
    db = SessionLocal()
    try:
        if watched:
            db.execute(insert(UserWatchlist).values(user_id=user_id, cmc_id=cmc_id).on_conflict_do_nothing())
        else:
            db.query(UserWatchlist).filter(UserWatchlist.user_id == user_id, UserWatchlist.cmc_id == cmc_id).delete()
        db.commit()
    finally:
        db.close()
