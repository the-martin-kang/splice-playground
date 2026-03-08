
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import torch

from app.ai_models.spliceai_inference import InferenceConfig, predict_probs_center_crop, safe_float_list
from app.ai_models.spliceai_resblock import load_model
from app.db.supabase_client import get_supabase_client
from app.schemas.splicing import Edit, PredictSplicingRequest, RegionBrief, RegionWithRel, SplicingPredictionResponse
from app.services.snv_alleles import complement_base, to_gene_direction_alleles

logger = logging.getLogger("app")


def normalize_edit_to_sequence(base_at_pos: str, ref: str, alt: str) -> Tuple[str, str, bool]:
    base_at_pos = (base_at_pos or "N").upper()
    ref_u = (ref or "N").upper()
    alt_u = (alt or "N").upper()
    if base_at_pos == ref_u:
        return ref_u, alt_u, True
    cref = complement_base(ref_u)
    calt = complement_base(alt_u)
    if base_at_pos == cref:
        return cref, calt, True
    return ref_u, alt_u, False


def apply_substitution(seq_list: List[str], idx: int, from_b: str, to_b: str, *, strict: bool) -> bool:
    if idx < 0 or idx >= len(seq_list):
        raise IndexError(f"edit idx out of range: {idx} (len={len(seq_list)})")
    cur = (seq_list[idx] or "N").upper()
    fb = (from_b or "N").upper()
    tb = (to_b or "N").upper()
    ok = cur == fb
    if strict and not ok:
        return False
    seq_list[idx] = tb
    return ok


def _env(key: str, default: str) -> str:
    v = os.getenv(key)
    return v if v is not None and str(v).strip() != "" else default


def _resolve_device_str(requested: Optional[str]) -> str:
    if requested:
        req = str(requested).strip().lower()
        if req.startswith("cuda"):
            return req if torch.cuda.is_available() else "cpu"
        if req == "mps":
            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                return "mps"
            return "cpu"
        if req == "cpu":
            return "cpu"
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _resolve_model_path(model_path: str) -> str:
    model_path = model_path.strip()
    default_path = "app/ai_models/spliceai_window=10000.pt"
    if os.path.exists(model_path):
        return model_path
    if model_path != default_path and os.path.exists(default_path):
        logger.warning("SPLICEAI_MODEL_PATH=%s not found. Falling back to packaged default=%s", model_path, default_path)
        return default_path
    here_default = os.path.join(os.path.dirname(__file__), "..", "ai_models", "spliceai_window=10000.pt")
    here_default = os.path.normpath(here_default)
    if os.path.exists(here_default):
        return here_default
    raise FileNotFoundError(
        f"Model checkpoint not found: env/path={model_path!r}. Checked default={default_path!r}. "
        "If running in Docker/AWS, confirm .dockerignore does not exclude app/ai_models/*.pt and that the file exists in the image."
    )


@lru_cache(maxsize=1)
def get_spliceai_model() -> torch.nn.Module:
    model_path = _resolve_model_path(_env("SPLICEAI_MODEL_PATH", "app/ai_models/spliceai_window=10000.pt"))
    device_str = _resolve_device_str(os.getenv("SPLICEAI_DEVICE"))
    device = torch.device(device_str)
    logger.info("Loading SpliceAI model from %s on device=%s", model_path, device)
    return load_model(model_path, device=device)


def get_model_version() -> str:
    return _env("SPLICEAI_MODEL_VERSION", "spliceai10k_custom_v1")


def _single_or_none(q) -> Optional[Dict[str, Any]]:
    res = q.execute()
    data = res.data if hasattr(res, "data") else res.get("data")
    if data is None:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data


def fetch_state(state_id: str) -> Dict[str, Any]:
    sb = get_supabase_client()
    row = _single_or_none(sb.table("user_state").select("*").eq("state_id", state_id).limit(1))
    if not row:
        raise ValueError(f"state not found: {state_id}")
    return row


def fetch_disease(disease_id: str) -> Dict[str, Any]:
    sb = get_supabase_client()
    row = _single_or_none(sb.table("disease").select("*").eq("disease_id", disease_id).limit(1))
    if not row:
        raise ValueError(f"disease not found: {disease_id}")
    return row


def fetch_gene(gene_id: str) -> Dict[str, Any]:
    sb = get_supabase_client()
    row = _single_or_none(sb.table("gene").select("*").eq("gene_id", gene_id).limit(1))
    if not row:
        raise ValueError(f"gene not found: {gene_id}")
    return row


def fetch_representative_snv(disease_id: str) -> Dict[str, Any]:
    sb = get_supabase_client()
    row = _single_or_none(
        sb.table("splice_altering_snv").select("*").eq("disease_id", disease_id).eq("is_representative", True).limit(1)
    )
    if row:
        row.setdefault("allele_coordinate_system", "gene_direction")
        return row
    try:
        gene, gene0, pos, change = disease_id.split("_", 3)
        if gene0 != "gene0":
            raise ValueError
        pos_gene0 = int(pos)
        ref, alt = change.split(">", 1)
        return {
            "disease_id": disease_id,
            "gene_id": gene,
            "pos_gene0": pos_gene0,
            "ref": ref,
            "alt": alt,
            "is_representative": True,
            "allele_coordinate_system": "gene_direction",
        }
    except Exception as e:
        raise ValueError(f"Could not find representative SNV in DB and could not parse disease_id={disease_id!r}") from e


def fetch_regions_for_gene(gene_id: str) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    res = sb.table("region").select(
        "region_id,gene_id,region_type,region_number,gene_start_idx,gene_end_idx,length,sequence"
    ).eq("gene_id", gene_id).order("gene_start_idx").execute()
    data = res.data if hasattr(res, "data") else res.get("data")
    return list(data or [])


def build_gene_sequence(gene_len: int, regions: List[Dict[str, Any]]) -> str:
    arr = ["N"] * int(gene_len)
    for r in regions:
        s = int(r["gene_start_idx"])
        e = int(r["gene_end_idx"])
        seq = (r.get("sequence") or "").upper()
        if not seq:
            continue
        expected = e - s + 1
        if expected != len(seq):
            m = min(expected, len(seq))
            seq = seq[:m]
            e = s + m - 1
        if s < 0 or e >= gene_len or s > e:
            continue
        arr[s:e+1] = list(seq)
    return "".join(arr)


def find_focus_region(regions: List[Dict[str, Any]], pos_gene0: int) -> Tuple[int, Dict[str, Any]]:
    for i, r in enumerate(regions):
        s = int(r["gene_start_idx"])
        e = int(r["gene_end_idx"])
        if s <= pos_gene0 <= e:
            return i, r
    raise ValueError(f"SNV pos_gene0={pos_gene0} not covered by any region rows")


def pick_target_regions(regions: List[Dict[str, Any]], focus_idx: int, radius: int) -> Tuple[List[Dict[str, Any]], int]:
    k = int(2 * radius + 1)
    if k <= 0:
        return [regions[focus_idx]], focus_idx
    if len(regions) <= k:
        return regions, 0
    start = max(0, focus_idx - radius)
    if start + k > len(regions):
        start = max(0, len(regions) - k)
    return regions[start : start + k], start


def parse_state_edits(state_row: Dict[str, Any]) -> List[Edit]:
    ae = state_row.get("applied_edit")
    if not ae:
        return []
    if isinstance(ae, str):
        try:
            ae = json.loads(ae)
        except Exception:
            return []
    edits = ae.get("edits") if isinstance(ae, dict) else None
    if not isinstance(edits, list):
        return []
    out: List[Edit] = []
    for it in edits:
        try:
            out.append(Edit.model_validate(it))
        except Exception:
            continue
    return out


def predict_splicing_for_state(state_id: str, req: PredictSplicingRequest) -> SplicingPredictionResponse:
    state = fetch_state(state_id)
    disease_id = str(state.get("disease_id") or "")
    if not disease_id:
        raise ValueError("user_state.disease_id is missing")

    disease = fetch_disease(disease_id)
    max_step = disease.get("max_supported_step")
    if max_step is not None:
        try:
            if int(max_step) < 3:
                raise ValueError(f"Step3 is not enabled for disease_id={disease_id} (max_supported_step={max_step})")
        except Exception:
            pass

    gene_id = str(disease.get("gene_id") or disease.get("gene") or "")
    if not gene_id:
        raise ValueError("disease.gene_id is missing")

    gene = fetch_gene(gene_id)
    gene_len = int(gene.get("length") or 0)
    if gene_len <= 0:
        raise ValueError("gene.length is missing/invalid")
    gene_strand = str(gene.get("strand") or "+")

    snv = fetch_representative_snv(disease_id)
    pos_gene0 = int(snv["pos_gene0"])
    snv_ref_gene, snv_alt_gene = to_gene_direction_alleles(snv, gene_strand)
    snv_ref_display = str(snv.get("ref") or snv_ref_gene)
    snv_alt_display = str(snv.get("alt") or snv_alt_gene)

    regions = fetch_regions_for_gene(gene_id)
    if not regions:
        raise ValueError(f"No regions found for gene_id={gene_id}")

    focus_idx, focus_region = find_focus_region(regions, pos_gene0)
    target_regions, target_start_idx = pick_target_regions(regions, focus_idx, int(req.region_radius))

    target_start = int(target_regions[0]["gene_start_idx"])
    target_end = int(target_regions[-1]["gene_end_idx"]) + 1  # exclusive
    if target_end <= target_start:
        raise ValueError("Invalid target span")
    target_len = target_end - target_start

    gene_seq = build_gene_sequence(gene_len, regions)

    flank = int(req.flank)
    input_start_gene0 = target_start - flank
    input_end_gene0 = target_end + flank
    input_len = input_end_gene0 - input_start_gene0
    if input_len <= 0:
        raise ValueError("Invalid input span")

    pad_left = max(0, -input_start_gene0)
    pad_right = max(0, input_end_gene0 - gene_len)
    in_start_clamped = max(0, input_start_gene0)
    in_end_clamped = min(gene_len, input_end_gene0)
    input_seq = ("N" * pad_left) + gene_seq[in_start_clamped:in_end_clamped] + ("N" * pad_right)
    if len(input_seq) != input_len:
        raise ValueError(f"input_seq length mismatch: got {len(input_seq)} expected {input_len}")

    ref_input = input_seq
    alt_list = list(input_seq)

    def idx_in_input(pos0: int) -> int:
        return int(pos0 - input_start_gene0)

    seed_mode = str(disease.get("seed_mode") or "apply_alt")
    if req.include_disease_snv and seed_mode != "reference_is_current":
        idx = idx_in_input(pos_gene0)
        base_at = alt_list[idx] if 0 <= idx < len(alt_list) else "N"
        ref_n, alt_n, _ = normalize_edit_to_sequence(base_at, snv_ref_gene, snv_alt_gene)
        ok = apply_substitution(alt_list, idx, ref_n, alt_n, strict=req.strict_ref_check)
        if req.strict_ref_check and not ok:
            raise ValueError(f"Representative SNV ref mismatch at pos_gene0={pos_gene0} (expected {ref_n}, saw {base_at})")
        snv_ref_gene = ref_n
        snv_alt_gene = alt_n

    edits = parse_state_edits(state)
    if req.edits_override:
        edits = edits + list(req.edits_override)
    for e in edits:
        idx = idx_in_input(int(e.pos_gene0))
        if idx < 0 or idx >= len(alt_list):
            continue
        base_at = alt_list[idx]
        ref_n, alt_n, _ = normalize_edit_to_sequence(base_at, e.from_base, e.to_base)
        ok = apply_substitution(alt_list, idx, ref_n, alt_n, strict=req.strict_ref_check)
        if req.strict_ref_check and not ok:
            raise ValueError(f"Edit ref mismatch at pos_gene0={e.pos_gene0} (expected {ref_n}, saw {base_at})")

    alt_input = "".join(alt_list)

    if input_len < target_len:
        raise ValueError("input_len must be >= target_len")
    if input_len - target_len != 2 * flank:
        raise ValueError(
            f"Alignment requires input_len - target_len == 2*flank. Got input_len={input_len}, target_len={target_len}, flank={flank}."
        )

    model = get_spliceai_model()
    cfg = InferenceConfig(device=_resolve_device_str(os.getenv("SPLICEAI_DEVICE")))
    prob_ref = predict_probs_center_crop(model, ref_input, in_length=input_len, out_length=target_len, cfg=cfg)
    prob_alt = predict_probs_center_crop(model, alt_input, in_length=input_len, out_length=target_len, cfg=cfg)

    def to_region_brief(r: Dict[str, Any]) -> RegionBrief:
        return RegionBrief(
            region_id=str(r["region_id"]),
            region_type=str(r["region_type"]),
            region_number=int(r["region_number"]),
            gene_start_idx=int(r["gene_start_idx"]),
            gene_end_idx=int(r["gene_end_idx"]),
            length=int(r["length"]),
        )

    focus_brief = to_region_brief(focus_region)
    target_models: List[RegionWithRel] = []
    for i, r in enumerate(target_regions):
        rel = int((target_start_idx + i) - focus_idx)
        target_models.append(RegionWithRel(**to_region_brief(r).model_dump(), rel=rel))

    snv_idx_in_target = int(pos_gene0 - target_start)
    target_seq_ref = gene_seq[target_start:target_end] if req.return_target_sequence else None
    target_seq_alt = "".join(alt_list)[flank:flank + target_len] if req.return_target_sequence else None

    return SplicingPredictionResponse(
        state_id=state_id,
        disease_id=disease_id,
        gene_id=gene_id,
        model_version=get_model_version(),
        region_radius=int(req.region_radius),
        flank=flank,
        target_start_gene0=target_start,
        target_end_gene0=target_end,
        target_len=target_len,
        input_start_gene0=input_start_gene0,
        input_end_gene0=input_end_gene0,
        input_len=input_len,
        snv_pos_gene0=pos_gene0,
        snv_ref=snv_ref_display,
        snv_alt=snv_alt_display,
        snv_index_in_target_0=snv_idx_in_target,
        focus_region=focus_brief,
        target_regions=target_models,
        prob_ref=safe_float_list(prob_ref),
        prob_alt=safe_float_list(prob_alt),
        target_seq_ref=target_seq_ref,
        target_seq_alt=target_seq_alt,
    )
