"""CoinMarketCap API wrapper (Basic Free Tier).

Thin client around the two endpoints Feature 1 needs. Kept dependency-free of
any persistence/business logic — that lives in app/services/market_data_service.py.
"""

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

    def get_category_list(self) -> list[dict]:
        """GET /v1/cryptocurrency/categories — the full dynamic narrative/category list."""
        payload = self._get("/v1/cryptocurrency/categories")
        return payload["data"]
