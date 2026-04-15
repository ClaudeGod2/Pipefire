from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    abpi_api_key: str = ""
    abpi_base_url: str = "https://abpi.se/api"
    database_url: str = "sqlite:///./data/pipefire.db"
    output_dir: str = "./data/exports"
    scb_cache_path: str = "./data/scb_cache.txt"
    scb_cache_ttl: int = 604800
    secret_key: str = "change_me"
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = "http://localhost:8000/auth/gmail/callback"
    gmail_token_path: str = "./data/token.json"
    sender_name: str = "Adam"
    gmail_send_as: str = ""
    abpi_request_delay: float = 0.15
    abpi_timeout: int = 10
    followup_day_1: int = 5
    followup_day_2: int = 10
    followup_cold: int = 15

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
