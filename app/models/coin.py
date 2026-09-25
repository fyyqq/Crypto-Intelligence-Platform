from datetime import datetime

from sqlalchemy import JSON, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.category import coin_category


class Coin(Base):
    __tablename__ = "coins"

    id: Mapped[int] = mapped_column(primary_key=True)
    cmc_id: Mapped[int] = mapped_column(unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    cmc_rank: Mapped[int | None] = mapped_column(nullable=True)

    price_usd: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    market_cap_usd: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    volume_24h_usd: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    percent_change_1h: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    percent_change_24h: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    percent_change_7d: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    # circulating/total/max_supply and fully_diluted_market_cap are already
    # present on every listings/latest and quotes/latest response we already
    # fetch — just never persisted before now, so this is free (no new API
    # call) real data for the coin-detail stats box (see MarketDataService.
    # _upsert_coins/_upsert_quotes).
    # Wider precision than market_cap_usd/volume_24h_usd: those are bounded by
    # price * circulating_supply (generally sane), but FDV = price * max/total
    # supply can be an astronomically large, low-quality number for shitcoins
    # with an uncapped supply — confirmed live, a Numeric(24, 2) FDV column
    # overflowed on a real synced coin (6.78e+23).
    circulating_supply: Mapped[float | None] = mapped_column(Numeric(36, 2), nullable=True)
    total_supply: Mapped[float | None] = mapped_column(Numeric(36, 2), nullable=True)
    max_supply: Mapped[float | None] = mapped_column(Numeric(36, 2), nullable=True)
    fully_diluted_market_cap: Mapped[float | None] = mapped_column(Numeric(36, 2), nullable=True)

    # Sourced from /v2/cryptocurrency/info's `urls` object — fetched on the
    # same 24h sync_contracts call that already pulls contract_address from
    # that endpoint (see MarketDataService._extract_urls), so this is free:
    # no new API call, just persisting fields the response already carries.
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    whitepaper_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    twitter_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    telegram_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_code_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    explorer_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reddit_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    facebook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Free-text project description, straight from the same /v2/info payload
    # website_url etc. above already come from — no new API call, just one
    # more field persisted from a response we already fetch. Text (not a
    # bounded String) since CMC's community-submitted descriptions vary
    # wildly in length with no documented cap.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set once (see app/services/coingecko_service.py::upgrade_description)
    # after the first on-demand attempt to replace CMC's own auto-generated
    # "<name> is a cryptocurrency and operates on..." boilerplate (CMC's
    # public API has no real curated description for most non-major coins —
    # confirmed live for several, e.g. Pythia — only their website does) with
    # CoinGecko's free public API, which does carry real project write-ups
    # for the same coins via a contract-address lookup. Once set, the nightly
    # _upsert_contracts sync stops overwriting `description` from CMC, so a
    # successfully-upgraded real description survives future syncs instead
    # of being clobbered back to boilerplate.
    description_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Set once (see app/services/description_ai_service.py) after the
    # one-time attempt to replace a description that's STILL boilerplate
    # after the CoinGecko upgrade above (common for memecoins/newly-listed
    # tokens with no real whitepaper or curated write-up anywhere) with an
    # AI-generated summary grounded in that project's own website text and/or
    # cached X posts — the only two public sources available for a coin with
    # no formal documentation. Independent of description_synced_at (which
    # gates the CoinGecko step only) since the two steps can each succeed or
    # fail on their own.
    description_ai_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # AI-generated "what does this coin do / how does it make money" plain-
    # language explainer (see app/services/business_summary_service.py —
    # Feature 2's AI Business Model Agent per ai-instructions.md), built from
    # this coin's own name/category/description via OpenRouter rather than a
    # fetched whitepaper. business_summary_updated_at gates regeneration to
    # once per settings.business_summary_ttl_days — periodic (not one-time
    # like description_synced_at above) since a project's real business
    # model can genuinely change over time.
    business_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # The exact OpenRouter model slug that generated business_summary (from
    # the API response's own "model" field, not just settings.
    # openrouter_model — the two can differ if OpenRouter routes to a
    # specific provider/variant) — drives the UI's "Generated by AI ·
    # <model>" attribution badge, kept accurate per-summary even after the
    # configured default model changes.
    business_summary_model: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # AI-generated short business-model classification (e.g. "Tokenized
    # Public Funds / Treasuries", "RWA Sovereign Layer-1") — generated by the
    # same OpenRouter call as business_summary (see that service's
    # CATEGORY: line), more specific than the broad CMC narrative tags shown
    # elsewhere on the page (e.g. "Real World Assets (RWA)"). Shares
    # business_summary_updated_at's TTL — regenerated together, never
    # independently, so no separate timestamp column for this one.
    business_model_category: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # On-demand CEX/DEX market-pair listing cache (see
    # app/services/market_pairs_service.py) — real per-exchange price/volume
    # from CoinGecko's free API (CMC's equivalent endpoint 403s on this
    # project's Basic/free CMC plan — see that service's module docstring).
    # Same TTL-cached-JSON-column pattern as cached_tweets below, just a
    # much shorter TTL (settings.market_pairs_cache_ttl_hours) since price/
    # volume data is far more time-sensitive than a cached tweet.
    cached_market_pairs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    market_pairs_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # On-demand X (Twitter) post cache (see app/services/social_service.py)
    # — x_username is parsed from twitter_url above the first time a coin's
    # detail page is viewed; cached_tweets holds up to 10 already-normalized
    # {text, image_url, has_image, url, time_display, likes, replies,
    # retweets} dicts from the last successful scraper call.
    # last_social_update gates re-scraping to once per
    # settings.social_cache_ttl_hours, protecting scraper API credits the
    # same way the CMC sync cadences protect CMC's. Plain JSON (not
    # Postgres's JSONB) since nothing here ever queries *inside* the array —
    # it's only ever read/written whole — and a plain JSON type mirrors
    # cleanly to the Reflex SQLite cache, which has no JSONB equivalent.
    x_username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cached_tweets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    last_social_update: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    categories: Mapped[list["Category"]] = relationship(
        secondary=coin_category, back_populates="coins"
    )
    contracts: Mapped[list["CoinContract"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="CoinContract.sort_order",
    )
