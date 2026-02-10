"""Configuration loader for ATS Optimizer."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


# Project root is one level above src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///data/ats_optimizer.db"


class LLMConfig(BaseModel):
    provider: str = "stub"
    model: str = "llama3"
    api_key: str | None = None
    base_url: str = "http://localhost:11434"


class BrowserConfig(BaseModel):
    engine: str = "playwright"
    headless: bool = True
    user_data_dir: str = "data/browser_profiles"


class NotificationsConfig(BaseModel):
    enabled: bool = False
    method: str = "desktop"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


class ScoringConfig(BaseModel):
    auto_apply_threshold: int = 70
    min_ats_score: int = 70
    max_retry_generations: int = 2


class AppConfig(BaseModel):
    name: str = "ATS Optimizer"
    version: str = "1.0.0"


class Config(BaseModel):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    llm: LLMConfig = LLMConfig()
    browser: BrowserConfig = BrowserConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    scoring: ScoringConfig = ScoringConfig()


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from YAML file, falling back to defaults."""
    if config_path is None:
        config_path = PROJECT_ROOT / "config" / "app.yaml"

    if config_path.exists():
        with open(config_path, "r") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return Config(**raw)

    return Config()


# Global config singleton
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance (lazy-loaded)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
