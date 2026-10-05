"""Price history for the /gainers-losers page.

Step 1 (this file so far): every scheduled listings sync records one
price_snapshot row per coin from the CMC response it already fetched (no
extra API call). Later steps add the window config, the lookback query and
the gainers/losers ranking here.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.price_snapshot import PriceSnapshot


def record_snapshots(db: Session, payloads: list[dict], synced_at: datetime | None = None) -> int:
    """Adds one PriceSnapshot per coin in a CMC listings/quotes payload and
    commits. Insert-only: never updates or deletes an existing row. A coin
    with no usable price (missing, zero or negative) is skipped, since it
    could never be used to compute a % change. Returns the rows added.

    `synced_at` is UTC (naive, like the rest of the app); one sync shares one
    timestamp so all its rows line up."""
    synced_at = synced_at or datetime.utcnow()
    rows = []
    for payload in payloads:
        quote = (payload.get("quote") or {}).get("USD") or {}
        price = quote.get("price")
        if price is None or price <= 0:
            continue
        rows.append(
            PriceSnapshot(
                coin_id=payload["id"],
                symbol=payload.get("symbol") or "",
                price_usd=price,
                cmc_rank=payload.get("cmc_rank"),
                volume_24h=quote.get("volume_24h"),
                synced_at=synced_at,
            )
        )
    db.add_all(rows)
    db.commit()
    return len(rows)
