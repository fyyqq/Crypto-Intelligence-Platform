from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.external.coinmarketcap import CoinMarketCapClient
from app.models.sync_log import SyncLog, SyncStatus, SyncType


class MarketDataService:
    """Owns the sync workflow for Feature 1. Delegates raw HTTP calls to
    CoinMarketCapClient (currently unimplemented — see app/external/coinmarketcap.py)
    and persists sync outcomes to SyncLog so the scheduler can enforce the
    once-per-24h cost-control rule.
    """

    def __init__(self, db: Session, client: CoinMarketCapClient | None = None) -> None:
        self.db = db
        self.client = client or CoinMarketCapClient()

    def is_sync_due(self, sync_type: SyncType) -> bool:
        stmt = (
            select(SyncLog)
            .where(SyncLog.sync_type == sync_type, SyncLog.status == SyncStatus.SUCCESS)
            .order_by(SyncLog.started_at.desc())
            .limit(1)
        )
        last_success = self.db.scalars(stmt).first()
        if last_success is None:
            return True
        cutoff = datetime.utcnow() - timedelta(hours=settings.sync_interval_hours)
        return last_success.started_at < cutoff

    def sync_listings(self) -> SyncLog:
        return self._run_sync(SyncType.LISTINGS, lambda: self.client.get_listings_latest())

    def sync_categories(self) -> SyncLog:
        return self._run_sync(SyncType.CATEGORIES, lambda: self.client.get_category_list())

    def _run_sync(self, sync_type: SyncType, fetch) -> SyncLog:
        log = SyncLog(sync_type=sync_type, status=SyncStatus.RUNNING)
        self.db.add(log)
        self.db.commit()

        try:
            fetch()
            # TODO (Feature 1, next review): persist fetched records into
            # Coin / Category once the CoinMarketCap client is connected.
            log.status = SyncStatus.SUCCESS
        except NotImplementedError as exc:
            log.status = SyncStatus.FAILED
            log.error_message = str(exc)
        except Exception as exc:  # noqa: BLE001 - surfaced via SyncLog for now
            log.status = SyncStatus.FAILED
            log.error_message = str(exc)
        finally:
            log.finished_at = datetime.utcnow()
            self.db.commit()

        return log
