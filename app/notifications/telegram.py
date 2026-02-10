"""Утилиты для отправки уведомлений в Telegram.

В дальнейшем здесь появится интеграция с Telegram Bot API или aiogram.
Сейчас функции — заглушки и не используются в продакшн-коде.
"""

from typing import Optional


def send_telegram_message(chat_id: str, text: str, url_button: Optional[str] = None) -> None:
    """
    Заглушка для отправки уведомлений в Telegram.

    :param chat_id: ID чата или пользователя в Telegram
    :param text: Текст сообщения
    :param url_button: Необязательная URL-кнопка
    """
    # TODO: реализовать реальную отправку сообщений через Telegram Bot API
    return
