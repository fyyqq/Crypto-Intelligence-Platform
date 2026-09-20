"""CoinMarketCap API wrapper.

NOT CONNECTED YET. This is the boilerplate shape for Feature 1's external client —
method signatures mirror the CMC Basic (free tier) endpoints we'll need, but the
HTTP calls are intentionally left unimplemented pending explicit approval to
connect live (see ai-instructions.md rules on API cost control).
"""

from app.core.config import settings


class CoinMarketCapClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or settings.coinmarketcap_api_key
        self.base_url = base_url or settings.coinmarketcap_base_url

    def get_listings_latest(self, limit: int = 500) -> dict:
        """Maps to GET /v1/cryptocurrency/listings/latest."""
        raise NotImplementedError(
            "CoinMarketCap integration is pending approval — not connected yet."
        )

    def get_category_list(self) -> dict:
        """Maps to GET /v1/cryptocurrency/categories."""
        raise NotImplementedError(
            "CoinMarketCap integration is pending approval — not connected yet."
        )

    def get_category(self, category_id: str) -> dict:
        """Maps to GET /v1/cryptocurrency/category."""
        raise NotImplementedError(
            "CoinMarketCap integration is pending approval — not connected yet."
        )
