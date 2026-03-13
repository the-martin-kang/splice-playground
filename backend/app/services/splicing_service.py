from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
from fastapi import HTTPException

from app.ai_models.spliceai_inference import InferenceConfig, predict_probs_center_crop, safe_float_list
from app.ai_models.spliceai_resblock import load_model
from app.db.repositories import disease_repo, gene_repo, region_repo, snv_repo, state_repo
from app.schemas.splicing import (
    DeltaPeak,
    DeltaSummary,
    Edit,
    PredictSplicingRequest,
    RegionBrief,
    RegionWithRel,
    SplicingPredictionResponse,
)
from app.services.gene_context import build_gene_sequence, find_focus_region, pick_regions_with_shift, resolve_single_gene_id_for_disease
from app.services.snv_alleles import complement_base, to_gene_direction_alleles
from app.services.state_lineage import collect_effective_state_edits
from app.services.step3_interpreter import interpret_step3

logger = logging.getLogger("app")


# ---------------------------------------------------------------------------
# Sequence edit helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Environment / model helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Response metadata helpers
# ---------------------------------------------------------------------------

def _to_region_brief(r: Dict[str, Any]) -> RegionBrief:
    return RegionBrief(
        region_id=str(r["region_id"]),
        region_type=str(r["region_type"]),
        region_number=int(r["region_number"]),
        gene_start_idx=int(r["gene_start_idx"]),
        gene_end_idx=int(r["gene_end_idx"]),
        length=int(r["length"]),
    )


def _to_edit_model(edit_like: Dict[str, Any]) -> Edit:
    return Edit.model_validate(
        {
            "pos": int(edit_like.get("pos")),
            "from": str(edit_like.get("from") or "N").upper(),
            "to": str(edit_like.get("to") or "N").upper(),
        }
    )


def _build_delta_peak(delta: np.ndarray, ref: np.ndarray, alt: np.ndarray, *, target_start_gene0: int) -> DeltaPeak:
    if delta.size == 0:
        return DeltaPeak(pos_gene0=target_start_gene0, index_in_target_0=0, delta=0.0, ref_prob=0.0, alt_prob=0.0)

    idx = int(np.argmax(delta))
    magnitude = float(delta[idx])
    if magnitude < 0:
        magnitude = 0.0
    return DeltaPeak(
        pos_gene0=int(target_start_gene0 + idx),
        index_in_target_0=idx,
        delta=magnitude,
        ref_prob=float(ref[idx]),
        alt_prob=float(alt[idx]),
    )


def _build_delta_summary(prob_ref: np.ndarray, prob_alt: np.ndarray, *, target_start_gene0: int) -> DeltaSummary:
    acc_ref = prob_ref[1]
    acc_alt = prob_alt[1]
    don_ref = prob_ref[2]
    don_alt = prob_alt[2]

    acc_gain = _build_delta_peak(acc_alt - acc_ref, acc_ref, acc_alt, target_start_gene0=target_start_gene0)
    acc_loss = _build_delta_peak(acc_ref - acc_alt, acc_ref, acc_alt, target_start_gene0=target_start_gene0)
    don_gain = _build_delta_peak(don_alt - don_ref, don_ref, don_alt, target_start_gene0=target_start_gene0)
    don_loss = _build_delta_peak(don_ref - don_alt, don_ref, don_alt, target_start_gene0=target_start_gene0)

    candidates = {
        "acceptor_gain": acc_gain.delta,
        "acceptor_loss": acc_loss.delta,
        "donor_gain": don_gain.delta,
        "donor_loss": don_loss.delta,
    }
    max_effect = max(candidates, key=candidates.get)
    max_abs_delta = float(candidates[max_effect])
    if max_abs_delta <= 0.0:
        max_effect = "none"

    return DeltaSummary(
        acceptor_gain=acc_gain,
        acceptor_loss=acc_loss,
        donor_gain=don_gain,
        donor_loss=don_loss,
        max_effect=max_effect,  # type: ignore[arg-type]
        max_abs_delta=max_abs_delta,
    )


def _assert_step3_enabled(disease_id: str, disease_row: Dict[str, Any]) -> None:
    max_step = disease_row.get("max_supported_step")
    if max_step is None:
        return
    try:
        max_step_i = int(max_step)
    except (TypeError, ValueError):
        logger.warning("Ignoring non-integer max_supported_step=%r for disease_id=%s", max_step, disease_id)
        return
    if max_step_i < 3:
        raise HTTPException(
            status_code=403,
            detail=f"Step3 is not enabled for disease_id={disease_id} (max_supported_step={max_step_i})",
        )


# ---------------------------------------------------------------------------
# STEP3 main entry
# ---------------------------------------------------------------------------

def predict_splicing_for_state(state_id: str, req: PredictSplicingRequest) -> SplicingPredictionResponse:
    state = state_repo.get_state(state_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"state not found: {state_id}")

    disease_id = str(state.get("disease_id") or "")
    if not disease_id:
        raise HTTPException(status_code=500, detail="user_state.disease_id is missing")

    disease = disease_repo.get_disease(disease_id)
    if not disease:
        raise HTTPException(status_code=404, detail=f"disease not found: {disease_id}")
    _assert_step3_enabled(disease_id, disease)

    try:
        gene_id = resolve_single_gene_id_for_disease(disease_id, disease)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    gene = gene_repo.get_gene(gene_id)
    if not gene:
        raise HTTPException(status_code=404, detail=f"gene not found: {gene_id}")

    gene_len = int(gene.get("length") or 0)
    if gene_len <= 0:
        raise HTTPException(status_code=500, detail="gene.length is missing/invalid")
    gene_exon_count_raw = gene.get("exon_count")
    try:
        gene_exon_count = int(gene_exon_count_raw) if gene_exon_count_raw is not None else None
    except (TypeError, ValueError):
        gene_exon_count = None
    gene_strand = str(gene.get("strand") or "+")

    snv = snv_repo.get_representative_snv(disease_id)
    if not snv:
        raise HTTPException(status_code=404, detail=f"representative SNV not found for disease_id={disease_id}")
    pos_gene0 = int(snv["pos_gene0"])
    snv_ref_gene, snv_alt_gene = to_gene_direction_alleles(snv, gene_strand)
    snv_ref_display = str(snv.get("ref") or snv_ref_gene)
    snv_alt_display = str(snv.get("alt") or snv_alt_gene)

    regions = region_repo.list_regions_by_gene(gene_id, include_sequence=True)
    if not regions:
        raise HTTPException(status_code=404, detail=f"No regions found for gene_id={gene_id}")

    focus_idx, focus_region = find_focus_region(regions, pos_gene0)
    target_regions, target_start_idx = pick_regions_with_shift(regions, focus_idx, int(req.region_radius))

    target_start = int(target_regions[0]["gene_start_idx"])
    target_end = int(target_regions[-1]["gene_end_idx"]) + 1  # exclusive
    if target_end <= target_start:
        raise HTTPException(status_code=500, detail="Invalid target span")
    target_len = target_end - target_start

    gene_seq = build_gene_sequence(gene_len, regions)

    flank = int(req.flank)
    input_start_gene0 = target_start - flank
    input_end_gene0 = target_end + flank
    input_len = input_end_gene0 - input_start_gene0
    if input_len <= 0:
        raise HTTPException(status_code=500, detail="Invalid input span")

    pad_left = max(0, -input_start_gene0)
    pad_right = max(0, input_end_gene0 - gene_len)
    in_start_clamped = max(0, input_start_gene0)
    in_end_clamped = min(gene_len, input_end_gene0)
    input_seq = ("N" * pad_left) + gene_seq[in_start_clamped:in_end_clamped] + ("N" * pad_right)
    if len(input_seq) != input_len:
        raise HTTPException(status_code=500, detail=f"input_seq length mismatch: got {len(input_seq)} expected {input_len}")

    if input_len < target_len:
        raise HTTPException(status_code=500, detail="input_len must be >= target_len")
    if input_len - target_len != 2 * flank:
        raise HTTPException(
            status_code=500,
            detail=(
                "Alignment requires input_len - target_len == 2*flank. "
                f"Got input_len={input_len}, target_len={target_len}, flank={flank}."
            ),
        )

    warnings: List[str] = []
    n_count = input_seq.count("N")
    if n_count > 0:
        warnings.append(f"Input span includes {n_count} padded/uncovered base(s) represented as 'N'.")

    ref_input = input_seq
    alt_list = list(input_seq)

    def idx_in_input(pos0: int) -> int:
        return int(pos0 - input_start_gene0)

    seed_mode = str(disease.get("seed_mode") or "apply_alt")
    representative_snv_applied = False
    if req.include_disease_snv and seed_mode != "reference_is_current":
        idx = idx_in_input(pos_gene0)
        base_at = alt_list[idx] if 0 <= idx < len(alt_list) else "N"
        ref_n, alt_n, _ = normalize_edit_to_sequence(base_at, snv_ref_gene, snv_alt_gene)
        ok = apply_substitution(alt_list, idx, ref_n, alt_n, strict=req.strict_ref_check)
        if req.strict_ref_check and not ok:
            raise HTTPException(
                status_code=400,
                detail=f"Representative SNV ref mismatch at pos_gene0={pos_gene0} (expected {ref_n}, saw {base_at})",
            )
        snv_ref_gene = ref_n
        snv_alt_gene = alt_n
        representative_snv_applied = True
    elif req.include_disease_snv and seed_mode == "reference_is_current":
        warnings.append("seed_mode=reference_is_current, so representative SNV was not auto-applied to the current sequence.")

    effective_edits_raw, lineage_ids = collect_effective_state_edits(state, include_parent_chain=req.include_parent_chain)
    if not req.include_parent_chain and state.get("parent_state_id"):
        warnings.append("include_parent_chain=false, so parent_state_id lineage edits were intentionally ignored for this prediction.")

    if req.edits_override:
        effective_edits_raw = effective_edits_raw + [
            {"pos": int(e.pos_gene0), "from": e.from_base.upper(), "to": e.to_base.upper()} for e in req.edits_override
        ]
        warnings.append(f"Applied {len(req.edits_override)} request-time override edit(s) after the stored state lineage.")

    ignored_outside_input = 0
    for e in effective_edits_raw:
        idx = idx_in_input(int(e["pos"]))
        if idx < 0 or idx >= len(alt_list):
            ignored_outside_input += 1
            continue
        base_at = alt_list[idx]
        ref_n, alt_n, _ = normalize_edit_to_sequence(base_at, e["from"], e["to"])
        ok = apply_substitution(alt_list, idx, ref_n, alt_n, strict=req.strict_ref_check)
        if req.strict_ref_check and not ok:
            raise HTTPException(
                status_code=400,
                detail=f"Edit ref mismatch at pos_gene0={e['pos']} (expected {ref_n}, saw {base_at})",
            )
    if ignored_outside_input:
        warnings.append(f"Ignored {ignored_outside_input} effective edit(s) outside the current model input span.")

    alt_input = "".join(alt_list)

    model = get_spliceai_model()
    cfg = InferenceConfig(device=_resolve_device_str(os.getenv("SPLICEAI_DEVICE")))
    prob_ref = predict_probs_center_crop(model, ref_input, in_length=input_len, out_length=target_len, cfg=cfg)
    prob_alt = predict_probs_center_crop(model, alt_input, in_length=input_len, out_length=target_len, cfg=cfg)

    focus_brief = _to_region_brief(focus_region)
    target_models: List[RegionWithRel] = []
    for i, r in enumerate(target_regions):
        rel = int((target_start_idx + i) - focus_idx)
        target_models.append(RegionWithRel(**_to_region_brief(r).model_dump(), rel=rel))

    snv_idx_in_target = int(pos_gene0 - target_start)
    target_seq_ref_full = gene_seq[target_start:target_end]
    target_seq_alt_full = alt_input[flank : flank + target_len]
    target_seq_ref = target_seq_ref_full if req.return_target_sequence else None
    target_seq_alt = target_seq_alt_full if req.return_target_sequence else None
    delta_summary = _build_delta_summary(prob_ref, prob_alt, target_start_gene0=target_start)
    interpretation = interpret_step3(
        target_regions=target_regions,
        gene_exon_count=gene_exon_count,
        target_start_gene0=target_start,
        target_len=target_len,
        target_seq_ref=target_seq_ref_full,
        target_seq_alt=target_seq_alt_full,
        prob_ref=prob_ref,
        prob_alt=prob_alt,
        snv_pos_gene0=pos_gene0,
        seed_mode=seed_mode,
    )

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
        snv_ref_gene_direction=snv_ref_gene,
        snv_alt_gene_direction=snv_alt_gene,
        representative_snv_applied=representative_snv_applied,
        snv_index_in_target_0=snv_idx_in_target,
        focus_region=focus_brief,
        target_regions=target_models,
        prob_ref=safe_float_list(prob_ref),
        prob_alt=safe_float_list(prob_alt),
        state_lineage=lineage_ids,
        effective_edits=[_to_edit_model(e) for e in effective_edits_raw],
        warnings=warnings,
        delta_summary=delta_summary,
        canonical_sites=interpretation["canonical_sites"],
        novel_sites=interpretation["novel_sites"],
        interpreted_events=interpretation["interpreted_events"],
        frontend_summary=interpretation["frontend_summary"],
        logic_thresholds=interpretation["logic_thresholds"],
        target_seq_ref=target_seq_ref,
        target_seq_alt=target_seq_alt,
    )
