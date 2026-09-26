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
    # rate-limits unpredictably. Configured actor: Apify's "Twitter (X)
    # Scraper - Tweets, Profiles & Monitor" (scrapesage/twitter-scraper, id
    # FqR0b3b6K64iyiDHL) — swapped from the previously-configured actor
    # (Y3cgyqvI46p0VMr0m) specifically because that one's free tier is a
    # hard 10-tweet-scrapes/month cap account-wide (confirmed live, and
    # already exhausted), while this one bills per event with no such fixed
    # monthly wall (confirmed live: $0.002/tweet, no "profile" event
    # charged at all since SocialService requests includeProfile=false).
    # SocialService._normalize is written against this actor's own schema
    # (confirmed live: {"handles": [...], "maxTweetsPerProfile": ...,
    # "includeProfile": false, "includeTweets": true} in, ISO
    # "createdAt" + a "media": [{"type": "photo"|"video", "url", ...}] list
    # out), not a generic guess across Apify's various X-scraper actors —
    # swapping the configured actor again would need re-verifying that
    # shape (confirmed live it differs meaningfully between actors: field
    # names, date format, and whether a "profile" summary row is mixed
    # into the same result list all varied across the three actors tried
    # this session).
    apify_api_token: str = ""
    apify_actor_id: str = "FqR0b3b6K64iyiDHL"
    social_cache_ttl_hours: int = 4
    # How many of a coin's own latest posts to scrape per profile — this is
    # also the actor's own billing unit (pay-per-tweet-scraped), so this is
    # a direct cost lever, not just a display cap.
    social_max_posts: int = 20

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

    # Last-resort TradingView DEX-pool chart symbol lookup (see
    # app/services/tradingview_symbol_service.py) — only ever queried for a
    # coin with zero real CEX pairs, and a DEX pool's existence/symbol on
    # TradingView is far more stable than exchange price/volume, so this
    # gets a much longer TTL than market_pairs_cache_ttl_hours above.
    tradingview_symbol_ttl_hours: int = 24


settings = Settings()
