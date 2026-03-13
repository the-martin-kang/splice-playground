
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from app.db.repositories import disease_repo, gene_repo, region_repo, snv_repo, window_repo
from app.schemas.common import Constraints, Highlight, UIHints, Coordinate
from app.schemas.disease import (
    DiseaseListResponse,
    DiseasePublic,
    SpliceAlteringSNV,
    Step2PayloadResponse,
    Step2Target,
    TargetWindow,
)
from app.schemas.gene import Gene
from app.schemas.region import RegionBase, RegionContext
from app.services.gene_context import build_gene_sequence, find_focus_region, pick_regions_with_shift, resolve_single_gene_id_for_disease
from app.services.storage_service import create_signed_url
from app.services.snv_alleles import complement_base


def _to_gene_model(row: Dict[str, Any]) -> Gene:
    return Gene(
        gene_id=str(row.get("gene_id") or ""),
        gene_symbol=str(row.get("gene_symbol") or row.get("gene_id") or ""),
        chromosome=row.get("chromosome") or row.get("chrom"),
        strand=str(row.get("strand") or "+"),
        length=int(row.get("length") or 0),
        exon_count=int(row.get("exon_count") or 0),
        canonical_transcript_id=row.get("canonical_transcript_id"),
        canonical_source=row.get("canonical_source"),
        source_version=row.get("source_version"),
    )


def _to_disease_public(row: Dict[str, Any]) -> DiseasePublic:
    image_path = row.get("image_path")
    url, exp = create_signed_url(image_path)
    return DiseasePublic(
        disease_id=str(row.get("disease_id")),
        disease_name=str(row.get("disease_name")),
        description=row.get("description"),
        gene_id=row.get("gene_id"),
        image_path=image_path,
        image_url=url,
        image_expires_in=exp,
        is_visible_in_service=row.get("is_visible_in_service"),
        max_supported_step=row.get("max_supported_step"),
        seed_mode=row.get("seed_mode"),
        note=row.get("note"),
    )


def _to_region_base(row: Dict[str, Any], *, include_sequence: bool) -> RegionBase:
    return RegionBase(
        region_id=str(row["region_id"]),
        region_type=str(row["region_type"]),
        region_number=int(row["region_number"]),
        gene_start_idx=int(row["gene_start_idx"]),
        gene_end_idx=int(row["gene_end_idx"]),
        length=int(row["length"]),
        sequence=(row.get("sequence") if include_sequence else None),
    )


def _to_region_context(row: Dict[str, Any], *, rel: int, include_sequence: bool) -> RegionContext:
    b = _to_region_base(row, include_sequence=include_sequence)
    return RegionContext(**b.model_dump(), rel=rel)


def _to_snv_model(row: Dict[str, Any]) -> SpliceAlteringSNV:
    chrom = row.get("_chrom") or row.get("chromosome") or row.get("chrom") or row.get("chr")
    pos1 = row.get("_pos1") or row.get("pos_hg38_1") or row.get("pos1")
    coord = Coordinate(
        chromosome=chrom,
        pos_hg38_1=int(pos1) if pos1 is not None else None,
        genomic_position=(f"{chrom}:{int(pos1)}" if chrom and pos1 is not None else None),
    )
    return SpliceAlteringSNV(
        snv_id=row.get("snv_id"),
        pos_gene0=int(row.get("pos_gene0")),
        ref=str(row.get("ref")),
        alt=str(row.get("alt")),
        coordinate=coord,
        note=row.get("note"),
        is_representative=row.get("is_representative"),
        allele_coordinate_system=row.get("allele_coordinate_system"),
    )


def list_diseases(limit: int = 100, offset: int = 0) -> DiseaseListResponse:
    rows, total = disease_repo.list_diseases(limit=limit, offset=offset, include_hidden=False)
    items = [_to_disease_public(r) for r in rows]
    return DiseaseListResponse(items=items, count=total)


def get_step2_payload(disease_id: str, *, include_sequence: bool = True) -> Step2PayloadResponse:
    drow = disease_repo.get_disease(disease_id)
    if not drow:
        raise HTTPException(status_code=404, detail=f"disease not found: {disease_id}")

    gid = resolve_single_gene_id_for_disease(disease_id, drow)
    grow = gene_repo.get_gene(gid)
    if not grow:
        raise HTTPException(status_code=404, detail=f"gene not found: {gid}")

    snv = snv_repo.get_representative_snv(disease_id)
    if not snv:
        raise HTTPException(status_code=404, detail=f"representative SNV not found for disease_id={disease_id}")

    regions = region_repo.list_regions_by_gene(gid, include_sequence=include_sequence)
    if not regions:
        raise HTTPException(status_code=404, detail=f"no regions for gene_id={gid}")

    focus_idx, focus_row = find_focus_region(regions, int(snv["pos_gene0"]))
    context_rows, start_idx = pick_regions_with_shift(regions, focus_idx, radius=2)

    wrow = window_repo.get_target_window(disease_id)
    if wrow:
        window = TargetWindow(
            start_gene0=int(wrow.get("start_gene0")),
            end_gene0=int(wrow.get("end_gene0")),
            label=wrow.get("label"),
            chosen_by=wrow.get("chosen_by"),
            note=wrow.get("note"),
        )
    else:
        window = TargetWindow(
            start_gene0=int(context_rows[0]["gene_start_idx"]),
            end_gene0=int(context_rows[-1]["gene_end_idx"]),
            label="default_context_5_regions",
            chosen_by="default:+/-2_regions",
            note=None,
        )

    focus = _to_region_base(focus_row, include_sequence=include_sequence)
    context = []
    for i, r in enumerate(context_rows):
        rel = int((start_idx + i) - focus_idx)
        context.append(_to_region_context(r, rel=rel, include_sequence=include_sequence))

    target = Step2Target(
        window=window,
        focus_region=focus,
        context_regions=context,
        constraints=Constraints(),
    )

    ui_hints = UIHints(highlight=Highlight(type="snv", pos_gene0=int(snv["pos_gene0"])), default_view="sequence")

    return Step2PayloadResponse(
        disease=_to_disease_public(drow),
        gene=_to_gene_model(grow),
        splice_altering_snv=_to_snv_model(snv),
        target=target,
        ui_hints=ui_hints,
    )


_COMP = {"A": "T", "T": "A", "C": "G", "G": "C", "N": "N"}


def _complement_base(b: str) -> str:
    return _COMP.get((b or "N").upper(), "N")


def _normalize_alleles_to_seq(base_at_pos: str, ref: str, alt: str) -> Tuple[str, str, bool]:
    base = (base_at_pos or "N").upper()
    ref_u = (ref or "N").upper()
    alt_u = (alt or "N").upper()
    if base == ref_u:
        return ref_u, alt_u, True
    c_ref = _complement_base(ref_u)
    if base == c_ref:
        return c_ref, _complement_base(alt_u), True
    return ref_u, alt_u, False


def get_region_detail(
    disease_id: str,
    region_type: str,
    region_number: int,
    *,
    include_sequence: bool = True,
) -> RegionBase:
    drow = disease_repo.get_disease(disease_id)
    if not drow:
        raise HTTPException(status_code=404, detail=f"disease not found: {disease_id}")
    gid = resolve_single_gene_id_for_disease(disease_id, drow)
    row = region_repo.get_region_by_type_number(gid, region_type, int(region_number), include_sequence=include_sequence)
    if not row:
        raise HTTPException(status_code=404, detail=f"region not found: gene_id={gid} {region_type}{region_number}")
    return _to_region_base(row, include_sequence=include_sequence)


def get_window_payload(disease_id: str, *, window_size: int = 4000) -> Dict[str, Any]:
    drow = disease_repo.get_disease(disease_id)
    if not drow:
        raise HTTPException(status_code=404, detail=f"disease not found: {disease_id}")
    gid = resolve_single_gene_id_for_disease(disease_id, drow)
    grow = gene_repo.get_gene(gid)
    if not grow:
        raise HTTPException(status_code=404, detail=f"gene not found: {gid}")
    gene_len = int(grow.get("length") or 0)
    if gene_len <= 0:
        raise HTTPException(status_code=400, detail=f"gene.length invalid for gene_id={gid}")

    snv = snv_repo.get_representative_snv(disease_id)
    if not snv:
        raise HTTPException(status_code=404, detail=f"representative SNV not found for disease_id={disease_id}")

    pos_gene0 = int(snv["pos_gene0"])
    ref = str(snv["ref"])
    alt = str(snv["alt"])

    regions = region_repo.list_regions_by_gene(gid, include_sequence=True)
    gene_seq = build_gene_sequence(gene_len, regions)

    ws = int(window_size)
    if ws <= 0:
        raise HTTPException(status_code=400, detail="window_size must be > 0")

    center_idx = ws // 2
    start_gene0 = pos_gene0 - center_idx
    end_gene0 = start_gene0 + ws

    pad_left = max(0, -start_gene0)
    pad_right = max(0, end_gene0 - gene_len)

    s = max(0, start_gene0)
    e = min(gene_len, end_gene0)
    ref_seq = ("N" * pad_left) + gene_seq[s:e] + ("N" * pad_right)
    if len(ref_seq) != ws:
        raise HTTPException(status_code=500, detail=f"window extraction length mismatch (got {len(ref_seq)} expected {ws})")

    base_at = ref_seq[center_idx]
    ref_n, alt_n, ok = _normalize_alleles_to_seq(base_at, ref, alt)

    alt_list = list(ref_seq)
    alt_list[center_idx] = alt_n
    alt_seq = "".join(alt_list)

    out: Dict[str, Any] = {
        "disease_id": disease_id,
        "gene_id": gid,
        "window_size": ws,
        "center_index_0": center_idx,
        "start_gene0": start_gene0,
        "end_gene0": end_gene0,
        "pos_gene0": pos_gene0,
        "ref_base": ref_n,
        "alt_base": alt_n,
        "ref_matches": bool(ok and base_at.upper() == ref_n),
        "ref_seq": ref_seq,
        "alt_seq": alt_seq,
    }
    if ws == 4000:
        out["ref_seq_4000"] = ref_seq
        out["alt_seq_4000"] = alt_seq
    return out
