from sqlalchemy import Column, Text, Integer
from app.core.database import Base

class Region(Base):
    __tablename__ = "region"
    
    region_id = Column(Text, primary_key=True)
    gene_id = Column(Text)
    region_type = Column(Text)      # 'exon', 'intron'
    region_number = Column(Integer)
    gene_start_idx = Column(Integer)
    gene_end_idx = Column(Integer)
    length = Column(Integer)
    sequence = Column(Text)
    cds_start_offset = Column(Integer, nullable=True)
    cds_end_offset = Column(Integer, nullable=True)