from pydantic import BaseModel
from typing import List, Optional

class DiseaseBase(BaseModel):
    disease_id: str
    disease_name: str
    image_path: Optional[str] = None

    class Config:
        from_attributes = True

class DiseaseListResponse(BaseModel):
    items: List[DiseaseBase]

class GeneInfo(BaseModel):
    gene_id: str
    gene_symbol: str
    chromosome: Optional[str]
    exon_count: int

    class Config:
        from_attributes = True

class SNVInfo(BaseModel):
    pos_gene0: int
    ref: str
    alt: str

    class Config:
        from_attributes = True

class DiseaseDetailResponse(BaseModel):
    disease: DiseaseBase
    gene: Optional[GeneInfo] = None
    seed_snv: Optional[SNVInfo] = None