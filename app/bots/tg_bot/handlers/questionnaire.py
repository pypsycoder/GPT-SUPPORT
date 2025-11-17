from aiogram import Router
from app.scales.fsm.questionnaire import router as questionnaire_fsm_router

# Экспортируем под нужным именем
router = Router()
router.include_router(questionnaire_fsm_router)
