from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ValidationError


class Settings(BaseSettings):
    GEMINI_API_KEY: str
    SARVAM_API_KEY: str
    HA_URL: str
    HA_TOKEN: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


_settings: Settings | None = None


def load_settings() -> Settings:
    global _settings
    _settings = Settings()
    return _settings


def get_settings() -> Settings:
    if _settings is None:
        raise RuntimeError("Settings not loaded. Call load_settings() first.")
    return _settings


def missing_fields() -> list[str]:
    """Return names of required fields missing from .env."""
    import os
    from dotenv import dotenv_values

    values = dotenv_values(".env")
    required = ["GEMINI_API_KEY", "SARVAM_API_KEY", "HA_URL", "HA_TOKEN"]
    return [f for f in required if not values.get(f) and not os.environ.get(f)]
