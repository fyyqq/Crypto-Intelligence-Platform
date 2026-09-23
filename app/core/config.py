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


settings = Settings()
