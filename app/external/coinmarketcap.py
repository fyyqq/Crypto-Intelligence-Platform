"""CoinMarketCap API wrapper (Basic Free Tier).

Thin client around the two endpoints Feature 1 needs. Kept dependency-free of
any persistence/business logic — that lives in app/services/market_data_service.py.
"""

import time

import requests

from app.core.config import settings


class CoinMarketCapClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 15,
    ) -> None:
        self.api_key = api_key or settings.coinmarketcap_api_key
        self.base_url = base_url or settings.coinmarketcap_base_url
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = requests.get(
            f"{self.base_url}{path}",
            headers={
                "X-CMC_PRO_API_KEY": self.api_key,
                "Accept": "application/json",
            },
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_all_listings(self, page_size: int = 5000) -> list[dict]:
        """GET /v1/cryptocurrency/listings/latest — every currently listed coin, USD
        quote. Paginates via `start`/`limit` (5000 is CMC's max per call) until the
        API's own `status.total_count` is covered, so this always reflects the
        real, current total rather than a hardcoded page size.
        """
        all_coins: list[dict] = []
        start = 1
        while True:
            payload = self._get(
                "/v1/cryptocurrency/listings/latest",
                params={"start": start, "limit": page_size, "convert": "USD"},
            )
            page = payload["data"]
            all_coins.extend(page)
            total_count = payload["status"]["total_count"]
            start += page_size
            if not page or start > total_count:
                break
        return all_coins

    def get_top_listings(self, limit: int = 500) -> list[dict]:
        """GET /v1/cryptocurrency/listings/latest, single call, no pagination —
        CMC sorts by market_cap rank by default, so `limit` (<=5000) is just
        the top N coins in one request. Used for the frequent "hot" quote
        refresh (price/market cap/volume/1h/24h/7d) instead of re-fetching
        the full universe every cycle.
        """
        payload = self._get(
            "/v1/cryptocurrency/listings/latest",
            params={"start": 1, "limit": limit, "convert": "USD"},
        )
        return payload["data"]

    def get_quotes_by_ids(self, cmc_ids: list[int], batch_size: int = 100) -> list[dict]:
        """GET /v2/cryptocurrency/quotes/latest, batched (CMC caps `id` at 100
        per call) — refreshes just the given coins' quote (price/market cap/
        volume/1h/24h/7d), regardless of their rank. Used for the
        view-driven sync: whichever page a user is actually looking at,
        rather than a fixed top-N cutoff. Returns a flat list shaped like
        get_top_listings's entries (each with its own "id") so both feed the
        same quote-only upsert.
        """
        quotes: list[dict] = []
        for i in range(0, len(cmc_ids), batch_size):
            if i > 0:
                # Basic tier caps requests at 30/min; ~2.2s of headroom per
                # call keeps a multi-batch sync well under that.
                time.sleep(2.2)
            batch = cmc_ids[i : i + batch_size]
            payload = self._get(
                "/v2/cryptocurrency/quotes/latest",
                params={"id": ",".join(str(cid) for cid in batch), "convert": "USD"},
            )
            for id_str, entry in payload["data"].items():
                entry.setdefault("id", int(id_str))
                quotes.append(entry)
        return quotes

    def get_category_list(self) -> list[dict]:
        """GET /v1/cryptocurrency/categories — the full dynamic narrative/category list."""
        payload = self._get("/v1/cryptocurrency/categories")
        return payload["data"]

    def get_platforms_info(self, cmc_ids: list[int], batch_size: int = 100) -> dict[int, dict]:
        """GET /v2/cryptocurrency/info, batched (CMC caps `id` at 100 per call) —
        the `contract_address` list per coin is the only place the Basic tier
        exposes every chain a token is deployed on (listings/latest only carries
        a single primary `platform`). Returns {cmc_id: raw info payload}.
        """
        info_by_id: dict[int, dict] = {}
        for i in range(0, len(cmc_ids), batch_size):
            if i > 0:
                # Basic tier caps requests at 30/min; ~2.2s of headroom per
                # call keeps a full 82-batch sync well under that.
                time.sleep(2.2)
            batch = cmc_ids[i : i + batch_size]
            payload = self._get(
                "/v2/cryptocurrency/info",
                params={"id": ",".join(str(cid) for cid in batch)},
            )
            for id_str, entry in payload["data"].items():
                info_by_id[int(id_str)] = entry
        return info_by_id
