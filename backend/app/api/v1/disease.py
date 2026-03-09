import urllib.parse
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from sqlalchemy.orm import Session
from app.crud import disease as crud
from app.core.database import get_db
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.models.user_state import UserState
from app.models.region import Region

# 1단계/2단계에서 만든 예측기 로드
from app.services.splice_service import SplicePredictor

router = APIRouter()

# 전역 변수로 예측기 초기화
predictor = SplicePredictor("spliceAI_v1_4000_2000.pt")

# --- 1. 스키마 정의 ---
class SingleEdit(BaseModel):
    pos: int = Field(..., description="변이 위치 (0-based index)")
    from_base: str = Field(..., alias="from", description="원래 염기")
    to_base: str = Field(..., alias="to", description="바꿀 염기")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"pos": 109442, "from": "A", "to": "G"}}
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
    edits: List[SingleEdit] = Field(default_factory=list)

class StateCreate(BaseModel):
    parent_state_id: Optional[str] = None
    applied_edit: MultiEditPayload = Field(default_factory=MultiEditPayload)

# --- 2. 헬퍼 함수 (최적화 로직) ---

def get_significant_scores(delta_array, mutant_probs, start_offset, threshold=0.01):
    """
    변화량(Delta)의 절대값이 threshold 이상인 지점만 필터링하여 추출합니다.
    """
    # 임계값 이상의 인덱스 추출
    sig_indices = np.where(np.abs(delta_array) > threshold)[0]
    
    results = []
    for idx in sig_indices:
        results.append({
            "pos": int(start_offset + idx), # 절대 좌표 계산
            "delta": round(float(delta_array[idx]), 4),
            "prob": round(float(mutant_probs[idx]), 4)
        })
    return results

# --- 3. 엔드포인트 ---

@router.get("/")
def read_diseases(db: Session = Depends(get_db)):
    diseases = crud.get_diseases(db)
    return {"items": diseases}

@router.get("/{disease_id}")
def read_disease_detail(disease_id: str, db: Session = Depends(get_db)):
    decoded_id = urllib.parse.unquote(disease_id)
    detail = crud.get_disease_detail_full(db, decoded_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Disease not found")
    return detail

@router.get("/diseases/{disease_id}/sequence-window")
def get_sequence_window(
    disease_id: str, 
    state_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    사용자의 편집 상태(state_id)가 반영된 주변 서열 윈도우를 가져옵니다.
    삭제된 염기는 'N'으로 표시되어 길이를 고정합니다.
    """
    decoded_id = urllib.parse.unquote(disease_id)
    detail = crud.get_disease_detail_full(db, decoded_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Disease not found")

    seed_snv = detail["splice_altering_snv"]
    target_pos = seed_snv["pos_gene0"]
    gene_id = detail["gene"]["gene_id"]
    
    # 1. 주변 Region들 가져오기 (Target 포함 앞뒤 2개씩, 총 5개)
    all_regions = db.query(Region).filter(Region.gene_id == gene_id).order_by(Region.gene_start_idx).all()
    focus_idx = next((i for i, r in enumerate(all_regions) if r.gene_start_idx <= target_pos < r.gene_end_idx), 0)
    target_regions = all_regions[max(0, focus_idx - 2):focus_idx + 3]

    # 2. 사용자 편집 데이터(state_id) 가져오기
    user_edits = []
    if state_id:
        state = db.query(UserState).filter(UserState.state_id == state_id).first()
        if state and isinstance(state.applied_edit, dict):
            user_edits = state.applied_edit.get("edits", [])

    processed_regions = []
    for r in target_regions:
        seq_list = list(r.sequence)
        
        # A. 기본 환자 변이(Seed SNV) 반영
        if r.gene_start_idx <= target_pos < r.gene_end_idx:
            seq_list[target_pos - r.gene_start_idx] = seed_snv["alt"]
            
        # B. 사용자 추가 편집 반영 (길이 고정 로직)
        for edit in user_edits:
            e_pos = int(edit.get("pos", -1))
            if r.gene_start_idx <= e_pos < r.gene_end_idx:
                new_base = edit.get("to", "").upper()
                
                # 핵심: 삭제 버튼을 눌러 빈 값이 오면 'N'으로 치환하여 길이 유지
                if new_base == "" or new_base == "N":
                    seq_list[e_pos - r.gene_start_idx] = "N"
                else:
                    seq_list[e_pos - r.gene_start_idx] = new_base

        processed_regions.append({
            "region_id": r.region_id,
            "region_type": r.region_type,
            "region_number": r.region_number,
            "sequence": "".join(seq_list), # 길이는 r.sequence와 동일함
            "gene_start_idx": r.gene_start_idx,
            "gene_end_idx": r.gene_end_idx,
            "is_target": (r.gene_start_idx <= target_pos < r.gene_end_idx)
        })

    return {
        "disease_id": decoded_id, 
        "state_id": state_id,
        "regions": processed_regions
    }

@router.get("/{disease_id}/splicing/predict")
def get_splicing_prediction(
    disease_id: str,
    state_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    정상 대비 변이 서열의 스플라이싱 변화를 예측합니다. (유의미한 지점만 반환)
    """
    decoded_id = urllib.parse.unquote(disease_id)
    detail = crud.get_disease_detail_full(db, decoded_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Disease not found")

    # 1. 서열 조립
    gene_id = detail["gene"]["gene_id"]
    full_seq, start_offset = crud.get_full_gene_sequence(db, gene_id)
    
    # 2. Baseline(정상) 예측
    baseline_probs = predictor.predict(full_seq) # [3, L]

    # 3. 변이 서열 생성
    mut_seq_list = list(full_seq)
    snv = detail["splice_altering_snv"]
    mut_seq_list[snv["pos_gene0"] - start_offset] = snv["alt"]
    
    if state_id:
        state = db.query(UserState).filter(UserState.state_id == state_id).first()
        if state:
            edits = state.applied_edit.get("edits", [])
            for edit in edits:
                rel_pos = int(edit["pos"]) - start_offset
                if 0 <= rel_pos < len(mut_seq_list):
                    mut_seq_list[rel_pos] = edit["to"].upper()
    
    mutated_seq = "".join(mut_seq_list)
    mutant_probs = predictor.predict(mutated_seq) # [3, L]

    # 4. Delta 계산 (Mutant - Baseline)
    delta_acceptor = mutant_probs[1] - baseline_probs[1]
    delta_donor = mutant_probs[2] - baseline_probs[2]

    # 5. 유의미한 지점 필터링 (최적화 핵심)
    sig_acceptors = get_significant_scores(delta_acceptor, mutant_probs[1], start_offset, threshold=0.01)
    sig_donors = get_significant_scores(delta_donor, mutant_probs[2], start_offset, threshold=0.01)

    return {
        "disease_id": decoded_id,
        "state_id": state_id,
        "summary": {
            "total_gene_length": len(full_seq),
            "sig_acceptor_count": len(sig_acceptors),
            "sig_donor_count": len(sig_donors)
        },
        "significant_changes": {
            "acceptor": sig_acceptors,
            "donor": sig_donors
        }
    }

@router.post("/{disease_id}/states")
def save_user_edit(disease_id: str, payload: StateCreate, db: Session = Depends(get_db)):
    decoded_id = urllib.parse.unquote(disease_id)
    
    if not payload.applied_edit.edits:
        snv_info = crud.get_disease_detail_data(db, decoded_id)
        if snv_info and snv_info.get("seed_snv"):
            seed = snv_info["seed_snv"]
            payload.applied_edit.edits.append(
                SingleEdit(pos=int(seed.pos_gene0), from_base=seed.ref, to_base=seed.alt)
            )
        else:
            raise HTTPException(status_code=404, detail="기본 변이 정보를 찾을 수 없습니다.")

    applied_edit_dict = payload.applied_edit.model_dump(by_alias=True)
    new_state = crud.create_user_state(db, disease_id=decoded_id, parent_state_id=payload.parent_state_id, applied_edit=applied_edit_dict)
    
    return {"state_id": new_state.state_id, "message": "스마트 자동 완성이 적용되었습니다.", "applied_data": applied_edit_dict}
