"""API service configuration."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from shared.config import BaseServiceConfig


class APIConfig(BaseServiceConfig):
    """Configuration for the API service."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")
