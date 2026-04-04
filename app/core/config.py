from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = ".env"
VALID_ENVIRONMENTS = {"dev", "test", "prod"}


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_environment(*, env_file: str | None = None, override: bool = False) -> Path:
    """Load environment variables once from an explicit bootstrap entrypoint."""
    env_name = env_file or os.getenv("ENV_FILE") or DEFAULT_ENV_FILE
    env_path = Path(env_name)
    if not env_path.is_absolute():
        env_path = BASE_DIR / env_name

    if env_path.exists():
        load_dotenv(env_path, override=override)

    return env_path


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    database_url: str
    bot_token: str | None
    scheduler_enabled: bool
    scheduler_lock_id: int
    csrf_enabled: bool

    @property
    def is_dev(self) -> bool:
        return self.environment == "dev"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"

    def require_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required")
        return self.database_url

    def require_bot_token(self) -> str:
        if not self.bot_token:
            raise RuntimeError("BOT_TOKEN is required")
        return self.bot_token


def _read_environment() -> str:
    value = os.getenv("ENVIRONMENT", "dev").strip().lower()
    if value not in VALID_ENVIRONMENTS:
        raise RuntimeError(
            "ENVIRONMENT must be one of: dev, test, prod"
        )
    return value


def _read_scheduler_lock_id() -> int:
    raw_value = os.getenv("SCHEDULER_LOCK_ID", "4815162342").strip()
    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError("SCHEDULER_LOCK_ID must be an integer") from exc


def build_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "GPT Health Support"),
        environment=_read_environment(),
        database_url=os.getenv("DATABASE_URL", "").strip(),
        bot_token=os.getenv("BOT_TOKEN", "").strip() or None,
        scheduler_enabled=_parse_bool(os.getenv("SCHEDULER_ENABLED"), default=False),
        scheduler_lock_id=_read_scheduler_lock_id(),
        csrf_enabled=_parse_bool(os.getenv("CSRF_ENABLED"), default=False),
    )


class SettingsProxy:
    def __getattr__(self, item: str):
        return getattr(build_settings(), item)


settings = SettingsProxy()
