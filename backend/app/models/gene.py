from sqlalchemy import Column, Text, Integer, CHAR
from app.core.database import Base

class Gene(Base):
    __tablename__ = "gene"
    
    gene_id = Column(Text, primary_key=True)
    gene_symbol = Column(Text, nullable=False)
    chromosome = Column(Text)
    strand = Column(CHAR(1))
    length = Column(Integer)
    exon_count = Column(Integer)
    canonical_transcript_id = Column(Text)
    canonical_source = Column(Text)
    source_version = Column(Text)