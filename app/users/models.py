# models.py — SQLAlchemy модели пользователя
from sqlalchemy import Column, Integer, String, Boolean
#from sqlalchemy.orm import declarative_base
from app.models import Base  # 👈 используем общий


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "users"}

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    full_name = Column(String)
    consent_personal_data = Column(Boolean, default=False)
    consent_bot_use = Column(Boolean, default=False)