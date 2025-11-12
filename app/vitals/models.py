from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.models import Base


class VitalMeasurement(Base):
    """Таблица витальных показателей, связанных с пользователями по FK."""
    __tablename__ = "measurements"
    __table_args__ = {"schema": "vitals"}

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    bp_sys = Column(Integer)
    bp_dia = Column(Integer)
    pulse = Column(Integer)
    fluid_intake = Column(Numeric)
    measured_at = Column(DateTime, server_default=func.now())
