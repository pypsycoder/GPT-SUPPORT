"""Reply-keyboard helpers for quick actions after /start."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def reply_start_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Пройти шкалу HADS")],
            [KeyboardButton(text="📈 Внести показатели")],
        ],
        resize_keyboard=True,
    )
