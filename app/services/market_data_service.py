from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.external.coinmarketcap import CoinMarketCapClient
from app.models.category import Category
from app.models.coin import Coin
from app.models.sync_log import SyncLog, SyncStatus, SyncType


class MarketDataService:
    """Owns the sync workflow for Feature 1: fetches from CoinMarketCap via
    CoinMarketCapClient and caches results into Coin / Category, recording
    each run in SyncLog so the scheduler can enforce the once-per-24h
    cost-control rule (see is_sync_due).
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

    def sync_categories(self) -> SyncLog:
        log = self._start_log(SyncType.CATEGORIES)
        try:
            categories = self.client.get_category_list()
            count = self._upsert_categories(categories)
            self._finish_log(log, SyncStatus.SUCCESS, count)
        except Exception as exc:  # noqa: BLE001 - surfaced via SyncLog
            self.db.rollback()
            self._finish_log(log, SyncStatus.FAILED, 0, str(exc))
        return log

    def sync_listings(self) -> SyncLog:
        log = self._start_log(SyncType.LISTINGS)
        try:
            coins = self.client.get_all_listings()
            count = self._upsert_coins(coins)
            self._finish_log(log, SyncStatus.SUCCESS, count)
        except Exception as exc:  # noqa: BLE001 - surfaced via SyncLog
            self.db.rollback()
            self._finish_log(log, SyncStatus.FAILED, 0, str(exc))
        return log

    def _start_log(self, sync_type: SyncType) -> SyncLog:
        log = SyncLog(sync_type=sync_type, status=SyncStatus.RUNNING)
        self.db.add(log)
        self.db.commit()
        return log

    def _finish_log(
        self, log: SyncLog, status: SyncStatus, records_synced: int, error_message: str | None = None
    ) -> None:
        log.status = status
        log.records_synced = records_synced
        log.error_message = error_message[:2000] if error_message else None
        log.finished_at = datetime.utcnow()
        self.db.commit()

    def _upsert_categories(self, categories: list[dict]) -> int:
        """Caches CMC's curated category list (informational metadata only — the
        Basic tier doesn't expose per-category token membership, so these rows are
        not guaranteed to link to any coin). Per-coin narrative grouping instead
        comes from each coin's own `tags` in listings/latest — see _upsert_coins.
        """
        existing = {c.cmc_category_id: c for c in self.db.scalars(select(Category)).all()}
        for payload in categories:
            category = existing.get(payload["id"])
            if category is None:
                category = Category(cmc_category_id=payload["id"])
                self.db.add(category)
                existing[payload["id"]] = category
            category.name = payload["name"]
            category.slug = self._slugify(payload["name"])
            category.description = payload.get("description")
        self.db.commit()
        return len(categories)

    def _upsert_coins(self, coins: list[dict]) -> int:
        categories_by_slug = {c.slug: c for c in self.db.scalars(select(Category)).all()}
        existing_coins = {c.cmc_id: c for c in self.db.scalars(select(Coin)).all()}
        now = datetime.utcnow()

        for payload in coins:
            coin = existing_coins.get(payload["id"])
            if coin is None:
                coin = Coin(cmc_id=payload["id"])
                self.db.add(coin)
                existing_coins[payload["id"]] = coin

            quote = payload["quote"]["USD"]
            coin.symbol = payload["symbol"]
            coin.name = payload["name"]
            coin.slug = payload["slug"]
            coin.cmc_rank = payload.get("cmc_rank")
            coin.price_usd = quote.get("price")
            coin.market_cap_usd = quote.get("market_cap")
            coin.volume_24h_usd = quote.get("volume_24h")
            coin.percent_change_1h = quote.get("percent_change_1h")
            coin.percent_change_24h = quote.get("percent_change_24h")
            coin.percent_change_7d = quote.get("percent_change_7d")
            coin.last_synced_at = now

            # Each coin's own `tags` (e.g. "defi", "layer-1") are the real dynamic
            # narrative classification CMC gives us on the Basic tier — self-heal
            # any tag we haven't seen as a Category yet instead of dropping it.
            tag_slugs = payload.get("tags") or []
            coin_categories = []
            for slug in tag_slugs:
                category = categories_by_slug.get(slug)
                if category is None:
                    category = Category(
                        cmc_category_id=slug,
                        name=self._humanize(slug),
                        slug=slug,
                    )
                    self.db.add(category)
                    categories_by_slug[slug] = category
                coin_categories.append(category)
            coin.categories = coin_categories

        self.db.commit()
        return len(coins)

    @staticmethod
    def _slugify(name: str) -> str:
        return name.strip().lower().replace(" ", "-")

    @staticmethod
    def _humanize(slug: str) -> str:
        return slug.replace("-", " ").replace("_", " ").title()
