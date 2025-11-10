# start_keyboard.py — кнопки для начального экрана
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def start_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Пройти шкалу HADS")],
            [KeyboardButton(text="📈 Внести показатели")]
        ],
        resize_keyboard=True
    )
