from sqlalchemy import Column, String, ForeignKey
from app.core.database import Base

class DiseaseGene(Base):
    __tablename__ = "disease_gene"

    disease_id = Column(String, ForeignKey("disease.disease_id"), primary_key=True)
    gene_id = Column(String, ForeignKey("gene.gene_id"), primary_key=True)
