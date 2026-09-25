from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path — pydantic-settings otherwise resolves env_file relative to
# the process's cwd, which breaks whenever this module is imported from a
# process started elsewhere (e.g. the Reflex frontend, whose cwd is
# frontend/, cross-importing this package for the view-driven live sync).
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = "postgresql+psycopg2://crypto:crypto@localhost:5432/crypto_intelligence"

    sync_interval_hours: int = 24

    # "Hot" sync: a cheap, frequent refresh of just the top N coins' price/
    # market cap/volume/1h/24h/7d quote (a single listings/latest call), so
    # the dashboard's most-viewed rows stay near-live without re-syncing the
    # full ~8,000-coin universe (that stays on sync_interval_hours).
    hot_sync_interval_hours: int = 1
    hot_sync_top_n: int = 500

    # Feature 1 placeholders: reserved for the CoinMarketCap wrapper, unused until connected.
    coinmarketcap_api_key: str = ""
    coinmarketcap_base_url: str = "https://pro-api.coinmarketcap.com"

    # On-demand X (Twitter) post caching (see app/services/social_service.py)
    # — replaces the free embed widget, which X's own syndication backend
    # rate-limits unpredictably. apify_actor_id defaults to a placeholder;
    # whichever actor is actually configured must return per-tweet text +
    # image URLs, since SocialService._normalize's field-name guessing is
    # written against the common shapes seen across Apify's X-scraper
    # actors, not one specific schema.
    apify_api_token: str = ""
    apify_actor_id: str = "apidojo~tweet-scraper"
    social_cache_ttl_hours: int = 4

    # On-demand "About the business" summary (see
    # app/services/business_summary_service.py) — Feature 2's AI Business
    # Model Agent per ai-instructions.md, generated via OpenRouter rather
    # than a direct per-provider API key so the model can be swapped without
    # a code change. Refreshed periodically (not once-forever like
    # description_synced_at) since a project's real business model can
    # change over time in a way its own CMC/CoinGecko description won't
    # reflect.
    openrouter_api_key: str = ""
    # ai-instructions.md's roadmap named "Claude 3.5 Sonnet" for this feature,
    # but that model has since been retired from OpenRouter (confirmed live —
    # it now 404s with "No endpoints found"), and this project's own
    # OpenRouter account is on the free tier with $0 credit balance, which
    # 402s on every paid model regardless of price (confirmed live against
    # both anthropic/claude-sonnet-5 and the far cheaper claude-haiku-4.5).
    # Defaults to the largest :free-suffixed model available instead (550B
    # params, easily the biggest free option on OpenRouter at the time this
    # was checked) — no cost, works within OpenRouter's free-tier daily
    # request quota (50/day, checked via /api/v1/key) — see
    # business_summary_service.py's retry handling for this tier's other
    # characteristic: transient 429s from its shared provider pool, not a
    # real quota problem. Coin.business_summary_model records whichever
    # model actually served each generation (from the API response itself),
    # so the UI's attribution badge stays accurate even after this default
    # changes.
    openrouter_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    business_summary_ttl_days: int = 60

    # On-demand CEX/DEX market-pair listing (see
    # app/services/market_pairs_service.py) — refreshed far more often than
    # description/business_summary since real exchange price/volume data
    # goes stale within the hour, unlike a project's write-up or business
    # model, which barely change week to week.
    market_pairs_cache_ttl_hours: int = 1


settings = Settings()
