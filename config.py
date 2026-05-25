from app.core.config import settings


BOT_TOKEN = settings.require_bot_token()
DATABASE_URL = settings.require_database_url()
