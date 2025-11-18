from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# # Главное меню (inline)
def main_menu_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧪 Шкалы", callback_data="menu:scales")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile")],
        [InlineKeyboardButton(text="📚 Обучение", callback_data="menu:learning")],
        [InlineKeyboardButton(text="📊 Показатели", callback_data="menu:vitals")],
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

def vitals_menu_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💪 Давление", callback_data="vitals:bp")],
        [InlineKeyboardButton(text="💓 Пульс", callback_data="vitals:pulse")],
        [InlineKeyboardButton(text="⚖️ Вес", callback_data="vitals:weight")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="nav:home"),
        ]
    ])

def bp_context_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="До диализа", callback_data="vitals:bp_ctx:pre_hd")],
        [InlineKeyboardButton(text="После диализа", callback_data="vitals:bp_ctx:post_hd")],
        [InlineKeyboardButton(text="Дома", callback_data="vitals:bp_ctx:home")],
        [InlineKeyboardButton(text="В клинике", callback_data="vitals:bp_ctx:clinic")],
        [InlineKeyboardButton(text="Не важно", callback_data="vitals:bp_ctx:na")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="nav:home"),
        ],
    ])

def weight_context_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="До диализа", callback_data="vitals:weight_ctx:pre_hd")],
        [InlineKeyboardButton(text="После диализа", callback_data="vitals:weight_ctx:post_hd")],
        [InlineKeyboardButton(text="Дома утром", callback_data="vitals:weight_ctx:home_morning")],
        [InlineKeyboardButton(text="Дома вечером", callback_data="vitals:weight_ctx:home_evening")],
        [InlineKeyboardButton(text="Не важно", callback_data="vitals:weight_ctx:na")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="nav:home"),
        ]
    ])

def pulse_context_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="До диализа", callback_data="vitals:pulse_ctx:pre_hd")],
        [InlineKeyboardButton(text="После диализа", callback_data="vitals:pulse_ctx:post_hd")],
        [InlineKeyboardButton(text="Дома", callback_data="vitals:pulse_ctx:home")],
        [InlineKeyboardButton(text="В клинике", callback_data="vitals:pulse_ctx:clinic")],
        [InlineKeyboardButton(text="Не важно", callback_data="vitals:pulse_ctx:na")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="nav:home"),
        ]
    ])
