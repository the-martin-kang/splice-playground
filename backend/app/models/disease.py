from sqlalchemy import Column, String, Integer, ForeignKey, Text, CHAR
from sqlalchemy.orm import relationship
from app.core.database import Base

class Disease(Base):
    __tablename__ = "disease"
    disease_id = Column(Text, primary_key=True)
    disease_name = Column(Text, nullable=False)
    description = Column(Text)
    image_path = Column(Text)

    # 2. 이 부분을 추가하세요! (back_populates의 이름이 snv 모델과 일치해야 함)
    snvs = relationship("DiseaseRepresentativeSNV", back_populates="disease")