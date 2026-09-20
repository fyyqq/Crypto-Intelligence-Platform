from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = "postgresql+psycopg2://crypto:crypto@localhost:5432/crypto_intelligence"

    sync_interval_hours: int = 24

    # Feature 1 placeholders: reserved for the CoinMarketCap wrapper, unused until connected.
    coinmarketcap_api_key: str = ""
    coinmarketcap_base_url: str = "https://pro-api.coinmarketcap.com"


settings = Settings()
