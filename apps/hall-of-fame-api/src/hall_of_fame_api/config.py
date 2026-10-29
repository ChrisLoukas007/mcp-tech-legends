"""Settings for the private app, read from HALL_OF_FAME_API_* environment variables."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HALL_OF_FAME_API_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8200
    database_url: SecretStr = SecretStr("postgresql://halloffame_app:change-me@localhost:5433/legends")

    # Who may call this API: tokens for THIS audience, from these OAuth clients only.
    issuer_url: str = "http://localhost:8180/realms/legends"
    jwks_url: str = "http://localhost:8180/realms/legends/protocol/openid-connect/certs"
    audience: str = "hall-of-fame-api"
    trusted_callers: tuple[str, ...] = ("hall-of-fame-mcp",)

    rate_limit: str = "60/minute"
