import urllib.parse
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.crud import disease as crud
from app.core.database import get_db
from app.services.splice_service import SplicePredictor
from app.models.user_state import UserState
# 실제 프로젝트의 모델 정의 파일에서 클래스들을 가져오세요.
# from app.models.result import BaselineResult, UserStateResult 

router = APIRouter()
predictor = SplicePredictor("spliceAI_v1_4000_2000.pt")

def get_sig_data(delta, probs, offset, threshold=0.01):
    """유의미한 변화가 있는 좌표만 필터링 (JSON 용량 최적화)"""
    indices = np.where(np.abs(delta) > threshold)[0]
    return [{"pos": int(offset + i), "delta": round(float(delta[i]), 4), "prob": round(float(probs[i]), 4)} for i in indices]

# --- 6) 정상 Splicing 결과 (Baseline 최적화 버전) ---
@router.get("/diseases/{disease_id}/baseline/splicing")
def get_baseline_splicing(disease_id: str, db: Session = Depends(get_db)):
    decoded_id = urllib.parse.unquote(disease_id)
    detail = crud.get_disease_detail_full(db, decoded_id)
    if not detail: raise HTTPException(status_code=404, detail="Disease not found")
    
    gene_id = detail["gene"]["gene_id"]

    # 1. 서열 가져오기 및 예측
    full_seq, start_offset = crud.get_full_gene_sequence(db, gene_id)
    probs = predictor.predict(full_seq) # [3, L]
    
    # 2. 모든 데이터를 보내는 대신 '의미 있는 점수'만 필터링
    # threshold=0.01 이상인 지점만 추출 (정상적인 exon-intron 경계들만 남음)
    def get_high_probs(prob_array, offset, threshold=0.01):
        indices = np.where(prob_array > threshold)[0]
        return [{"pos": int(offset + i), "prob": round(float(prob_array[i]), 4)} for i in indices]

    sig_acceptors = get_high_probs(probs[1], start_offset)
    sig_donors = get_high_probs(probs[2], start_offset)

    return {
        "gene_id": gene_id,
        "step": "splicing",
        "summary": {
            "total_length": len(full_seq),
            "acceptor_count": len(sig_acceptors),
            "donor_count": len(sig_donors)
        },
        "result": {
            "acceptor": sig_acceptors,
            "donor": sig_donors
        }
    }

# --- 7) Seed (SNV) Splicing 결과 ---
@router.get("/diseases/{disease_id}/snv/splicing")
def get_snv_splicing(disease_id: str, db: Session = Depends(get_db)):
    decoded_id = urllib.parse.unquote(disease_id)
    detail = crud.get_disease_detail_full(db, decoded_id)
    gene_id = detail["gene"]["gene_id"]
    
    # [DB READ] snv_result 테이블 조회 로직 (설계안 7번)
    
    full_seq, start_offset = crud.get_full_gene_sequence(db, gene_id)
    snv = detail["splice_altering_snv"]
    
    mut_seq = list(full_seq)
    mut_seq[snv["pos_gene0"] - start_offset] = snv["alt"]
    
    base_probs = predictor.predict(full_seq)
    snv_probs = predictor.predict("".join(mut_seq))
    
    delta_acc = snv_probs[1] - base_probs[1]
    delta_don = snv_probs[2] - base_probs[2]
    
    return {
        "disease_id": decoded_id,
        "step": "splicing",
        "result": {"acceptor": snv_probs[1].tolist(), "donor": snv_probs[2].tolist()},
        "significant_delta": {
            "acceptor": get_sig_data(delta_acc, snv_probs[1], start_offset),
            "donor": get_sig_data(delta_don, snv_probs[2], start_offset)
        }
    }

# --- 8) User State Splicing 결과 (예측 및 저장) ---
@router.post("/states/{state_id}/spliceai/predict")
def predict_user_state_splicing(state_id: str, db: Session = Depends(get_db)):
    # [DB READ] user_state 테이블에서 편집 내용(edits) 가져오기
    state = db.query(UserState).filter(UserState.state_id == state_id).first()
    if not state: raise HTTPException(status_code=404, detail="State not found")
    
    full_seq, start_offset = crud.get_full_gene_sequence(db, state.disease_id)
    
    # 편집 반영
    mut_seq = list(full_seq)
    for edit in state.applied_edit.get("edits", []):
        mut_seq[edit["pos"] - start_offset] = edit["to"].upper()
    
    # 예측
    user_probs = predictor.predict("".join(mut_seq))
    base_probs = predictor.predict(full_seq) # Delta 계산용
    
    delta_acc = user_probs[1] - base_probs[1]
    delta_don = user_probs[2] - base_probs[2]

    # [DB WRITE] user_state_result upsert 로직 추가 위치 (설계안 8번)
    
    return {
        "state_id": state_id,
        "step": "splicing",
        "significant_delta": {
            "acceptor": get_sig_data(delta_acc, user_probs[1], start_offset),
            "donor": get_sig_data(delta_don, user_probs[2], start_offset)
        }
    }