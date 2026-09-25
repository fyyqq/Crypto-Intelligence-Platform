from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.external.coinmarketcap import CoinMarketCapClient
from app.models.category import Category
from app.models.coin import Coin
from app.models.coin_contract import CoinContract
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

    def is_sync_due(self, sync_type: SyncType, interval_hours: int | None = None) -> bool:
        stmt = (
            select(SyncLog)
            .where(SyncLog.sync_type == sync_type, SyncLog.status == SyncStatus.SUCCESS)
            .order_by(SyncLog.started_at.desc())
            .limit(1)
        )
        last_success = self.db.scalars(stmt).first()
        if last_success is None:
            return True
        hours = interval_hours if interval_hours is not None else settings.sync_interval_hours
        cutoff = datetime.utcnow() - timedelta(hours=hours)
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

    def sync_hot_listings(self) -> SyncLog:
        """Frequent, cheap refresh (see settings.hot_sync_interval_hours) of
        just the top settings.hot_sync_top_n coins' quote fields (price,
        market cap, 24h volume, 1h/24h/7d % change) — a single listings/latest
        call. Never creates coins or touches categories/tags/contracts; that
        stays on the slower full sync_listings/sync_contracts cadence.
        """
        log = self._start_log(SyncType.LISTINGS_HOT)
        try:
            coins = self.client.get_top_listings(settings.hot_sync_top_n)
            count = self._upsert_quotes(coins)
            self._finish_log(log, SyncStatus.SUCCESS, count)
        except Exception as exc:  # noqa: BLE001 - surfaced via SyncLog
            self.db.rollback()
            self._finish_log(log, SyncStatus.FAILED, 0, str(exc))
        return log

    def sync_ids(self, cmc_ids: list[int]) -> SyncLog:
        """View-driven refresh: just the given coins' quote fields, called
        on demand for whichever page a Reflex session is actually looking
        at (see frontend/state/coin_state.py's live sync loop), regardless
        of rank. Not gated by is_sync_due — the caller's own polling
        interval controls the cadence. Never creates coins or touches
        categories/tags/contracts.
        """
        log = self._start_log(SyncType.LISTINGS_RANGE)
        try:
            coins = self.client.get_quotes_by_ids(cmc_ids)
            count = self._upsert_quotes(coins)
            self._finish_log(log, SyncStatus.SUCCESS, count)
        except Exception as exc:  # noqa: BLE001 - surfaced via SyncLog
            self.db.rollback()
            self._finish_log(log, SyncStatus.FAILED, 0, str(exc))
        return log

    def sync_contracts(self) -> SyncLog:
        """Fetches each coin's cross-chain contract list from CMC's /v2/info
        endpoint (~1 call per 100 coins). Kept as its own SyncType so it's
        gated by the same 24h is_sync_due rule rather than adding cost every
        listings sync.
        """
        log = self._start_log(SyncType.CONTRACTS)
        try:
            cmc_ids = [c.cmc_id for c in self.db.scalars(select(Coin)).all()]
            info_by_id = self.client.get_platforms_info(cmc_ids)
            count = self._upsert_contracts(info_by_id)
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
            coin.circulating_supply = payload.get("circulating_supply")
            coin.total_supply = payload.get("total_supply")
            coin.max_supply = payload.get("max_supply")
            coin.fully_diluted_market_cap = quote.get("fully_diluted_market_cap")
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

    def _upsert_quotes(self, coins: list[dict]) -> int:
        """Quote-only counterpart to _upsert_coins for the hot sync: updates
        price/market_cap/volume/percent_change fields on coins that already
        exist from a full sync_listings run, skips any CMC id we haven't
        seen yet (that coin will appear on the next full sync), and never
        touches name/slug/tags/categories.
        """
        existing_coins = {c.cmc_id: c for c in self.db.scalars(select(Coin)).all()}
        now = datetime.utcnow()
        count = 0
        for payload in coins:
            coin = existing_coins.get(payload["id"])
            if coin is None:
                continue
            quote = payload["quote"]["USD"]
            coin.cmc_rank = payload.get("cmc_rank")
            coin.price_usd = quote.get("price")
            coin.market_cap_usd = quote.get("market_cap")
            coin.volume_24h_usd = quote.get("volume_24h")
            coin.percent_change_1h = quote.get("percent_change_1h")
            coin.percent_change_24h = quote.get("percent_change_24h")
            coin.percent_change_7d = quote.get("percent_change_7d")
            coin.circulating_supply = payload.get("circulating_supply")
            coin.total_supply = payload.get("total_supply")
            coin.max_supply = payload.get("max_supply")
            coin.fully_diluted_market_cap = quote.get("fully_diluted_market_cap")
            coin.last_synced_at = now
            count += 1
        self.db.commit()
        return count

    def _upsert_contracts(self, info_by_id: dict[int, dict]) -> int:
        coins_by_cmc_id = {c.cmc_id: c for c in self.db.scalars(select(Coin)).all()}
        count = 0
        for cmc_id, info in info_by_id.items():
            coin = coins_by_cmc_id.get(cmc_id)
            if coin is None:
                continue

            for field, value in self._extract_urls(info).items():
                setattr(coin, field, value)
            coin.description = info.get("description")

            declared_platform = info.get("platform")
            entries = info.get("contract_address") or []
            if not entries and declared_platform:
                entries = [
                    {
                        "contract_address": declared_platform.get("token_address"),
                        "platform": {
                            "name": declared_platform.get("name"),
                            "coin": declared_platform.get("coin") or {},
                        },
                    }
                ]

            contracts = [
                CoinContract(
                    platform_name=entry["platform"]["name"],
                    platform_symbol=entry["platform"].get("coin", {}).get("symbol"),
                    contract_address=entry.get("contract_address"),
                    sort_order=order,
                )
                for order, entry in enumerate(entries)
                if entry.get("platform", {}).get("name")
            ]

            if contracts:
                declared_name = (declared_platform or {}).get("name")
                primary = next((c for c in contracts if c.platform_name == declared_name), None)
                if primary is None:
                    # No single declared platform (root assets like BTC/ETH/BNB, or
                    # multi-issued stablecoins): the coin's native home is whichever
                    # chain's own gas token is this coin itself (e.g. ETH's own
                    # entry among its bridged copies elsewhere). Falls back to
                    # CMC's own list order when no chain matches that way.
                    primary = next(
                        (c for c in contracts if c.platform_symbol == coin.symbol), contracts[0]
                    )
                primary.is_primary = True

            coin.contracts = contracts
            count += 1
        self.db.commit()
        return count

    @staticmethod
    def _extract_urls(info: dict) -> dict[str, str | None]:
        """Pulls website/whitepaper/social/explorer links out of /v2/info's
        `urls` object — each field there is a list (CMC lets a project
        declare more than one), so this just takes the first entry. `chat`
        mixes Telegram/Discord/Gitter/etc — only a link actually containing
        "t.me" is trusted as Telegram (the UI shows a Telegram icon for this
        field, so falling back to some other chat link there would mislabel
        it); coins whose only declared chat isn't Telegram just get no
        telegram_url rather than a wrongly-badged link.
        """
        urls = info.get("urls") or {}

        def first(key: str) -> str | None:
            values = urls.get(key) or []
            return values[0] if values else None

        chat_links = urls.get("chat") or []
        telegram = next((link for link in chat_links if "t.me" in link), None)

        return {
            "website_url": first("website"),
            "whitepaper_url": first("technical_doc"),
            "twitter_url": first("twitter"),
            "telegram_url": telegram,
            "source_code_url": first("source_code"),
            "explorer_url": first("explorer"),
            "reddit_url": first("reddit"),
            "facebook_url": first("facebook"),
        }

    @staticmethod
    def _slugify(name: str) -> str:
        return name.strip().lower().replace(" ", "-")

    @staticmethod
    def _humanize(slug: str) -> str:
        return slug.replace("-", " ").replace("_", " ").title()
