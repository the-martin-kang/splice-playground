from sqlalchemy import Column, Text, Integer, ForeignKey, CHAR
from sqlalchemy.orm import relationship
from app.core.database import Base

class DiseaseRepresentativeSNV(Base):
    __tablename__ = "disease_representative_snv"
    
    disease_id = Column(Text, ForeignKey("disease.disease_id"), primary_key=True)
    gene_id = Column(Text, ForeignKey("gene.gene_id"))
    pos_gene0 = Column(Integer, nullable=False)
    ref = Column(CHAR(1), nullable=False)
    alt = Column(CHAR(1), nullable=False)
    note = Column(Text) # 'chr=chr7;pos1=117589467' 정보 저장

    disease = relationship("Disease", back_populates="snvs")