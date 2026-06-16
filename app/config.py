from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_max_tokens: int = 20
    openrouter_temperature: float = 0.0

    maersk_api_enabled: bool = False
    maersk_api_base_url: str = "https://api.maersk.com"
    maersk_consumer_key: str = ""
    maersk_client_secret: str = ""

    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300
    status_ttl_seconds: int = 604800  # 7 days — keeps status history for change detection

    request_timeout_seconds: int = 30
    max_concurrent_requests: int = 3
    retry_attempts: int = 2
    playwright_render_wait_seconds: int = 5

    debug: bool = False
    log_level: str = "INFO"


settings = Settings()
