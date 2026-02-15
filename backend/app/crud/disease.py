import os
import uuid
from sqlalchemy.orm import Session
from app.models.disease import Disease
from app.models.gene import Gene
from app.models.disease_gene import DiseaseGene
from app.models.disease_representative_snv import DiseaseRepresentativeSNV
from app.models.region import Region
from app.models.user_state import UserState

def get_valid_image_url(image_filename: str) -> str:
    """
    파일명이 없거나 파일이 서버에 존재하지 않을 경우 default.png 경로를 반환합니다.
    """
    current_dir = os.path.dirname(os.path.realpath(__file__)) # app/crud
    app_dir = os.path.dirname(current_dir) # app
    static_disease_dir = os.path.join(app_dir, "static", "diseases")
    
    if not image_filename or image_filename.strip() == "":
        return "/static/diseases/default.png"
        
    full_path = os.path.join(static_disease_dir, image_filename)
    if os.path.exists(full_path):
        return f"/static/diseases/{image_filename}"
    
    return "/static/diseases/default.png"

# 질병 목록 조회
def get_diseases(db: Session):
    diseases = db.query(Disease).all()
    for d in diseases:
        d.image_path = get_valid_image_url(d.image_path)
    return diseases

# 질병 상세 정보 조회 (기존 로직 유지)
def get_disease_detail_data(db: Session, disease_id: str):
    disease = db.query(Disease).filter(Disease.disease_id == disease_id).first()
    if not disease:
        return None 
    
    disease.image_path = get_valid_image_url(disease.image_path)
    
    # DiseaseGene을 통해 Gene 정보 조회
    dg = db.query(DiseaseGene).filter(DiseaseGene.disease_id == disease_id).first()
    gene_info = None
    if dg and dg.gene_id:
        gene_info = db.query(Gene).filter(Gene.gene_id == dg.gene_id).first()
    
    snv_info = db.query(DiseaseRepresentativeSNV).filter(
        DiseaseRepresentativeSNV.disease_id == disease_id
    ).first()
    
    return {
        "disease": disease,
        "gene": gene_info,
        "seed_snv": snv_info
    }

# 윈도우 기반 서열 및 리전 조회 함수
def get_sequence_window_data(db: Session, disease_id: str, start: int, end: int):
    """
    특정 질병의 SNV 정보를 바탕으로 해당 범위(start~end) 내의 Region(Exon/Intron)들을 가져옵니다.
    """
    # 질병 및 SNV 기본 정보 조회
    snv_info = db.query(DiseaseRepresentativeSNV).filter(
        DiseaseRepresentativeSNV.disease_id == disease_id
    ).first()
    
    if not snv_info:
        return None, None

    disease = db.query(Disease).filter(Disease.disease_id == disease_id).first()
    if disease:
        disease.image_path = get_valid_image_url(disease.image_path)

    # 해당 유전자의 범위 내 Region들 조회
    regions = db.query(Region).filter(
        Region.gene_id == snv_info.gene_id,
        Region.gene_start_idx <= end,
        Region.gene_end_idx >= start
    ).order_by(Region.gene_start_idx).all()

    return {
        "disease": disease,
        "seed_snv": snv_info,
        "regions": regions
    }

def create_user_state(db: Session, disease_id: str, applied_edit: dict, parent_state_id: str = None):
    """
    유저의 편집 상태를 DB에 저장합니다.
    """
    # 새로운 UUID 생성
    new_state_id = str(uuid.uuid4())
    
    db_state = UserState(
        state_id=new_state_id,
        disease_id=disease_id,
        parent_state_id=parent_state_id,
        applied_edit=applied_edit
    )
    
    db.add(db_state)
    db.commit()
    db.refresh(db_state)
    return db_state