import os
import uuid
import urllib.parse
from sqlalchemy.orm import Session
from app.models.disease import Disease
from app.models.gene import Gene
from app.models.disease_gene import DiseaseGene
from app.models.splice_altering_snv import SpliceAlteringSNV
from app.models.region import Region
from app.models.user_state import UserState
from app.services.spliceai import splice_service

# --- 1. 유틸리티 함수 ---

def get_valid_image_url(db_image_path: str) -> str:
    """DB에 저장된 이미지 경로를 검증하여 반환합니다."""
    if not db_image_path or str(db_image_path).strip() in ("", "None"):
        return "/static/diseases/default.png"
    
    return db_image_path if db_image_path.startswith('/') else f"/{db_image_path}"

# --- 2. 질병 상세 조회 (Gene 테이블 정보 통합) ---

def get_disease_detail_full(db: Session, disease_id: str):
    """
    질병, 유전자, SNV 및 주변 Region 정보를 모두 조립하여 
    프론트엔드 요구사항에 맞는 상세 데이터를 반환합니다.
    """
    decoded_id = urllib.parse.unquote(disease_id)
    
    # 기본 정보 조회
    disease = db.query(Disease).filter(Disease.disease_id == decoded_id).first()
    if not disease: return None

    snv = db.query(SpliceAlteringSNV).filter(SpliceAlteringSNV.disease_id == decoded_id).first()
    if not snv: return None

    gene = db.query(Gene).filter(Gene.gene_id == snv.gene_id).first()
    if not gene: return None

    # 중심 Region 및 주변 Region(앞뒤 2개) 조회
    target_pos = int(snv.pos_gene0)
    all_regions = db.query(Region).filter(Region.gene_id == gene.gene_id).order_by(Region.region_number).all()
    
    focus_idx = next((i for i, r in enumerate(all_regions) 
                      if r.gene_start_idx <= target_pos < r.gene_end_idx), None)
    
    if focus_idx is None: return None
    focus_region = all_regions[focus_idx]

    # Genomic Position 파싱 (chr=chr7;pos1=117589467 -> chr7:117589467)
    genomic_pos = "Unknown"
    if snv.note:
        parts = {p.split('=')[0]: p.split('=')[1] for p in snv.note.split(';') if '=' in p}
        if 'chr' in parts and 'pos1' in parts:
            genomic_pos = f"{parts['chr']}:{parts['pos1']}"

    # Context Regions 구성
    context_regions = []
    start_idx = max(0, focus_idx - 2)
    end_idx = min(len(all_regions), focus_idx + 3)
    
    for i in range(start_idx, end_idx):
        r = all_regions[i]
        context_regions.append({
            "rel": i - focus_idx,
            "region_id": r.region_id,
            "region_type": r.region_type,
            "region_number": r.region_number,
            "gene_start_idx": r.gene_start_idx,
            "gene_end_idx": r.gene_end_idx,
            "length": r.gene_end_idx - r.gene_start_idx,
            "sequence": r.sequence
        })

    return {
        "disease": {
            "disease_id": disease.disease_id,
            "disease_name": disease.disease_name,
            "description": disease.description,
            "image_path": get_valid_image_url(disease.image_path)
        },
        "gene": {
            "gene_id": gene.gene_id,
            "gene_symbol": gene.gene_symbol,
            "chromosome": gene.chromosome,
            "strand": gene.strand,
            "length": gene.length,
            "exon_count": gene.exon_count,
            "canonical_transcript_id": gene.canonical_transcript_id,
            "canonical_source": gene.canonical_source,
            "source_version": gene.source_version
        },
        "splice_altering_snv": {
            "pos_gene0": target_pos,
            "ref": snv.ref,
            "alt": snv.alt,
            "coordinate": {
                "coordinate_system": "gene0",
                "assembly": "GRCh38",
                "genomic_position": genomic_pos
            },
            "note": "representative splice-altering SNV"
        },
        "target": {
            "focus_region": {
                "region_id": focus_region.region_id,
                "region_type": focus_region.region_type,
                "gene_start_idx": focus_region.gene_start_idx,
                "gene_end_idx": focus_region.gene_end_idx,
                "length": focus_region.gene_end_idx - focus_region.gene_start_idx
            },
            "snv_mapping": {
                "snv_in_focus_region": True,
                "offset_in_region0": target_pos - focus_region.gene_start_idx,
                "snv_context_seq": focus_region.sequence[max(0, (target_pos - focus_region.gene_start_idx)-7):min(len(focus_region.sequence), (target_pos - focus_region.gene_start_idx)+8)],
                "context_window": { "left": 7, "right": 7 }
            },
            "context_regions": context_regions,
            "constraints": {
                "sequence_alphabet": ["A", "C", "G", "T", "N"],
                "edit_length_must_be_preserved": True
            }
        },
        "ui_hints": {
            "default_view": "sequence",
            "highlight": { "type": "snv", "pos_gene0": target_pos }
        }
    }

# --- 3. 서열 조립 및 다중 편집 반영 (핵심) ---

def assemble_full_gene_sequence(db: Session, disease_id: str, apply_seed: bool = False, edits: list = None):
    """
    전체 유전자 서열을 조립하고, Seed SNV 및 다중 사용자 편집을 반영합니다.
    """
    decoded_id = urllib.parse.unquote(disease_id)
    snv_info = db.query(SpliceAlteringSNV).filter(SpliceAlteringSNV.disease_id == decoded_id).first()
    if not snv_info: return ""

    regions = db.query(Region).filter(Region.gene_id == snv_info.gene_id).order_by(Region.region_number).all()
    if not regions: return ""

    # 전체 서열 조립
    full_seq_list = list("".join([r.sequence for r in regions]))
    seq_len = len(full_seq_list)

    # 1. 질병 원인 변이(Seed SNV) 반영
    if apply_seed:
        pos = int(snv_info.pos_gene0)
        if 0 <= pos < seq_len:
            full_seq_list[pos] = snv_info.alt

    # 2. 다중 사용자 편집(User Edits) 반영
    if edits:
        for edit in edits:
            e_pos = int(edit.get("pos", -1))
            new_base = edit.get("to", "").upper()
            if 0 <= e_pos < seq_len and new_base in {'A', 'C', 'G', 'T', 'N'}:
                full_seq_list[e_pos] = new_base

    return "".join(full_seq_list)

# --- 4. 기타 기존 함수 유지 ---

def get_diseases(db: Session):
    diseases = db.query(Disease).all()
    for d in diseases:
        d.image_path = get_valid_image_url(d.image_path)
    return diseases

def create_user_state(db: Session, disease_id: str, applied_edit: dict, parent_state_id: str = None):
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

def get_disease_detail_data(db: Session, disease_id: str):
    """기존 API 호환용 (상세 조립 이전 버전)"""
    disease = db.query(Disease).filter(Disease.disease_id == disease_id).first()
    if not disease: return None
    disease.image_path = get_valid_image_url(disease.image_path)
    snv_info = db.query(SpliceAlteringSNV).filter(SpliceAlteringSNV.disease_id == disease_id).first()
    return {"disease": disease, "seed_snv": snv_info}