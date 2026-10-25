from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path — pydantic-settings otherwise resolves env_file relative to
# the process's cwd, which breaks whenever this module is imported from a
# process started elsewhere (e.g. the Reflex frontend, whose cwd is
# frontend/, cross-importing this package for the view-driven live sync).
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    # Local development only: when set (DEV_AUTO_LOGIN_EMAIL in the local,
    # gitignored .env) the site logs that account in automatically, but only
    # for requests whose Host is localhost (auth_service.dev_auto_login).
    # Never set on a server.
    dev_auto_login_email: str = ""

    # Private mode: when set (comma-separated emails, e.g. on the live server),
    # only these accounts can log in, sign-up is closed, and every page sends
    # a logged-out visitor to /login (auth_service.is_allowed,
    # CoinState.restore_session). Empty = the site is open as before.
    allowed_login_emails: str = ""

    # Google sign-in (Google Identity Services). Only the client ID is used:
    # an ID token is verified with Google's public keys and must be issued
    # for this client ID (app/services/google_auth_service.py). The client
    # secret is not needed for this flow and is never sent anywhere.
    google_client_id: str = ""

    # Telegram bot (@BotFather) that delivers triggered price alerts to a
    # connected account (app/services/telegram_notify_service.py), and the
    # public site URL used for the "Open on Repace" link in those messages.
    telegram_bot_token: str = ""
    public_site_url: str = "https://repace.fyqqflow.com"
    # True on ONE server only (live): runs the bot's command listener
    # (/alerts, /alert ETH). Telegram allows a single getUpdates consumer per
    # bot token, so local dev leaves this off (on-demand linking only).
    telegram_bot_polling: bool = False
    # True on the same ONE server: sends the automatic Gainers & Losers digest
    # (app/services/telegram_digest_service.py) so it is not sent twice.
    telegram_digest: bool = False

    # CPI & FOMC calendar (/tools/cpi-fomc): the schedule, forecast and previous come from the free
    # public Forex Factory feed (no key); actual values come from the free official sources (BLS for CPI,
    # FRED for the fed funds target). An Apify token is an optional extra (pay per event, 25 free rows
    # per run) for whatever those cannot fill (app/services/macro_calendar_service.py).
    apify_token: str = ""
    macro_actuals_max_runs_per_day: int = 40
    # Free BLS registration key (https://data.bls.gov/registrationEngine/). Optional: without it the BLS v1
    # API is used (25 requests a day), with it v2 (500 a day).
    bls_api_key: str = ""
    # Free FRED API key (https://fredaccount.stlouisfed.org/apikeys). Optional: gives the CPI and jobs report
    # release dates weeks ahead (Telegram 7-day / 3-day reminders, the month view); FOMC dates need no key.
    fred_api_key: str = ""
    macro_free_actuals_max_per_day: int = 20  # BLS public API v1 allows 25 requests a day

    # MEXC portfolio (/portfolio and the coin page's "Your MEXC orders"), app/services/mexc_service.py. A
    # READ-ONLY key (Spot: View Account Details + View Order Details only) linked to the server's IP; the
    # service only ever sends signed GETs to a fixed list of read endpoints. The key and secret stay on the
    # server: never logged, never put in page state. Only the logged-in accounts in MEXC_VIEWER_EMAILS
    # (comma-separated) see the data; empty = nobody. MEXC_FIXTURE_FILE (local UI testing only) serves a JSON
    # file of MEXC-shaped responses instead of calling MEXC, and the page shows a "Demo data" badge.
    mexc_api_key: str = ""
    mexc_api_secret: str = ""
    mexc_viewer_emails: str = ""
    mexc_fixture_file: str = ""

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

    # How often app/scheduler/jobs.py::run_news_pipeline_sync re-runs the
    # standalone news pipeline (app/services/news_pipeline.py). Float, not
    # int — APScheduler's interval trigger and datetime.timedelta both
    # accept fractional hours, needed to express a sub-hour cadence (e.g.
    # 0.25 = 15 minutes). The RSS feeds it ingests only ever expose a
    # site's current "latest N" items (not an archive), so real 90-day-deep
    # coverage for those sources only accumulates by actually running this
    # repeatedly over time, not from any one run; a shorter interval
    # surfaces newly-published articles (RSS and Google News alike) sooner
    # — though see this module's own note on _news_sync_due for why an
    # interval shorter than a single run's real duration doesn't actually
    # buy extra freshness.
    news_pipeline_sync_interval_hours: float = 0.25

    # Feature 1 placeholders: reserved for the CoinMarketCap wrapper, unused until connected.
    coinmarketcap_api_key: str = ""
    coinmarketcap_base_url: str = "https://pro-api.coinmarketcap.com"

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
    # Cost guards for every OpenRouter call (see app/services/ai_budget.py).
    openrouter_max_calls_per_hour: int = 60
    openrouter_failure_cooldown_minutes: int = 30
    # Free-tier daily request cap (50 a day, per account, reset 00:00 UTC; 0 = unlimited, set it once credits are
    # added). Background AI work stops `openrouter_visit_reserve` calls early so page-visit summaries always
    # have room (app/services/ai_budget.py).
    openrouter_daily_limit: int = 50
    openrouter_visit_reserve: int = 30
    # Local Malay translation model (app/services/local_translate_service.py): folder of the NLLB-200 600M CTranslate2 model
    # (fetched by `python -m scripts.download_translation_model`) and how many CPU threads one translation may use.
    translation_model_dir: str = "models/nllb-600m-ct2-int8"
    translation_threads: int = 2
    # Beam width of the translation search: 2 is about 2.3x faster than 4 on the live server (a whole summary in ~11 s instead of ~24 s)
    # with a small quality cost; 4 threads were slower than 2 on that 4-vCPU server.
    translation_beam_size: int = 2
    # Weekly coin business-model category check (app/services/
    # coin_category_service.py): one OpenRouter call (8 coins) per interval.
    # 120 min = 12 calls/day, sized for the free tier's ~50 requests/day;
    # lower it on a paid model to cover the whole weekly re-check faster.
    coin_category_interval_minutes: int = 120

    # Google reCAPTCHA v3 (invisible, score based) on the login/signup forms. Set
    # RECAPTCHA_SITE_KEY / RECAPTCHA_SECRET_KEY in .env (v3 keys; v2 keys will not work).
    # Off by default until the v3 keys are confirmed to work for the domain in use.
    recaptcha_enabled: bool = False
    recaptcha_site_key: str = ""
    recaptcha_secret_key: str = ""

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

    # DeFiLlama unlocks deep-link resolution (see
    # app/services/defillama_unlocks_service.py) — whether a token's
    # DefiLlama protocol slug exists at all barely ever changes, same
    # reasoning as tradingview_symbol_ttl_hours above.
    defillama_unlocks_ttl_hours: int = 24

    # Spoken price alerts (app/services/alert_voice_service.py).
    gemini_api_key: str = ""
    gemini_text_model: str = "gemini-2.5-flash"
    # gemini-2.5-flash has no audio output; speech comes from the TTS variant.
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    gemini_voice_name: str = "Puck"


settings = Settings()
