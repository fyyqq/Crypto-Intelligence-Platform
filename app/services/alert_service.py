"""Per-account price alerts. Every call is scoped by the server-side user_id (taken from the
logged-in session state, never from the browser)."""
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.models.price_alert import PriceAlert


def list_active(user_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(PriceAlert)
            .filter(PriceAlert.user_id == user_id, PriceAlert.triggered_at.is_(None))
            .order_by(PriceAlert.created_at)
            .all()
        )
        return [{"id": r.id, "cmc_id": r.cmc_id, "price": r.target_price, "direction": r.direction} for r in rows]
    finally:
        db.close()


def list_history(user_id: int, limit: int = 200) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(PriceAlert)
            .filter(PriceAlert.user_id == user_id, PriceAlert.triggered_at.is_not(None))
            .order_by(PriceAlert.triggered_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "cmc_id": r.cmc_id,
                "name": r.coin_name,
                "symbol": r.symbol,
                "direction": r.direction,
                "target": r.target_price,
                "price": r.triggered_price or r.target_price,
                "at": r.triggered_at,
            }
            for r in rows
        ]
    finally:
        db.close()


def add_alert(user_id: int, cmc_id: int, coin_name: str, symbol: str, direction: str, price: float) -> int:
    db = SessionLocal()
    try:
        alert = PriceAlert(
            user_id=user_id, cmc_id=cmc_id, coin_name=coin_name[:120], symbol=symbol[:40],
            direction=direction, target_price=price,
        )
        db.add(alert)
        db.commit()
        return alert.id
    finally:
        db.close()


def delete_alert(user_id: int, alert_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(PriceAlert).filter(PriceAlert.user_id == user_id, PriceAlert.id == alert_id).delete()
        db.commit()
    finally:
        db.close()


def mark_triggered(user_id: int, alert_id: int, price: float) -> bool:
    """False when another open tab already marked it."""
    db = SessionLocal()
    try:
        n = db.query(PriceAlert).filter(
            PriceAlert.user_id == user_id, PriceAlert.id == alert_id, PriceAlert.triggered_at.is_(None)
        ).update({"triggered_at": datetime.now(timezone.utc), "triggered_price": price})
        db.commit()
        return n > 0
    finally:
        db.close()


def update_alert(user_id: int, alert_id: int, price: float, direction: str) -> None:
    """Changes an active alert's target price (and its above/below side)."""
    db = SessionLocal()
    try:
        db.query(PriceAlert).filter(
            PriceAlert.user_id == user_id, PriceAlert.id == alert_id, PriceAlert.triggered_at.is_(None)
        ).update({"target_price": price, "direction": direction})
        db.commit()
    finally:
        db.close()
