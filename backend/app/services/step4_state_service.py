from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException

from app.core.config import get_settings
from app.db.repositories import disease_repo, gene_repo, region_repo, state_repo
from app.db.repositories.step4_baseline_repo import list_structure_assets
from app.db.repositories.structure_job_repo import get_job, list_jobs_for_state
from app.schemas.splicing import PredictSplicingRequest, Step3SplicingEvent
from app.schemas.step4 import (
    Step4CapabilitiesPublic,
    Step4JobAssetPublic,
    Step4MolstarTargetPublic,
    Step4NormalTrackPublic,
    Step4PredictedTranscriptPublic,
    Step4SequenceComparisonPublic,
    Step4StateResponse,
    Step4StructureAssetPublic,
    Step4StructureComparisonPublic,
    Step4StructureJobPublic,
    Step4TranscriptBlockPublic,
    Step4TranslationSanityPublic,
    Step4UserTrackPublic,
)
from app.services.gene_context import build_gene_sequence, resolve_single_gene_id_for_disease
from app.services.protein_translation import (
    compare_sequences,
    first_stop_codon_end_1,
    normalize_nt,
    sha256_text,
    translate_cds,
    trim_to_complete_codons,
)
from app.services.splicing_service import apply_substitution, normalize_edit_to_sequence, predict_splicing_for_state
from app.services.snv_alleles import to_gene_direction_alleles
from app.services.state_lineage import collect_effective_state_edits
from app.services.step4_baseline_service import get_step4_baseline_for_state
from app.services.step4_validation import build_canonical_mrna_from_region_rows
from app.services.storage_service import create_signed_storage_url


@dataclass
class _InternalBlock:
    block_id: str
    block_kind: str
    label: str
    gene_start_idx: int
    gene_end_idx: int
    canonical_exon_number: Optional[int] = None
    notes: Optional[List[str]] = None

    @property
    def length(self) -> int:
        return int(self.gene_end_idx - self.gene_start_idx + 1)


def _pick_primary_event(events: Sequence[Step3SplicingEvent]) -> Step3SplicingEvent:
    non_none = [e for e in events if e.event_type != "NONE"]
    if non_none:
        return non_none[0]
    if events:
        return events[0]
    return Step3SplicingEvent(
        event_type="NONE",
        subtype=None,
        confidence="low",
        score=0.0,
        summary="No interpreted STEP3 event available.",
    )



def _get_state_disease_gene(state_id: str) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    srow = state_repo.get_state(state_id)
    if not srow:
        raise HTTPException(status_code=404, detail=f"state not found: {state_id}")
    disease_id = str(srow.get("disease_id") or "")
    if not disease_id:
        raise HTTPException(status_code=500, detail="user_state.disease_id is missing")
    drow = disease_repo.get_disease(disease_id)
    if not drow:
        raise HTTPException(status_code=404, detail=f"disease not found: {disease_id}")
    gene_id = str(srow.get("gene_id") or "")
    if not gene_id:
        try:
            gene_id = resolve_single_gene_id_for_disease(disease_id, drow)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    grow = gene_repo.get_gene(gene_id)
    if not grow:
        raise HTTPException(status_code=404, detail=f"gene not found: {gene_id}")
    return srow, drow, grow



def _build_current_gene_sequence(
    *,
    state_row: Dict[str, Any],
    disease_row: Dict[str, Any],
    gene_row: Dict[str, Any],
    region_rows: Sequence[Dict[str, Any]],
) -> Tuple[str, List[Dict[str, Any]], List[str], bool, List[str]]:
    gene_len = int(gene_row.get("length") or 0)
    if gene_len <= 0:
        raise HTTPException(status_code=500, detail="gene.length is missing/invalid")

    base_seq = build_gene_sequence(gene_len, list(region_rows))
    seq_list = list(base_seq)
    warnings: List[str] = []

    representative_snv_applied = False
    seed_mode = str(disease_row.get("seed_mode") or "apply_alt")
    from app.db.repositories import snv_repo
    snv = snv_repo.get_representative_snv(str(disease_row.get("disease_id") or ""))
    if snv and seed_mode != "reference_is_current":
        pos_gene0 = int(snv["pos_gene0"])
        snv_ref_gene, snv_alt_gene = to_gene_direction_alleles(snv, str(gene_row.get("strand") or "+"))
        if 0 <= pos_gene0 < len(seq_list):
            base_at = seq_list[pos_gene0]
            ref_n, alt_n, _ = normalize_edit_to_sequence(base_at, snv_ref_gene, snv_alt_gene)
            ok = apply_substitution(seq_list, pos_gene0, ref_n, alt_n, strict=False)
            if not ok:
                warnings.append(
                    f"Representative SNV expected {ref_n} at pos_gene0={pos_gene0} but saw {base_at}; applied non-strict substitution."
                )
            representative_snv_applied = True
    elif snv and seed_mode == "reference_is_current":
        warnings.append("seed_mode=reference_is_current, so representative SNV was not auto-applied for STEP4 user track.")

    effective_edits, lineage_ids = collect_effective_state_edits(state_row, include_parent_chain=True)
    for e in effective_edits:
        pos = int(e.get("pos"))
        if pos < 0 or pos >= len(seq_list):
            warnings.append(f"Ignored effective edit outside gene bounds at pos_gene0={pos}.")
            continue
        base_at = seq_list[pos]
        ref_n, alt_n, _ = normalize_edit_to_sequence(base_at, str(e.get("from") or "N"), str(e.get("to") or "N"))
        ok = apply_substitution(seq_list, pos, ref_n, alt_n, strict=False)
        if not ok:
            warnings.append(
                f"Stored edit expected {ref_n} at pos_gene0={pos} but saw {base_at}; applied non-strict substitution."
            )

    return "".join(seq_list), effective_edits, lineage_ids, representative_snv_applied, warnings



def _canonical_exon_rows(region_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [r for r in region_rows if str(r.get("region_type") or "") == "exon"]
    rows.sort(key=lambda r: int(r.get("region_number") or 0))
    return rows



def _build_canonical_cdna_maps(exon_rows: Sequence[Dict[str, Any]]) -> Tuple[Dict[int, int], Dict[int, int]]:
    gene_to_cdna: Dict[int, int] = {}
    cdna_to_gene: Dict[int, int] = {}
    cdna1 = 1
    for row in exon_rows:
        start = int(row["gene_start_idx"])
        end = int(row["gene_end_idx"])
        for pos in range(start, end + 1):
            gene_to_cdna[pos] = cdna1
            cdna_to_gene[cdna1] = pos
            cdna1 += 1
    return gene_to_cdna, cdna_to_gene



def _make_block_from_exon(row: Dict[str, Any], *, current_gene_seq: str, block_kind: str = "canonical_exon", label_suffix: str = "") -> _InternalBlock:
    start = int(row["gene_start_idx"])
    end = int(row["gene_end_idx"])
    notes: List[str] = []
    if start < 0 or end >= len(current_gene_seq):
        raise HTTPException(status_code=500, detail="Transcript block outside gene sequence bounds")
    exon_no = int(row.get("region_number") or 0)
    label = f"Exon{exon_no}{label_suffix}"
    return _InternalBlock(
        block_id=f"exon_{exon_no}",
        block_kind=block_kind,
        label=label,
        gene_start_idx=start,
        gene_end_idx=end,
        canonical_exon_number=exon_no,
        notes=notes,
    )



def _insert_pseudo_exon_block(
    blocks: List[_InternalBlock],
    *,
    acceptor_pos_gene0: int,
    donor_pos_gene0: int,
    current_gene_seq: str,
) -> List[_InternalBlock]:
    if acceptor_pos_gene0 < 0 or donor_pos_gene0 < acceptor_pos_gene0 or donor_pos_gene0 >= len(current_gene_seq):
        return blocks
    pseudo = _InternalBlock(
        block_id=f"pseudo_{acceptor_pos_gene0}_{donor_pos_gene0}",
        block_kind="pseudo_exon",
        label="PseudoExon",
        gene_start_idx=acceptor_pos_gene0,
        gene_end_idx=donor_pos_gene0,
        canonical_exon_number=None,
        notes=["Inserted from STEP3 pseudo-exon event."],
    )
    insert_at = len(blocks)
    for i, blk in enumerate(blocks):
        if acceptor_pos_gene0 < blk.gene_start_idx:
            insert_at = i
            break
    return blocks[:insert_at] + [pseudo] + blocks[insert_at:]



def _apply_boundary_shift(
    blocks: List[_InternalBlock],
    *,
    event: Step3SplicingEvent,
    current_gene_seq: str,
    warnings: List[str],
) -> List[_InternalBlock]:
    if not event.affected_exon_numbers:
        warnings.append("BOUNDARY_SHIFT event is missing affected_exon_numbers; canonical transcript kept.")
        return blocks
    exon_no = int(event.affected_exon_numbers[0])
    out: List[_InternalBlock] = []
    changed = False
    for blk in blocks:
        if blk.canonical_exon_number != exon_no:
            out.append(blk)
            continue
        start = blk.gene_start_idx
        end = blk.gene_end_idx
        notes = list(blk.notes or [])
        if event.subtype in {"EXON_EXTENSION_5P", "EXON_SHORTENING_5P"} and event.acceptor_pos_gene0 is not None:
            start = int(event.acceptor_pos_gene0)
            notes.append(f"5' boundary updated from STEP3 subtype={event.subtype}.")
        elif event.subtype in {"EXON_EXTENSION_3P", "EXON_SHORTENING_3P"} and event.donor_pos_gene0 is not None:
            end = int(event.donor_pos_gene0)
            notes.append(f"3' boundary updated from STEP3 subtype={event.subtype}.")
        else:
            warnings.append(f"Unsupported BOUNDARY_SHIFT subtype={event.subtype}; canonical transcript kept for exon {exon_no}.")
            out.append(blk)
            continue
        if start < 0 or end < start or end >= len(current_gene_seq):
            warnings.append(f"BOUNDARY_SHIFT for exon {exon_no} produced invalid coordinates {start}-{end}; canonical block kept.")
            out.append(blk)
            continue
        out.append(
            _InternalBlock(
                block_id=blk.block_id,
                block_kind="boundary_shift",
                label=blk.label,
                gene_start_idx=start,
                gene_end_idx=end,
                canonical_exon_number=blk.canonical_exon_number,
                notes=notes,
            )
        )
        changed = True
    if not changed:
        warnings.append(f"BOUNDARY_SHIFT target exon {exon_no} was not found in canonical transcript blocks.")
    return out



def _blocks_from_primary_event(
    *,
    canonical_exon_rows: Sequence[Dict[str, Any]],
    current_gene_seq: str,
    primary_event: Step3SplicingEvent,
    warnings: List[str],
) -> Tuple[List[_InternalBlock], List[int], List[int], int]:
    blocks = [_make_block_from_exon(r, current_gene_seq=current_gene_seq) for r in canonical_exon_rows]
    included_exons = [int(r.get("region_number") or 0) for r in canonical_exon_rows]
    excluded_exons: List[int] = []
    inserted_block_count = 0

    if primary_event.event_type in {"NONE", "CANONICAL_STRENGTHENING"}:
        return blocks, included_exons, excluded_exons, inserted_block_count

    if primary_event.event_type == "COMPLEX":
        warnings.append("Primary STEP3 event is COMPLEX; canonical transcript is returned as a conservative fallback.")
        return blocks, included_exons, excluded_exons, inserted_block_count

    if primary_event.event_type == "EXON_EXCLUSION":
        excluded = {int(x) for x in primary_event.affected_exon_numbers}
        if not excluded:
            warnings.append("EXON_EXCLUSION event missing affected_exon_numbers; canonical transcript kept.")
            return blocks, included_exons, excluded_exons, inserted_block_count
        blocks = [b for b in blocks if b.canonical_exon_number not in excluded]
        excluded_exons = sorted(excluded)
        included_exons = [b.canonical_exon_number for b in blocks if b.canonical_exon_number is not None]
        return blocks, included_exons, excluded_exons, inserted_block_count

    if primary_event.event_type == "PSEUDO_EXON":
        if primary_event.acceptor_pos_gene0 is None or primary_event.donor_pos_gene0 is None:
            warnings.append("PSEUDO_EXON event missing acceptor/donor positions; canonical transcript kept.")
            return blocks, included_exons, excluded_exons, inserted_block_count
        blocks = _insert_pseudo_exon_block(
            blocks,
            acceptor_pos_gene0=int(primary_event.acceptor_pos_gene0),
            donor_pos_gene0=int(primary_event.donor_pos_gene0),
            current_gene_seq=current_gene_seq,
        )
        inserted_block_count = 1
        return blocks, included_exons, excluded_exons, inserted_block_count

    if primary_event.event_type == "BOUNDARY_SHIFT":
        blocks = _apply_boundary_shift(blocks, event=primary_event, current_gene_seq=current_gene_seq, warnings=warnings)
        included_exons = [b.canonical_exon_number for b in blocks if b.canonical_exon_number is not None]
        return blocks, included_exons, excluded_exons, inserted_block_count

    warnings.append(f"Unsupported STEP3 event_type={primary_event.event_type}; canonical transcript kept.")
    return blocks, included_exons, excluded_exons, inserted_block_count



def _build_cdna_from_blocks(
    *,
    blocks: Sequence[_InternalBlock],
    current_gene_seq: str,
) -> Tuple[str, Dict[int, int], List[Step4TranscriptBlockPublic], List[str]]:
    cdna_parts: List[str] = []
    gene_to_cdna: Dict[int, int] = {}
    public_blocks: List[Step4TranscriptBlockPublic] = []
    warnings: List[str] = []
    cdna1 = 1
    prev_end: Optional[int] = None
    for blk in blocks:
        start = int(blk.gene_start_idx)
        end = int(blk.gene_end_idx)
        if start < 0 or end < start or end >= len(current_gene_seq):
            warnings.append(f"Invalid transcript block coordinates skipped: {start}-{end}")
            continue
        if prev_end is not None and start <= prev_end:
            warnings.append(f"Transcript blocks overlap around gene0={start}; later block kept as-is.")
        seq = current_gene_seq[start:end + 1]
        if not seq:
            warnings.append(f"Empty transcript block skipped at {start}-{end}.")
            continue
        cdna_start_1 = cdna1
        cdna_end_1 = cdna1 + len(seq) - 1
        cdna_parts.append(seq)
        for offset, pos in enumerate(range(start, end + 1)):
            gene_to_cdna[pos] = cdna_start_1 + offset
        public_blocks.append(
            Step4TranscriptBlockPublic(
                block_id=blk.block_id,
                block_kind=blk.block_kind,  # type: ignore[arg-type]
                label=blk.label,
                gene_start_idx=start,
                gene_end_idx=end,
                length=len(seq),
                canonical_exon_number=blk.canonical_exon_number,
                cdna_start_1=cdna_start_1,
                cdna_end_1=cdna_end_1,
                notes=list(blk.notes or []),
            )
        )
        cdna1 = cdna_end_1 + 1
        prev_end = end
    return "".join(cdna_parts), gene_to_cdna, public_blocks, warnings



def _translation_from_user_cdna(
    *,
    baseline_cds_start_cdna_1: Optional[int],
    baseline_cds_end_cdna_1: Optional[int],
    baseline_cdna_to_gene: Dict[int, int],
    user_gene_to_cdna: Dict[int, int],
    user_cdna_seq: str,
    normal_cds_seq: str,
    normal_protein_seq: str,
) -> Tuple[str, str, Step4TranslationSanityPublic, List[str]]:
    warnings: List[str] = []
    baseline_start_gene0 = baseline_cdna_to_gene.get(int(baseline_cds_start_cdna_1)) if baseline_cds_start_cdna_1 else None
    baseline_end_gene0 = baseline_cdna_to_gene.get(int(baseline_cds_end_cdna_1)) if baseline_cds_end_cdna_1 else None

    if baseline_start_gene0 is None:
        sanity = Step4TranslationSanityPublic(
            translation_ok=False,
            reason="missing_baseline_cds_start_mapping",
            baseline_cds_start_cdna_1=baseline_cds_start_cdna_1,
            baseline_cds_end_cdna_1=baseline_cds_end_cdna_1,
            start_codon_preserved=False,
            stop_codon_found=False,
            multiple_of_three=False,
            frameshift_likely=None,
            premature_stop_likely=None,
            protein_length=0,
            cds_length_nt=0,
            notes=["Could not map baseline CDS start back to canonical gene coordinates."],
        )
        return "", "", sanity, warnings

    user_cds_start_cdna_1 = user_gene_to_cdna.get(baseline_start_gene0)
    if user_cds_start_cdna_1 is None:
        sanity = Step4TranslationSanityPublic(
            translation_ok=False,
            reason="baseline_start_codon_not_present_in_user_transcript",
            baseline_cds_start_cdna_1=baseline_cds_start_cdna_1,
            baseline_cds_end_cdna_1=baseline_cds_end_cdna_1,
            user_cds_start_cdna_1=None,
            user_cds_end_cdna_1=None,
            start_codon_preserved=False,
            stop_codon_found=False,
            multiple_of_three=False,
            frameshift_likely=True,
            premature_stop_likely=None,
            protein_length=0,
            cds_length_nt=0,
            notes=["The canonical CDS start position is absent from the predicted user transcript."],
        )
        return user_cdna_seq, "", sanity, warnings

    start_triplet = user_cdna_seq[user_cds_start_cdna_1 - 1:user_cds_start_cdna_1 + 2]
    stop_end_1 = first_stop_codon_end_1(user_cdna_seq, start_cdna_1=user_cds_start_cdna_1)
    if stop_end_1 is not None:
        user_cds_seq = normalize_nt(user_cdna_seq[user_cds_start_cdna_1 - 1:stop_end_1])
        user_cds_end_cdna_1 = int(stop_end_1)
    else:
        user_cds_seq = trim_to_complete_codons(user_cdna_seq, start_cdna_1=user_cds_start_cdna_1)
        user_cds_end_cdna_1 = (user_cds_start_cdna_1 + len(user_cds_seq) - 1) if user_cds_seq else None
        warnings.append("No in-frame stop codon found after the preserved start codon; CDS was truncated to complete codons.")

    tr = translate_cds(user_cds_seq)
    normal_cds_len = len(normalize_nt(normal_cds_seq))
    frameshift_likely = None
    if user_cds_seq:
        frameshift_likely = ((len(user_cds_seq) - normal_cds_len) % 3) != 0
    premature_stop_likely = bool(tr.terminal_stop_present and len(tr.protein_seq) < len(normal_protein_seq))

    notes = list(warnings)
    if baseline_end_gene0 is not None and baseline_end_gene0 not in user_gene_to_cdna:
        notes.append("The canonical CDS end position is absent from the predicted user transcript; translation relies on first reachable in-frame stop codon.")
    if tr.reason and tr.reason not in {"missing_terminal_stop_codon"}:
        notes.append(f"translation_report={tr.reason}")

    sanity = Step4TranslationSanityPublic(
        translation_ok=bool(tr.ok),
        reason=tr.reason,
        baseline_cds_start_cdna_1=baseline_cds_start_cdna_1,
        baseline_cds_end_cdna_1=baseline_cds_end_cdna_1,
        user_cds_start_cdna_1=user_cds_start_cdna_1,
        user_cds_end_cdna_1=user_cds_end_cdna_1,
        start_codon_preserved=(start_triplet == "ATG"),
        start_codon_triplet=(start_triplet if start_triplet else None),
        stop_codon_found=bool(tr.terminal_stop_present),
        stop_codon_triplet=tr.trailing_stop_codon,
        multiple_of_three=bool(tr.multiple_of_three),
        internal_stop_positions_aa=list(tr.internal_stop_positions_aa),
        frameshift_likely=frameshift_likely,
        premature_stop_likely=premature_stop_likely,
        protein_length=int(tr.protein_length),
        cds_length_nt=len(user_cds_seq),
        notes=notes,
    )
    return user_cdna_seq, user_cds_seq, sanity, warnings



def _sequence_comparison(normal_protein_seq: str, user_protein_seq: str) -> Step4SequenceComparisonPublic:
    cmp = compare_sequences(normal_protein_seq, user_protein_seq)
    return Step4SequenceComparisonPublic(
        same_as_normal=bool(cmp.get("match")),
        normal_protein_length=int(cmp.get("expected_length") or 0),
        user_protein_length=int(cmp.get("observed_length") or 0),
        length_delta_aa=int((cmp.get("observed_length") or 0) - (cmp.get("expected_length") or 0)),
        first_mismatch_aa_1=(int(cmp["first_mismatch_aa_1"]) if cmp.get("first_mismatch_aa_1") is not None else None),
        normalized_edit_similarity=float(cmp.get("normalized_edit_similarity") or 0.0),
        notes=[],
    )



def _viewer_format(file_format: Optional[str]) -> Optional[str]:
    fmt = str(file_format or "").strip().lower()
    if not fmt:
        return None
    if fmt in {"cif", "mmcif"}:
        return "mmcif"
    if fmt == "bcif":
        return "bcif"
    if fmt == "pdb":
        return "pdb"
    return fmt



def _default_structure_asset(structures: Sequence[Step4StructureAssetPublic]) -> Optional[Step4StructureAssetPublic]:
    if not structures:
        return None
    for asset in structures:
        if asset.is_default:
            return asset
    return structures[0]



def _molstar_target(asset: Optional[Step4StructureAssetPublic]) -> Optional[Step4MolstarTargetPublic]:
    if not asset or not asset.signed_url:
        return None
    return Step4MolstarTargetPublic(
        structure_asset_id=asset.structure_asset_id,
        provider=asset.provider,
        source_db=asset.source_db,
        source_id=asset.source_id,
        source_chain_id=asset.source_chain_id,
        title=asset.title,
        url=asset.signed_url,
        format=asset.viewer_format or _viewer_format(asset.file_format),
    )



def _asset_public_from_payload(asset: Dict[str, Any]) -> Step4JobAssetPublic:
    bucket = str(asset.get("bucket") or "")
    path = str(asset.get("path") or "")
    url, expires = create_signed_storage_url(bucket, path) if bucket and path else (None, None)
    file_format = str(asset.get("file_format") or "bin")
    return Step4JobAssetPublic(
        kind=str(asset.get("kind") or "other"),  # type: ignore[arg-type]
        file_format=file_format,
        viewer_format=_viewer_format(file_format),
        bucket=bucket,
        path=path,
        signed_url=url,
        signed_url_expires_in=expires,
    )



def _job_public(row: Dict[str, Any]) -> Step4StructureJobPublic:
    payload = row.get("result_payload") or {}
    assets = [_asset_public_from_payload(a) for a in (payload.get("assets") or []) if isinstance(a, dict)]
    comparison = payload.get("comparison_to_normal") or {}
    structure_comparison_raw = payload.get("structure_comparison") or None
    structure_comparison = None
    if isinstance(structure_comparison_raw, dict) and structure_comparison_raw:
        structure_comparison = Step4StructureComparisonPublic(
            method=structure_comparison_raw.get("method"),
            tm_score_1=(float(structure_comparison_raw["tm_score_1"]) if structure_comparison_raw.get("tm_score_1") is not None else None),
            tm_score_2=(float(structure_comparison_raw["tm_score_2"]) if structure_comparison_raw.get("tm_score_2") is not None else None),
            rmsd=(float(structure_comparison_raw["rmsd"]) if structure_comparison_raw.get("rmsd") is not None else None),
            aligned_length=(int(structure_comparison_raw["aligned_length"]) if structure_comparison_raw.get("aligned_length") is not None else None),
            raw_text_excerpt=structure_comparison_raw.get("raw_text_excerpt"),
        )
    return Step4StructureJobPublic(
        job_id=str(row.get("job_id")),
        state_id=str(row.get("state_id")),
        provider=str(row.get("provider") or "unknown"),
        status=str(row.get("status") or "unknown"),
        external_job_id=row.get("external_job_id"),
        error_message=row.get("error_message"),
        created_at=(str(row.get("created_at")) if row.get("created_at") is not None else None),
        updated_at=(str(row.get("updated_at")) if row.get("updated_at") is not None else None),
        user_protein_sha256=payload.get("user_protein_sha256"),
        user_protein_length=(int(payload["user_protein_length"]) if payload.get("user_protein_length") is not None else None),
        reused_baseline_structure=bool(payload.get("reused_baseline_structure")),
        assets=assets,
        confidence=(payload.get("confidence") or {}),
        comparison_to_normal=comparison,
        structure_comparison=structure_comparison,
        result_payload=payload,
    )



def _hydrate_jobs_for_state(state_id: str) -> Tuple[List[Step4StructureJobPublic], Optional[Step4StructureJobPublic]]:
    rows = list_jobs_for_state(state_id)
    jobs = [_job_public(r) for r in rows]
    latest = jobs[0] if jobs else None
    return jobs, latest



def get_step4_for_state(state_id: str, *, include_sequences: bool = False) -> Step4StateResponse:
    state_row, disease_row, gene_row = _get_state_disease_gene(state_id)
    baseline = get_step4_baseline_for_state(state_id, include_sequences=True)

    # STEP3 -> event / current sequence
    step3 = predict_splicing_for_state(state_id, PredictSplicingRequest(return_target_sequence=True, include_parent_chain=True, include_disease_snv=True))
    primary_event = _pick_primary_event(step3.interpreted_events)

    region_rows = region_repo.list_regions_by_gene(str(gene_row["gene_id"]), include_sequence=True)
    canonical_exons = _canonical_exon_rows(region_rows)
    if not canonical_exons:
        raise HTTPException(status_code=404, detail=f"No canonical exon rows found for gene_id={gene_row['gene_id']}")

    current_gene_seq, effective_edits_raw, lineage_ids, representative_snv_applied, sequence_warnings = _build_current_gene_sequence(
        state_row=state_row,
        disease_row=disease_row,
        gene_row=gene_row,
        region_rows=region_rows,
    )

    canonical_gene_to_cdna, canonical_cdna_to_gene = _build_canonical_cdna_maps(canonical_exons)
    canonical_mrna_from_db = build_canonical_mrna_from_region_rows(canonical_exons)
    transcript_warnings: List[str] = []
    if normalize_nt(canonical_mrna_from_db) != normalize_nt(baseline.baseline_protein.canonical_mrna_seq or ""):
        transcript_warnings.append("Canonical exon assembly from region rows does not exactly match stored baseline canonical_mrna_seq.")

    blocks, included_exons, excluded_exons, inserted_block_count = _blocks_from_primary_event(
        canonical_exon_rows=canonical_exons,
        current_gene_seq=current_gene_seq,
        primary_event=primary_event,
        warnings=transcript_warnings,
    )
    user_cdna_seq, user_gene_to_cdna, public_blocks, block_warnings = _build_cdna_from_blocks(blocks=blocks, current_gene_seq=current_gene_seq)
    transcript_warnings.extend(block_warnings)

    user_cdna_seq, user_cds_seq, translation_sanity, translation_warnings = _translation_from_user_cdna(
        baseline_cds_start_cdna_1=baseline.baseline_protein.cds_start_cdna_1,
        baseline_cds_end_cdna_1=baseline.baseline_protein.cds_end_cdna_1,
        baseline_cdna_to_gene=canonical_cdna_to_gene,
        user_gene_to_cdna=user_gene_to_cdna,
        user_cdna_seq=user_cdna_seq,
        normal_cds_seq=baseline.baseline_protein.cds_seq or "",
        normal_protein_seq=baseline.baseline_protein.protein_seq or "",
    )
    user_protein_seq = translate_cds(user_cds_seq).protein_seq if user_cds_seq else ""
    comparison = _sequence_comparison(baseline.baseline_protein.protein_seq or "", user_protein_seq)

    jobs, latest_job = _hydrate_jobs_for_state(state_id)
    settings = get_settings()
    structure_prediction_enabled = bool(settings.STEP4_ENABLE_STRUCTURE_JOBS)
    structure_prediction_message = (
        None
        if structure_prediction_enabled
        else (
            "STEP4 user-structure prediction is disabled on this CPU-only deployment. "
            "Use the normal baseline structure now, then enable STEP4_ENABLE_STRUCTURE_JOBS=true on the GPU worker deployment for ColabFold jobs."
        )
    )
    normalized_structures = [s.model_copy(update={"viewer_format": _viewer_format(s.file_format)}) for s in baseline.structures]
    default_structure = _default_structure_asset(normalized_structures)
    can_reuse_normal_structure = bool(comparison.same_as_normal and normalized_structures)
    recommended_strategy = "reuse_baseline" if can_reuse_normal_structure else "predict_user_structure"

    user_track = Step4UserTrackPublic(
        state_id=state_id,
        representative_snv_applied=representative_snv_applied,
        state_lineage=lineage_ids,
        effective_edits=list(effective_edits_raw),
        predicted_transcript=Step4PredictedTranscriptPublic(
            primary_event_type=primary_event.event_type,
            primary_subtype=primary_event.subtype,
            blocks=public_blocks,
            included_exon_numbers=[int(x) for x in included_exons if x is not None],
            excluded_exon_numbers=[int(x) for x in excluded_exons],
            inserted_block_count=int(inserted_block_count),
            warnings=transcript_warnings,
        ),
        translation_sanity=translation_sanity,
        comparison_to_normal=comparison,
        protein_seq=(user_protein_seq if include_sequences else None),
        cds_seq=(user_cds_seq if include_sequences else None),
        cdna_seq=(user_cdna_seq if include_sequences else None),
        structure_prediction_enabled=structure_prediction_enabled,
        structure_prediction_message=structure_prediction_message,
        can_reuse_normal_structure=can_reuse_normal_structure,
        recommended_structure_strategy=recommended_strategy,  # type: ignore[arg-type]
        latest_structure_job=latest_job,
        structure_jobs=jobs,
        warnings=list(step3.warnings) + sequence_warnings + translation_warnings,
    )

    normal_track = Step4NormalTrackPublic(
        baseline_protein=baseline.baseline_protein,
        structures=normalized_structures,
        default_structure_asset_id=(default_structure.structure_asset_id if default_structure else baseline.default_structure_asset_id),
        default_structure=default_structure,
        molstar_default=_molstar_target(default_structure),
    )

    notes: List[str] = []
    if primary_event.event_type == "COMPLEX":
        notes.append("STEP4 user track currently uses the primary STEP3 event only; COMPLEX events fall back to canonical transcript blocks.")
    if not jobs and can_reuse_normal_structure:
        notes.append("User protein matches the normal baseline protein; a baseline structure can be reused without a new prediction job.")
    if structure_prediction_message:
        notes.append(structure_prediction_message)

    capabilities = Step4CapabilitiesPublic(
        normal_structure_ready=bool(normal_track.molstar_default and normal_track.molstar_default.url),
        user_track_available=True,
        structure_prediction_enabled=structure_prediction_enabled,
        create_job_endpoint_enabled=structure_prediction_enabled,
        prediction_mode=("job_queue" if structure_prediction_enabled else "disabled"),
        reason=structure_prediction_message,
    )

    return Step4StateResponse(
        disease_id=str(disease_row.get("disease_id") or ""),
        state_id=state_id,
        gene_id=str(gene_row.get("gene_id") or ""),
        gene_symbol=(str(gene_row.get("gene_symbol") or "") or None),
        normal_track=normal_track,
        user_track=user_track,
        capabilities=capabilities,
        ready_for_frontend=bool(normal_track.molstar_default and normal_track.molstar_default.url),
        notes=notes,
    )



def get_step4_job_public(job_id: str) -> Step4StructureJobPublic:
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"structure_job not found: {job_id}")
    return _job_public(row)
