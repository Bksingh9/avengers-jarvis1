"""Global runtime settings.

Only process-wide concerns live here. Tenant-scoped settings come from
`config/tenants/*.yaml` via the config loader.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AVENGERS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARN", "ERROR"] = "INFO"
    config_dir: Path = Field(default=Path("config"))
    prompts_dir: Path = Field(default=Path("prompts"))
    region: str = "us-east-1"
    enable_audit: bool = True

    # Defaults used by adapters that don't have tenant-specific overrides:
    default_llm_timeout_s: float = 30.0
    default_max_tokens_out: int = 4_000


def get_settings() -> Settings:
    return Settings()
