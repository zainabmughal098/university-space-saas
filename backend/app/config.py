"""Environment configuration; never log the database connection string."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True,
    )
    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
            valid = (
                url.drivername == "postgresql+psycopg"
                and bool(url.host and url.database and url.username and url.password)
                and url.username not in {"USER", "REPLACE_WITH_USER"}
                and url.password not in {"PASSWORD", "REPLACE_WITH_PASSWORD"}
            )
        except Exception:
            valid = False
        if not valid:
            raise ValueError("Set DATABASE_URL in backend/.env to a PostgreSQL psycopg URL with your database credentials.")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
