"""Read-only data access for the Streamlit dashboard.

Reuses the backend's SQLAlchemy models/session directly (same DB cache the
24h sync job writes to) instead of duplicating query logic or requiring the
FastAPI server to be running just to view cached data.
"""

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Streamlit puts this file's own directory on sys.path, not the project root,
# so the backend's "app" package needs an explicit path entry to be importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.coin import Coin  # noqa: E402
from app.models.sync_log import SyncLog  # noqa: E402


def load_coins() -> pd.DataFrame:
    db = SessionLocal()
    try:
        stmt = (
            select(Coin)
            .options(selectinload(Coin.categories))
            .order_by(Coin.cmc_rank)
        )
        coins = db.scalars(stmt).all()
        rows = [
            {
                "Rank": coin.cmc_rank,
                "Name": coin.name,
                "Symbol": coin.symbol,
                "Price (USD)": coin.price_usd,
                "Market Cap (USD)": coin.market_cap_usd,
                "24h Volume (USD)": coin.volume_24h_usd,
                "24h Change (%)": coin.percent_change_24h,
                "Narratives": ", ".join(sorted(c.name for c in coin.categories)),
            }
            for coin in coins
        ]
        return pd.DataFrame(rows)
    finally:
        db.close()


def load_category_names() -> list[str]:
    db = SessionLocal()
    try:
        stmt = (
            select(Coin)
            .options(selectinload(Coin.categories))
        )
        coins = db.scalars(stmt).all()
        names = {c.name for coin in coins for c in coin.categories}
        return sorted(names)
    finally:
        db.close()


def load_last_sync_status() -> list[dict]:
    db = SessionLocal()
    try:
        stmt = select(SyncLog).order_by(SyncLog.started_at.desc()).limit(10)
        logs = db.scalars(stmt).all()
        latest_by_type = {}
        for log in logs:
            if log.sync_type not in latest_by_type:
                latest_by_type[log.sync_type] = log
        return [
            {
                "type": sync_type.value,
                "status": log.status.value,
                "finished_at": log.finished_at,
                "records_synced": log.records_synced,
                "error_message": log.error_message,
            }
            for sync_type, log in latest_by_type.items()
        ]
    finally:
        db.close()
