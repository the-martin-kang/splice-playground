from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.crud import disease as crud
from app.models.user_state import UserState

router = APIRouter()

@router.get("/{disease_id}/baseline/splicing")
def get_baseline_splicing(disease_id: str, db: Session = Depends(get_db)):
    """정상 서열 분석 (Baseline)"""
    result = crud.get_baseline_splicing_data(db, disease_id=disease_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Data for {disease_id} not found in SNV or Region tables.")
    return result

@router.get("/{disease_id}/snv/splicing")
def get_snv_splicing(disease_id: str, db: Session = Depends(get_db)):
    """환자 변이 서열 분석 (SNV)"""
    result = crud.get_snv_splicing_data(db, disease_id=disease_id)
    if not result:
        raise HTTPException(status_code=404, detail="SNV sequence assembly failed.")
    return result

@router.post("/states/{state_id}/spliceai/predict")
def predict_user_edit_splicing(state_id: str, db: Session = Depends(get_db)):
    """사용자 편집 서열 분석"""
    user_state = db.query(UserState).filter(UserState.state_id == state_id).first()
    if not user_state:
        raise HTTPException(status_code=404, detail="State not found")
    
    full_seq = crud.assemble_full_gene_sequence(
        db, user_state.disease_id, apply_seed=True, edit=user_state.applied_edit
    )
    if not full_seq:
        raise HTTPException(status_code=400, detail="Failed to assemble sequence.")
        
    prediction = crud.splice_service.predict(full_seq)
    crud.save_user_state_result(db, state_id, "splicing", prediction)
    return {"state_id": state_id, "prediction": prediction}