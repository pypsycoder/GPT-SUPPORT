from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def consent_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Я согласен", callback_data="consent_yes"),
            InlineKeyboardButton(text="❌ Я не согласен", callback_data="consent_no"),
        ]
    ])
