from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from sqlalchemy.orm import Session
from app.crud import disease as crud
from app.core.database import get_db
from pydantic import BaseModel, Field
from app.models.user_state import UserState
from app.models.region import Region

router = APIRouter()

# --- 스키마 정의 ---
class StateCreate(BaseModel):
    parent_state_id: Optional[str] = Field(None, description="이전 상태의 ID (없으면 null)")
    applied_edit: dict = Field(
        default={
            "pos_gene0": 109442,
            "ref": "A",
            "alt": "G",
            "type": "substitute"
        }
    )

    class Config:
        json_schema_extra = {
            "example": {
                "parent_state_id": None,
                "applied_edit": {
                    "pos_gene0": 109442,
                    "ref": "A",
                    "alt": "G",
                    "type": "substitute"
                }
            }
        }

# --- 엔드포인트 ---

@router.get("/")
def read_diseases(db: Session = Depends(get_db)):
    diseases = crud.get_diseases(db)
    return {"items": diseases}

@router.get("/{disease_id}")
def read_disease_detail(disease_id: str, db: Session = Depends(get_db)):
    detail = crud.get_disease_detail_data(db, disease_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Disease not found")
    return detail

# [신규] 특정 리전(Exon/Intron)의 정보만 전문적으로 가져오는 엔드포인트
@router.get("/{disease_id}/regions/{region_type}/{region_num}")
def get_specific_region(
    disease_id: str,
    region_type: str, # 'exon' 또는 'intron'
    region_num: str,
    db: Session = Depends(get_db)
):
    # 1. 질병 정보 확인
    snv_info = crud.get_disease_detail_data(db, disease_id)
    if not snv_info:
        raise HTTPException(status_code=404, detail="Disease not found")
    
    # 2. 특정 리전 조회
    target_region = db.query(Region).filter(
        Region.gene_id == snv_info["seed_snv"].gene_id,
        Region.region_type == region_type,
        Region.region_number == str(region_num)
    ).first()

    if not target_region:
        raise HTTPException(status_code=404, detail=f"{region_type} {region_num} not found")

    return {
        "disease_id": disease_id,
        "region_type": target_region.region_type,
        "region_number": target_region.region_number,
        "gene_start_idx": target_region.gene_start_idx,
        "gene_end_idx": target_region.gene_end_idx,
        "length": target_region.gene_end_idx - target_region.gene_start_idx,
        "sequence": target_region.sequence
    }

# 기존 윈도우 조회는 '좌표 기반' 탐색에 집중하도록 유지
@router.get("/{disease_id}/sequence-window")
def get_sequence_window(
    disease_id: str, 
    center: Optional[int] = Query(None), 
    radius: int = Query(200),
    state_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    snv_info = crud.get_disease_detail_data(db, disease_id)
    if not snv_info:
        raise HTTPException(status_code=404, detail="Disease not found")

    seed_snv = snv_info["seed_snv"]
    center = center if center is not None else seed_snv.pos_gene0
    start = max(0, center - radius)
    end = center + radius + 1

    data = crud.get_sequence_window_data(db, disease_id, start, end)
    
    user_edit = None
    if state_id:
        user_edit = db.query(UserState).filter(UserState.state_id == state_id).first()

    processed_regions = []
    for r in data["regions"]:
        visible_start = max(r.gene_start_idx, start)
        visible_end = min(r.gene_end_idx, end)
        if visible_start >= visible_end: continue
            
        current_sequence = r.sequence[visible_start - r.gene_start_idx : visible_end - r.gene_start_idx]

        # SNV 반영 (Baseline -> Disease)
        if visible_start <= seed_snv.pos_gene0 < visible_end:
            seq_list = list(current_sequence)
            seq_list[seed_snv.pos_gene0 - visible_start] = seed_snv.alt 
            current_sequence = "".join(seq_list)

        processed_regions.append({
            "region_id": r.region_id,
            "region_type": r.region_type,
            "region_number": r.region_number,
            "sequence": current_sequence, 
            "gene_start_idx": visible_start,
            "gene_end_idx": visible_end
        })

    return {
        "window": {"start": start, "end": end, "center": center},
        "regions": processed_regions
    }

@router.post("/{disease_id}/states")
def save_user_edit(disease_id: str, payload: StateCreate, db: Session = Depends(get_db)):
    new_state = crud.create_user_state(
        db, 
        disease_id=disease_id, 
        parent_state_id=payload.parent_state_id, 
        applied_edit=payload.applied_edit
    )
    return {"state_id": new_state.state_id}