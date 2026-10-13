"""Per-account price alerts. Every call is scoped by the server-side user_id (taken from the
logged-in session state, never from the browser)."""
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.models.price_alert import PriceAlert
from app.services import notification_service


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


def mark_triggered(
    user_id: int, alert_id: int, price: float, target_display: str | None = None, price_display: str | None = None
) -> bool:
    """False when another open tab already marked it. Marking it also adds the
    account's "price alert" notification, in the same transaction, so a
    triggered alert always shows up in the bell/notification list exactly once.
    The caller passes the prices already formatted (the frontend's _fmt_usd);
    plain numbers are the fallback."""
    db = SessionLocal()
    try:
        n = db.query(PriceAlert).filter(
            PriceAlert.user_id == user_id, PriceAlert.id == alert_id, PriceAlert.triggered_at.is_(None)
        ).update({"triggered_at": datetime.now(timezone.utc), "triggered_price": price})
        payload = None
        if n > 0:
            alert = db.query(PriceAlert).filter(PriceAlert.id == alert_id).one()
            above = alert.direction == "above"
            target_text = target_display or f"${alert.target_price:g}"
            price_text = price_display or f"${price:g}"
            payload = {
                "kind": "price_alert",
                "title": f"{alert.symbol} {'rose above' if above else 'fell below'} {target_text}",
                "body": f"{alert.coin_name} ({alert.symbol}) crossed {'above' if above else 'below'} {target_text}, now at {price_text}.",
                "link_url": f"/coin/{alert.symbol.lower()}",
                "image_url": f"https://s2.coinmarketcap.com/static/img/coins/64x64/{alert.cmc_id}.png",
                "tone": "up" if above else "down",
            }
            notification_service.add_in_session(
                db, user_id, payload["kind"], title=payload["title"], body=payload["body"],
                link_url=payload["link_url"], image_url=payload["image_url"], tone=payload["tone"],
            )
        db.commit()
    finally:
        db.close()
    if payload:
        # After the commit: Telegram/WhatsApp etc. (none registered yet).
        notification_service.deliver_external(user_id, payload)
    return n > 0


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
