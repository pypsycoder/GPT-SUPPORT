from app.core.config import settings


DATABASE_URL = settings.require_database_url()
