from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# # Главное меню (inline)
def main_menu_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧪 Шкалы", callback_data="menu:scales")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile")],
        [InlineKeyboardButton(text="📚 Обучение", callback_data="menu:learning")],
        [InlineKeyboardButton(text="📒 Дневник", callback_data="menu:diary")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
    ])

def back_home_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="nav:home"),
        ]
    ])

def scales_menu_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="HADS", callback_data="scales:hads")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="nav:home"),
        ]
    ])

def profile_menu_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Согласие", callback_data="profile:consent")],
        [InlineKeyboardButton(text="Мои данные", callback_data="profile:data")],
        [InlineKeyboardButton(text="Настройки", callback_data="profile:settings")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="nav:home"),
        ]
    ])

def learning_menu_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Нефрология", callback_data="learn:neph")],
        [InlineKeyboardButton(text="Психология", callback_data="learn:psy")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="nav:home"),
        ]
    ])

def diary_menu_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Ввести пульс", callback_data="diary:add_pulse")],
        [InlineKeyboardButton(text="📈 Статистика 7 дней", callback_data="diary:stats")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="nav:home"),
        ]
    ])
