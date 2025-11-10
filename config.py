# config.py — безопасная конфигурация через .env

from dotenv import load_dotenv
import os

# Загрузить переменные из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Проверка, чтобы не было пустых значений
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задан в .env")
