from aiogram import Dispatcher

from app.bots.tg_bot.handlers import start, consent, questionnaire


def register_user_routes(dp: Dispatcher):
    dp.include_routers(
        start.router,
        consent.router,
        questionnaire.router,  # ⬅️ подключаем FSM шкалы
    )
