# ============================================
# [DEPRECATED] Telegram Bot: Reply-клавиатуры (старые)
# ============================================
# Не используются. Заменены inline-клавиатурами (inline.py).
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Шкалы")],
            [KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="📚 Обучение")],
            [KeyboardButton(text="📒 Дневник")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел…"
    )


def back_home_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="🏠 Меню")]],
        resize_keyboard=True
    )


def scales_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="HADS")],
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="🏠 Меню")],
        ],
        resize_keyboard=True
    )


def profile_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Согласие")],
            [KeyboardButton(text="Мои данные")],
            [KeyboardButton(text="Настройки")],
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="🏠 Меню")],
        ],
        resize_keyboard=True
    )


def learning_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Нефрология")],
            [KeyboardButton(text="Психология")],
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="🏠 Меню")],
        ],
        resize_keyboard=True
    )


def diary_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Ввести пульс")],
            [KeyboardButton(text="📈 Статистика 7 дней")],
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="🏠 Меню")],
        ],
        resize_keyboard=True
    )
