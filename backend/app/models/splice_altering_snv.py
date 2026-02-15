from sqlalchemy import Column, String, Integer, Text, CHAR
from app.core.database import Base

class SpliceAlteringSNV(Base):
    __tablename__ = "splice_altering_snv"

    disease_id = Column(Text, primary_key=True, index=True)
    gene_id = Column(Text, index=True)
    pos_gene0 = Column(Integer)  # 서열 내 위치
    ref = Column(CHAR(1))         # 야생형(정상) 염기
    alt = Column(CHAR(1))         # 변이 염기
    note = Column(Text)          # 추가 정보 (chr, pos 등)