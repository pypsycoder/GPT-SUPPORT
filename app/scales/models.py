from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
#from sqlalchemy.orm import declarative_base
from datetime import datetime
from app.models import Base



class ScaleResponse(Base):
    __tablename__ = "responses"
    __table_args__ = {"schema": "scales"}

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    scale_code = Column(String, nullable=False)
    version = Column(String, default="1.0")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    raw_answers = Column(JSON)
    result = Column(JSON)
    interpretation = Column(String)

class ScaleDraft(Base):
    __tablename__ = "drafts"
    __table_args__ = {"schema": "scales"}

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    scale_code = Column(String)
    current_index = Column(Integer)
    answers = Column(JSON)
    started_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
