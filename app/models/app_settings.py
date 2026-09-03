"""
Универсальное key/value-хранилище рантайм-настроек — тумблеры админ-панели,
которые нельзя держать в ``.env`` (меняются на живой системе, без рестарта).

Схема: public. Одна строка = одна настройка. ``value`` — TEXT (сериализация на
стороне вызывающего: строка / "true" / JSON). Читать и писать через
``app.core.app_settings`` (get_setting / set_setting), не трогать таблицу напрямую.

Первый потребитель — ``llm_provider`` (``sber`` | ``cloudru``), переключатель
LLM-провайдера в researcher-панели (см. ``app/llm/pool.py`` Фаза 6).
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = {"schema": "public"}

    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("NOW()"),
        onupdate=sa.func.now(),
    )
    updated_by: Mapped[str | None] = mapped_column(
        sa.String(128), nullable=True, comment="кто менял (researcher.username)"
    )
