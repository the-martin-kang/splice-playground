import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from sqlalchemy.orm import Session
from app.crud import disease as crud
from app.core.database import get_db
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.models.user_state import UserState
from app.models.region import Region

router = APIRouter()

# --- 1. 스키마 정의 (Pydantic V2) ---

class SingleEdit(BaseModel):
    pos: int = Field(109442, description="변이 위치 (0-based index)")
    
    # alias를 설정하여 JSON 상에서는 'from', 'to'로 통신
    from_base: str = Field(..., alias="from", description="원래 염기")
    to_base: str = Field(..., alias="to", description="바꿀 염기")

    # [중요] populate_by_name 설정을 통해 'from_base'와 'from' 모두 수용
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "pos": 109442,
                "from": "A",
                "to": "G"
            }
        }
    )

    @field_validator('to_base', 'from_base')
    @classmethod
    def validate_bases(cls, v: str) -> str:
        allowed = {'A', 'C', 'G', 'T', 'N'}
        v = v.upper()
        if v not in allowed:
            raise ValueError(f"염기는 {allowed} 중 하나여야 합니다.")
        return v

class MultiEditPayload(BaseModel):
    type: str = "user"
    # 기본값을 빈 리스트로 설정하여 스마트 자동 완성 유도
    edits: List[SingleEdit] = Field(default_factory=list, description="비워두면 해당 질병의 기본 변이 정보가 자동 적용됩니다.")

class StateCreate(BaseModel):
    parent_state_id: Optional[str] = None
    applied_edit: MultiEditPayload = Field(default_factory=MultiEditPayload)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "parent_state_id": None,
                "applied_edit": {
                    "type": "user",
                    "edits": []
                }
            }
        }
    )

# --- 2. 엔드포인트 ---

@router.get("/")
def read_diseases(db: Session = Depends(get_db)):
    """모든 질병 목록을 조회합니다."""
    diseases = crud.get_diseases(db)
    return {"items": diseases}

@router.get("/{disease_id}")
def read_disease_detail(disease_id: str, db: Session = Depends(get_db)):
    """
    질병, 유전자, SNV 및 주변 Region 정보를 조립한 상세 데이터를 반환합니다.
    """
    decoded_id = urllib.parse.unquote(disease_id)
    
    # crud/disease.py에서 새로 만든 '전체 정보 조립' 함수 호출
    detail = crud.get_disease_detail_full(db, decoded_id)
    
    if not detail:
        raise HTTPException(status_code=404, detail="Disease not found")
        
    return detail

@router.get("/{disease_id}/sequence-window")
def get_sequence_window(
    disease_id: str, 
    state_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """특정 상태(state_id)가 반영된 주변 서열 윈도우를 가져옵니다."""
    decoded_id = urllib.parse.unquote(disease_id)
    
    # 기초 데이터 확보
    detail = crud.get_disease_detail_full(db, decoded_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Disease not found")

    seed_snv = detail["splice_altering_snv"]
    target_pos = seed_snv["pos_gene0"]
    
    # 현재 질병의 모든 Region 가져오기
    gene_id = detail["gene"]["gene_id"]
    all_regions = db.query(Region).filter(Region.gene_id == gene_id).order_by(Region.region_number).all()
    
    # 중심점 계산
    focus_idx = next((i for i, r in enumerate(all_regions) 
                      if r.gene_start_idx <= target_pos < r.gene_end_idx), 0)
    
    # 앞뒤 2개씩 총 5개 Region 선택
    start_idx = max(0, focus_idx - 2)
    end_idx = min(len(all_regions), focus_idx + 3)
    target_regions = all_regions[start_idx:end_idx]

    # 사용자의 추가 편집 정보 로드
    user_edits = []
    if state_id:
        state = db.query(UserState).filter(UserState.state_id == state_id).first()
        if state and isinstance(state.applied_edit, dict):
            user_edits = state.applied_edit.get("edits", [])

    # 서열 수정 반영 루프
    processed_regions = []
    for r in target_regions:
        seq_list = list(r.sequence)
        
        # 1. 기본 Seed SNV 반영
        if r.gene_start_idx <= target_pos < r.gene_end_idx:
            seq_list[target_pos - r.gene_start_idx] = seed_snv["alt"]

        # 2. 사용자 추가 편집(다중) 반영
        for edit in user_edits:
            e_pos = int(edit.get("pos", -1))
            if r.gene_start_idx <= e_pos < r.gene_end_idx:
                new_base = edit.get("to", "").upper()
                if new_base in {'A', 'C', 'G', 'T', 'N'}:
                    seq_list[e_pos - r.gene_start_idx] = new_base

        processed_regions.append({
            "region_id": r.region_id,
            "region_type": r.region_type,
            "region_number": r.region_number,
            "sequence": "".join(seq_list),
            "gene_start_idx": r.gene_start_idx,
            "gene_end_idx": r.gene_end_idx,
            "is_target": (r.gene_start_idx <= target_pos < r.gene_end_idx)
        })

    return {"disease_id": decoded_id, "regions": processed_regions}

@router.post("/{disease_id}/states")
def save_user_edit(
    disease_id: str, 
    payload: StateCreate, 
    db: Session = Depends(get_db)
):
    """사용자 편집 상태를 저장하며, 비어있을 시 자동 완성합니다."""
    decoded_id = urllib.parse.unquote(disease_id)
    
    # 스마트 자동 완성 로직
    if not payload.applied_edit.edits:
        # crud의 기본 데이터 조회 함수 사용 (호환성 유지)
        snv_info = crud.get_disease_detail_data(db, decoded_id)
        if snv_info and snv_info.get("seed_snv"):
            seed = snv_info["seed_snv"]
            payload.applied_edit.edits.append(
                SingleEdit(
                    pos=int(seed.pos_gene0), 
                    from_base=seed.ref, 
                    to_base=seed.alt
                )
            )
        else:
            raise HTTPException(status_code=404, detail="기본 변이 정보를 찾을 수 없습니다.")

    # DB 저장
    applied_edit_dict = payload.applied_edit.model_dump(by_alias=True)
    new_state = crud.create_user_state(
        db, 
        disease_id=decoded_id, 
        parent_state_id=payload.parent_state_id, 
        applied_edit=applied_edit_dict
    )
    
    return {
        "state_id": new_state.state_id,
        "message": "스마트 자동 완성이 적용되었습니다.",
        "applied_data": applied_edit_dict
    }