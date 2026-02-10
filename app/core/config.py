# app/core/config.py
# Базовая конфигурация проекта без pydantic-settings.
# Читает .env и предоставляет единый объект settings.

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Определяем корень проекта (папка GPT-SUPPORT)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Грузим .env из корня проекта
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Можно залогировать предупреждение, но не падаем
    print(f"[config] WARNING: .env not found at {env_path}")


@dataclass
class Settings:
    """Простые настройки проекта, читаемые из переменных окружения."""
    app_name: str = os.getenv("APP_NAME", "GPT Health Support")
    environment: str = os.getenv("ENVIRONMENT", "dev")
    database_url: str = os.getenv("DATABASE_URL", "")

    # позже сюда можно добавить:
    # telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")


# Глобальный объект настроек
settings = Settings()
