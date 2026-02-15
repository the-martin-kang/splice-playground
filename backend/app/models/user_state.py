import uuid
from sqlalchemy import Column, Text, ForeignKey, JSON, DateTime
from sqlalchemy.sql import func
from app.core.database import Base

class UserState(Base):
    __tablename__ = "user_state"
    
    state_id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    disease_id = Column(Text, ForeignKey("disease.disease_id"), nullable=False)
    parent_state_id = Column(Text, ForeignKey("user_state.state_id"), nullable=True) # 히스토리 추적용
    applied_edit = Column(JSON, nullable=False) # {type: 'substitute', pos: 125, ref: 'A', alt: 'T'}
    created_at = Column(DateTime(timezone=True), server_default=func.now())