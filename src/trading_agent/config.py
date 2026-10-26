"""Configuration management using Pydantic Settings.

Reads settings from environment variables and `.env` file with
automatic deduplication of watchlist entries.
"""

import logging
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

DEFAULT_WATCHLIST = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
]


class Settings(BaseSettings):
    """Application configuration settings."""

    database_path: str = Field(
        default="trading_agent.db",
        description="Path to local SQLite database file",
    )
    watchlist: list[str] = Field(
        default_factory=lambda: list(DEFAULT_WATCHLIST),
        description="List of stock tickers to monitor",
    )
    benchmark_symbol: str = Field(
        default="^NSEI",
        description="Market index ticker symbol (default NIFTY 50)",
    )
    telegram_bot_token: Optional[str] = Field(
        default=None,
        description="Telegram bot API token (optional)",
    )
    telegram_chat_id: Optional[str] = Field(
        default=None,
        description="Telegram destination chat ID (optional)",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("watchlist", mode="before")
    @classmethod
    def parse_and_dedupe_watchlist(cls, value: object) -> list[str]:
        """Parse comma-separated strings or list, and deduplicate with warning."""
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, (list, tuple)):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            items = list(DEFAULT_WATCHLIST)

        seen = set()
        deduped = []
        duplicates = []
        for item in items:
            if item in seen:
                duplicates.append(item)
            else:
                seen.add(item)
                deduped.append(item)

        if duplicates:
            logger.warning("Duplicate watchlist entries detected and removed: %s", duplicates)

        return deduped


def get_settings() -> Settings:
    """Factory helper to obtain a singleton or fresh Settings instance."""
    return Settings()
