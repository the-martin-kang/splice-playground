from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.schemas.splicing import (
    Step3FrontendSummary,
    Step3LogicThresholds,
    Step3SplicingEvent,
    Step3SpliceSite,
)

# ---------------------------------------------------------------------------
# Heuristic thresholds (frontend-ready, not final clinical rules)
# ---------------------------------------------------------------------------
# Broad spliceogenicity guidance:
# - ClinGen SVI calibration: max SpliceAI delta >= 0.2 is informative for spliceogenicity,
#   <=0.1 argues against spliceogenicity, and 0.1-0.2 is an uninformative zone.
# - SAI-10k-calc: pseudoexon gains often need lower thresholds than canonical-site loss,
#   with useful donor/acceptor-gain ranges around 0.02-0.05 and pseudoexon size 25-500 bp.
# This module uses those ideas as *service heuristics* for an educational frontend.
# It is not a clinical classifier.

GENERAL_SPLICEOGENIC_DELTA = 0.20
NON_SPLICEOGENIC_DELTA = 0.10
PSEUDOEXON_PAIR_DELTA = 0.05
WEAK_SITE_DELTA = 0.02
SITE_ALT_PROB_MIN = 0.05
SITE_ALT_PROB_STRONG = 0.20
SITE_ALT_PROB_VERY_STRONG = 0.50
RELATIVE_DROP_RATIO = 0.50
PSEUDOEXON_MIN_BP = 25
PSEUDOEXON_MAX_BP = 500
BOUNDARY_SHIFT_MAX_BP = 500
LOCAL_PEAK_RADIUS = 2
MAX_NOVEL_SITES_PER_CLASS = 8
MAX_EVENTS = 6


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _ratio(num: float, den: float) -> Optional[float]:
    if den <= 1e-8:
        return None
    return float(num / den)


def _find_region_for_pos(regions: Sequence[Dict[str, Any]], pos_gene0: int) -> Tuple[Optional[str], Optional[int]]:
    for r in regions:
        s = int(r["gene_start_idx"])
        e = int(r["gene_end_idx"])
        if s <= pos_gene0 <= e:
            return str(r["region_type"]), int(r["region_number"])
    return None, None


def _linked_exon_number(site_class: str, region_type: Optional[str], region_number: Optional[int]) -> Optional[int]:
    if region_type is None or region_number is None:
        return None
    if site_class == "acceptor":
        if region_type == "exon":
            return int(region_number)
        if region_type == "intron":
            return int(region_number) + 1
        return None
    if site_class == "donor":
        if region_type == "exon":
            return int(region_number)
        if region_type == "intron":
            return int(region_number)
        return None
    return None


def _acceptor_motif_ok(seq: str, target_start_gene0: int, pos_gene0: int) -> Optional[bool]:
    idx = int(pos_gene0 - target_start_gene0)
    if idx < 2 or idx > len(seq):
        return None
    return seq[idx - 2 : idx] == "AG"


def _donor_motif_ok(seq: str, target_start_gene0: int, pos_gene0: int) -> Optional[bool]:
    idx = int(pos_gene0 - target_start_gene0)
    if idx < 0 or idx + 3 > len(seq):
        return None
    return seq[idx + 1 : idx + 3] in {"GT", "GC"}


def _motif_ok(site_class: str, seq: str, target_start_gene0: int, pos_gene0: int) -> Optional[bool]:
    if site_class == "acceptor":
        return _acceptor_motif_ok(seq, target_start_gene0, pos_gene0)
    return _donor_motif_ok(seq, target_start_gene0, pos_gene0)


def _site_gain_confidence(delta_gain: float, alt_prob: float) -> str:
    if delta_gain >= GENERAL_SPLICEOGENIC_DELTA or alt_prob >= SITE_ALT_PROB_VERY_STRONG:
        return "high"
    if delta_gain >= PSEUDOEXON_PAIR_DELTA or alt_prob >= SITE_ALT_PROB_STRONG:
        return "medium"
    if delta_gain >= WEAK_SITE_DELTA or alt_prob >= SITE_ALT_PROB_MIN:
        return "low"
    return "none"


def _site_loss_confidence(delta_loss: float, ref_prob: float, alt_prob: float) -> str:
    ratio = _ratio(alt_prob, ref_prob)
    strong_relative_drop = ref_prob >= GENERAL_SPLICEOGENIC_DELTA and ratio is not None and ratio <= RELATIVE_DROP_RATIO
    if ref_prob >= GENERAL_SPLICEOGENIC_DELTA and (delta_loss >= GENERAL_SPLICEOGENIC_DELTA or strong_relative_drop):
        return "high"
    if ref_prob >= GENERAL_SPLICEOGENIC_DELTA and delta_loss >= PSEUDOEXON_PAIR_DELTA:
        return "medium"
    if delta_loss >= WEAK_SITE_DELTA:
        return "low"
    return "none"


def _event_confidence(score: float) -> str:
    if score >= 1.0:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _find_local_peaks(delta: np.ndarray, alt: np.ndarray, *, min_delta: float, max_n: int) -> List[int]:
    if delta.size == 0:
        return []
    cands: List[Tuple[int, float, float]] = []
    for i in range(delta.size):
        d = float(delta[i])
        a = float(alt[i])
        if d < min_delta:
            continue
        if a < SITE_ALT_PROB_MIN:
            continue
        lo = max(0, i - LOCAL_PEAK_RADIUS)
        hi = min(delta.size, i + LOCAL_PEAK_RADIUS + 1)
        if d + 1e-9 < float(np.max(delta[lo:hi])):
            continue
        cands.append((i, d, a))
    cands.sort(key=lambda t: (-t[1], -t[2], t[0]))
    keep: List[int] = []
    for idx, _, _ in cands:
        if any(abs(idx - kept) <= LOCAL_PEAK_RADIUS for kept in keep):
            continue
        keep.append(idx)
        if len(keep) >= max_n:
            break
    return keep


# ---------------------------------------------------------------------------
# Site construction
# ---------------------------------------------------------------------------

def _build_canonical_sites(
    *,
    target_regions: Sequence[Dict[str, Any]],
    gene_exon_count: Optional[int],
    target_start_gene0: int,
    target_len: int,
    target_seq_ref: str,
    target_seq_alt: str,
    prob_ref: np.ndarray,
    prob_alt: np.ndarray,
    snv_pos_gene0: int,
) -> List[Step3SpliceSite]:
    out: List[Step3SpliceSite] = []
    target_end_gene0 = int(target_start_gene0 + target_len)

    for r in target_regions:
        if str(r.get("region_type")) != "exon":
            continue
        exon_no = int(r["region_number"])
        exon_start = int(r["gene_start_idx"])
        exon_end = int(r["gene_end_idx"])

        # acceptor = exon start nucleotide (exclude exon1)
        if exon_no != 1 and target_start_gene0 <= exon_start < target_end_gene0:
            idx = exon_start - target_start_gene0
            ref_prob = float(prob_ref[1][idx])
            alt_prob = float(prob_alt[1][idx])
            delta_gain = max(0.0, alt_prob - ref_prob)
            delta_loss = max(0.0, ref_prob - alt_prob)
            conf = _site_loss_confidence(delta_loss, ref_prob, alt_prob) if delta_loss >= delta_gain else _site_gain_confidence(delta_gain, alt_prob)
            notes: List[str] = []
            if delta_loss >= GENERAL_SPLICEOGENIC_DELTA:
                notes.append("canonical acceptor loss exceeds general spliceogenicity threshold")
            ratio = _ratio(alt_prob, ref_prob)
            if ratio is not None and ratio <= RELATIVE_DROP_RATIO and ref_prob >= GENERAL_SPLICEOGENIC_DELTA:
                notes.append("canonical acceptor dropped by at least 50% relative to baseline")

            out.append(
                Step3SpliceSite(
                    site_class="acceptor",
                    site_kind="canonical",
                    pos_gene0=exon_start,
                    index_in_target_0=idx,
                    region_type="exon",
                    region_number=exon_no,
                    linked_exon_number=exon_no,
                    ref_prob=_clamp01(ref_prob),
                    alt_prob=_clamp01(alt_prob),
                    delta_gain=_clamp01(delta_gain),
                    delta_loss=_clamp01(delta_loss),
                    ratio_alt_over_ref=ratio,
                    motif_ref_ok=_acceptor_motif_ok(target_seq_ref, target_start_gene0, exon_start),
                    motif_alt_ok=_acceptor_motif_ok(target_seq_alt, target_start_gene0, exon_start),
                    distance_from_snv=abs(exon_start - snv_pos_gene0),
                    related_canonical_pos_gene0=exon_start,
                    related_canonical_exon_number=exon_no,
                    shift_bp=0,
                    confidence=conf,
                    notes=notes,
                )
            )

        # donor = exon end nucleotide (exclude last exon)
        if gene_exon_count is None or exon_no != gene_exon_count:
            if target_start_gene0 <= exon_end < target_end_gene0:
                idx = exon_end - target_start_gene0
                ref_prob = float(prob_ref[2][idx])
                alt_prob = float(prob_alt[2][idx])
                delta_gain = max(0.0, alt_prob - ref_prob)
                delta_loss = max(0.0, ref_prob - alt_prob)
                conf = _site_loss_confidence(delta_loss, ref_prob, alt_prob) if delta_loss >= delta_gain else _site_gain_confidence(delta_gain, alt_prob)
                notes = []
                if delta_loss >= GENERAL_SPLICEOGENIC_DELTA:
                    notes.append("canonical donor loss exceeds general spliceogenicity threshold")
                ratio = _ratio(alt_prob, ref_prob)
                if ratio is not None and ratio <= RELATIVE_DROP_RATIO and ref_prob >= GENERAL_SPLICEOGENIC_DELTA:
                    notes.append("canonical donor dropped by at least 50% relative to baseline")

                out.append(
                    Step3SpliceSite(
                        site_class="donor",
                        site_kind="canonical",
                        pos_gene0=exon_end,
                        index_in_target_0=idx,
                        region_type="exon",
                        region_number=exon_no,
                        linked_exon_number=exon_no,
                        ref_prob=_clamp01(ref_prob),
                        alt_prob=_clamp01(alt_prob),
                        delta_gain=_clamp01(delta_gain),
                        delta_loss=_clamp01(delta_loss),
                        ratio_alt_over_ref=ratio,
                        motif_ref_ok=_donor_motif_ok(target_seq_ref, target_start_gene0, exon_end),
                        motif_alt_ok=_donor_motif_ok(target_seq_alt, target_start_gene0, exon_end),
                        distance_from_snv=abs(exon_end - snv_pos_gene0),
                        related_canonical_pos_gene0=exon_end,
                        related_canonical_exon_number=exon_no,
                        shift_bp=0,
                        confidence=conf,
                        notes=notes,
                    )
                )

    out.sort(key=lambda s: (s.pos_gene0, 0 if s.site_class == "acceptor" else 1))
    return out


def _build_canonical_lookup(canonical_sites: Sequence[Step3SpliceSite]) -> Dict[Tuple[str, int], Step3SpliceSite]:
    out: Dict[Tuple[str, int], Step3SpliceSite] = {}
    for s in canonical_sites:
        if s.linked_exon_number is None:
            continue
        out[(s.site_class, int(s.linked_exon_number))] = s
    return out


def _build_novel_sites(
    *,
    target_regions: Sequence[Dict[str, Any]],
    canonical_sites: Sequence[Step3SpliceSite],
    target_start_gene0: int,
    target_len: int,
    target_seq_ref: str,
    target_seq_alt: str,
    prob_ref: np.ndarray,
    prob_alt: np.ndarray,
    snv_pos_gene0: int,
) -> List[Step3SpliceSite]:
    out: List[Step3SpliceSite] = []
    canonical_pos = {
        "acceptor": {int(s.pos_gene0) for s in canonical_sites if s.site_class == "acceptor"},
        "donor": {int(s.pos_gene0) for s in canonical_sites if s.site_class == "donor"},
    }
    canonical_lookup = _build_canonical_lookup(canonical_sites)

    for site_class, class_idx in (("acceptor", 1), ("donor", 2)):
        delta_gain = np.maximum(prob_alt[class_idx] - prob_ref[class_idx], 0.0)
        peak_indices = _find_local_peaks(delta_gain, prob_alt[class_idx], min_delta=WEAK_SITE_DELTA, max_n=MAX_NOVEL_SITES_PER_CLASS)
        for idx in peak_indices:
            pos_gene0 = int(target_start_gene0 + idx)
            if pos_gene0 in canonical_pos[site_class]:
                continue
            ref_prob = float(prob_ref[class_idx][idx])
            alt_prob = float(prob_alt[class_idx][idx])
            d_gain = max(0.0, alt_prob - ref_prob)
            d_loss = max(0.0, ref_prob - alt_prob)
            region_type, region_number = _find_region_for_pos(target_regions, pos_gene0)
            linked_exon = _linked_exon_number(site_class, region_type, region_number)
            related = canonical_lookup.get((site_class, linked_exon)) if linked_exon is not None else None
            motif_ref_ok = _motif_ok(site_class, target_seq_ref, target_start_gene0, pos_gene0)
            motif_alt_ok = _motif_ok(site_class, target_seq_alt, target_start_gene0, pos_gene0)
            notes: List[str] = []
            if d_gain >= GENERAL_SPLICEOGENIC_DELTA:
                notes.append("novel site gain exceeds general spliceogenicity threshold")
            elif d_gain >= PSEUDOEXON_PAIR_DELTA:
                notes.append("novel site gain exceeds pseudoexon pairing threshold")
            if motif_alt_ok is False:
                notes.append("alt sequence does not show canonical local AG/GT(GC) motif")
            if linked_exon is not None and related is not None:
                shift_bp = int(pos_gene0 - int(related.pos_gene0))
            else:
                shift_bp = None
            out.append(
                Step3SpliceSite(
                    site_class=site_class,  # type: ignore[arg-type]
                    site_kind="novel",
                    pos_gene0=pos_gene0,
                    index_in_target_0=idx,
                    region_type=region_type,  # type: ignore[arg-type]
                    region_number=region_number,
                    linked_exon_number=linked_exon,
                    ref_prob=_clamp01(ref_prob),
                    alt_prob=_clamp01(alt_prob),
                    delta_gain=_clamp01(d_gain),
                    delta_loss=_clamp01(d_loss),
                    ratio_alt_over_ref=_ratio(alt_prob, ref_prob),
                    motif_ref_ok=motif_ref_ok,
                    motif_alt_ok=motif_alt_ok,
                    distance_from_snv=abs(pos_gene0 - snv_pos_gene0),
                    related_canonical_pos_gene0=(int(related.pos_gene0) if related is not None else None),
                    related_canonical_exon_number=(int(related.linked_exon_number) if related and related.linked_exon_number is not None else linked_exon),
                    shift_bp=shift_bp,
                    confidence=_site_gain_confidence(d_gain, alt_prob),
                    notes=notes,
                )
            )

    out.sort(key=lambda s: (-float(s.delta_gain), -float(s.alt_prob), abs(int(s.pos_gene0) - int(snv_pos_gene0))))
    return out


# ---------------------------------------------------------------------------
# Event interpretation
# ---------------------------------------------------------------------------

def _pseudoexon_events(novel_sites: Sequence[Step3SpliceSite]) -> List[Step3SplicingEvent]:
    acceptors = [
        s
        for s in novel_sites
        if s.site_class == "acceptor"
        and s.region_type == "intron"
        and s.region_number is not None
        and s.confidence in {"high", "medium", "low"}
        and s.motif_alt_ok is not False
    ]
    donors = [
        s
        for s in novel_sites
        if s.site_class == "donor"
        and s.region_type == "intron"
        and s.region_number is not None
        and s.confidence in {"high", "medium", "low"}
        and s.motif_alt_ok is not False
    ]

    out: List[Step3SplicingEvent] = []
    for a in acceptors:
        for d in donors:
            if a.region_number != d.region_number:
                continue
            if int(a.pos_gene0) >= int(d.pos_gene0):
                continue
            size_bp = int(d.pos_gene0) - int(a.pos_gene0) + 1
            if size_bp < PSEUDOEXON_MIN_BP or size_bp > PSEUDOEXON_MAX_BP:
                continue
            score = float(a.delta_gain + d.delta_gain + 0.5 * (a.alt_prob + d.alt_prob))
            confidence = _event_confidence(score)
            intron_no = int(a.region_number)
            notes = []
            if a.delta_gain >= PSEUDOEXON_PAIR_DELTA and d.delta_gain >= PSEUDOEXON_PAIR_DELTA:
                notes.append("paired acceptor/donor gains exceed pseudoexon pairing threshold")
            out.append(
                Step3SplicingEvent(
                    event_type="PSEUDO_EXON",
                    subtype="PSEUDOEXON_INSERTION",
                    confidence=confidence,  # type: ignore[arg-type]
                    score=score,
                    summary=(
                        f"Novel intronic acceptor/donor pair in intron {intron_no} predicts a {size_bp} bp pseudoexon "
                        f"between exon {intron_no} and exon {intron_no + 1}."
                    ),
                    acceptor_pos_gene0=int(a.pos_gene0),
                    donor_pos_gene0=int(d.pos_gene0),
                    canonical_acceptor_pos_gene0=None,
                    canonical_donor_pos_gene0=None,
                    size_bp=size_bp,
                    affected_exon_numbers=[intron_no, intron_no + 1],
                    affected_intron_numbers=[intron_no],
                    notes=notes,
                )
            )
    out.sort(key=lambda e: (-float(e.score), e.acceptor_pos_gene0 or 0, e.donor_pos_gene0 or 0))
    return out


def _boundary_shift_events(
    *,
    novel_sites: Sequence[Step3SpliceSite],
    canonical_lookup: Dict[Tuple[str, int], Step3SpliceSite],
    used_novel_positions: set[int],
) -> List[Step3SplicingEvent]:
    out: List[Step3SplicingEvent] = []
    for s in novel_sites:
        if int(s.pos_gene0) in used_novel_positions:
            continue
        if s.linked_exon_number is None:
            continue
        related = canonical_lookup.get((s.site_class, int(s.linked_exon_number)))
        if related is None:
            continue
        shift_bp = s.shift_bp
        if shift_bp in (None, 0):
            continue
        if abs(int(shift_bp)) > BOUNDARY_SHIFT_MAX_BP:
            continue
        if s.site_class == "acceptor":
            if s.region_type == "intron" and int(s.pos_gene0) < int(related.pos_gene0):
                subtype = "EXON_EXTENSION_5P"
                summary = f"Novel acceptor {abs(int(shift_bp))} bp upstream of the canonical acceptor of exon {s.linked_exon_number} predicts a 5' exon extension."
            elif s.region_type == "exon" and int(s.pos_gene0) > int(related.pos_gene0):
                subtype = "EXON_SHORTENING_5P"
                summary = f"Novel acceptor {abs(int(shift_bp))} bp inside exon {s.linked_exon_number} predicts 5' exon shortening."
            else:
                continue
            canonical_acceptor_pos = int(related.pos_gene0)
            canonical_donor_pos = None
        else:
            if s.region_type == "exon" and int(s.pos_gene0) < int(related.pos_gene0):
                subtype = "EXON_SHORTENING_3P"
                summary = f"Novel donor {abs(int(shift_bp))} bp inside exon {s.linked_exon_number} predicts 3' exon shortening."
            elif s.region_type == "intron" and int(s.pos_gene0) > int(related.pos_gene0):
                subtype = "EXON_EXTENSION_3P"
                summary = f"Novel donor {abs(int(shift_bp))} bp downstream of exon {s.linked_exon_number} predicts a 3' exon extension."
            else:
                continue
            canonical_acceptor_pos = None
            canonical_donor_pos = int(related.pos_gene0)

        score = float(s.delta_gain + max(0.0, float(related.delta_loss)) + 0.5 * float(s.alt_prob))
        notes: List[str] = []
        if float(related.delta_loss) >= PSEUDOEXON_PAIR_DELTA:
            notes.append("paired with measurable loss at the canonical boundary")
        out.append(
            Step3SplicingEvent(
                event_type="BOUNDARY_SHIFT",
                subtype=subtype,
                confidence=_event_confidence(score),  # type: ignore[arg-type]
                score=score,
                summary=summary,
                acceptor_pos_gene0=(int(s.pos_gene0) if s.site_class == "acceptor" else None),
                donor_pos_gene0=(int(s.pos_gene0) if s.site_class == "donor" else None),
                canonical_acceptor_pos_gene0=canonical_acceptor_pos,
                canonical_donor_pos_gene0=canonical_donor_pos,
                size_bp=abs(int(shift_bp)),
                affected_exon_numbers=[int(s.linked_exon_number)],
                affected_intron_numbers=[],
                notes=notes,
            )
        )
    out.sort(key=lambda e: (-float(e.score), e.size_bp or 0))
    return out


def _snv_hits_acceptor_core(acceptor_pos: int, snv_pos: int) -> bool:
    return snv_pos in {acceptor_pos - 2, acceptor_pos - 1, acceptor_pos}


def _snv_hits_donor_core(donor_pos: int, snv_pos: int) -> bool:
    return snv_pos in {donor_pos, donor_pos + 1, donor_pos + 2}


def _exon_exclusion_events(
    *,
    canonical_sites: Sequence[Step3SpliceSite],
    boundary_events: Sequence[Step3SplicingEvent],
    snv_pos_gene0: int,
) -> List[Step3SplicingEvent]:
    by_exon: Dict[int, Dict[str, Step3SpliceSite]] = {}
    for s in canonical_sites:
        if s.linked_exon_number is None:
            continue
        ex = int(s.linked_exon_number)
        by_exon.setdefault(ex, {})[s.site_class] = s

    boundary_exons = {ex for ev in boundary_events for ex in ev.affected_exon_numbers}
    out: List[Step3SplicingEvent] = []
    for exon_no, pair in by_exon.items():
        acc = pair.get("acceptor")
        don = pair.get("donor")
        if acc is None and don is None:
            continue

        acc_loss = float(acc.delta_loss) if acc else 0.0
        don_loss = float(don.delta_loss) if don else 0.0
        acc_ref = float(acc.ref_prob) if acc else 0.0
        don_ref = float(don.ref_prob) if don else 0.0
        acc_ratio_drop = bool(acc and acc.ratio_alt_over_ref is not None and acc.ratio_alt_over_ref <= RELATIVE_DROP_RATIO and acc_ref >= GENERAL_SPLICEOGENIC_DELTA)
        don_ratio_drop = bool(don and don.ratio_alt_over_ref is not None and don.ratio_alt_over_ref <= RELATIVE_DROP_RATIO and don_ref >= GENERAL_SPLICEOGENIC_DELTA)
        acc_strong = (acc_ref >= GENERAL_SPLICEOGENIC_DELTA) and (acc_loss >= GENERAL_SPLICEOGENIC_DELTA or acc_ratio_drop)
        don_strong = (don_ref >= GENERAL_SPLICEOGENIC_DELTA) and (don_loss >= GENERAL_SPLICEOGENIC_DELTA or don_ratio_drop)
        if not (acc_strong or don_strong):
            continue

        score = acc_loss + don_loss
        notes: List[str] = []
        if exon_no in boundary_exons:
            notes.append("same exon also has a boundary-shift candidate; exon exclusion is not unique explanation")
            score *= 0.6
        if acc and _snv_hits_acceptor_core(int(acc.pos_gene0), int(snv_pos_gene0)):
            notes.append("SNV overlaps canonical acceptor core motif")
            score += 0.2
        if don and _snv_hits_donor_core(int(don.pos_gene0), int(snv_pos_gene0)):
            notes.append("SNV overlaps canonical donor core motif")
            score += 0.2

        if acc_strong and don_strong:
            summary = f"Both canonical splice boundaries of exon {exon_no} weaken, supporting exon exclusion / exon skipping."
        elif don_strong:
            summary = f"Canonical donor of exon {exon_no} weakens strongly without a clear compensatory donor, supporting exon exclusion / exon skipping."
        else:
            summary = f"Canonical acceptor of exon {exon_no} weakens strongly without a clear compensatory acceptor, supporting exon exclusion / exon skipping."

        out.append(
            Step3SplicingEvent(
                event_type="EXON_EXCLUSION",
                subtype="LIKELY_EXON_SKIP",
                confidence=_event_confidence(score),  # type: ignore[arg-type]
                score=score,
                summary=summary,
                acceptor_pos_gene0=(int(acc.pos_gene0) if acc else None),
                donor_pos_gene0=(int(don.pos_gene0) if don else None),
                canonical_acceptor_pos_gene0=(int(acc.pos_gene0) if acc else None),
                canonical_donor_pos_gene0=(int(don.pos_gene0) if don else None),
                size_bp=None,
                affected_exon_numbers=[exon_no],
                affected_intron_numbers=[],
                notes=notes,
            )
        )
    out.sort(key=lambda e: (-float(e.score), e.affected_exon_numbers[0] if e.affected_exon_numbers else 0))
    return out


def _canonical_strengthening_events(canonical_sites: Sequence[Step3SpliceSite]) -> List[Step3SplicingEvent]:
    by_exon: Dict[int, Dict[str, Step3SpliceSite]] = {}
    for s in canonical_sites:
        if s.linked_exon_number is None:
            continue
        by_exon.setdefault(int(s.linked_exon_number), {})[s.site_class] = s

    out: List[Step3SplicingEvent] = []
    for exon_no, pair in by_exon.items():
        acc = pair.get("acceptor")
        don = pair.get("donor")
        gains = []
        if acc and acc.delta_gain >= PSEUDOEXON_PAIR_DELTA and acc.alt_prob >= SITE_ALT_PROB_MIN:
            gains.append(float(acc.delta_gain))
        if don and don.delta_gain >= PSEUDOEXON_PAIR_DELTA and don.alt_prob >= SITE_ALT_PROB_MIN:
            gains.append(float(don.delta_gain))
        if not gains:
            continue
        score = sum(gains)
        summary = f"Canonical splice site strength increases around exon {exon_no}, suggesting improved exon inclusion."
        out.append(
            Step3SplicingEvent(
                event_type="CANONICAL_STRENGTHENING",
                subtype="EXON_INCLUSION_RESCUE",
                confidence=_event_confidence(score),  # type: ignore[arg-type]
                score=score,
                summary=summary,
                acceptor_pos_gene0=(int(acc.pos_gene0) if acc and acc.delta_gain >= PSEUDOEXON_PAIR_DELTA else None),
                donor_pos_gene0=(int(don.pos_gene0) if don and don.delta_gain >= PSEUDOEXON_PAIR_DELTA else None),
                canonical_acceptor_pos_gene0=(int(acc.pos_gene0) if acc else None),
                canonical_donor_pos_gene0=(int(don.pos_gene0) if don else None),
                size_bp=None,
                affected_exon_numbers=[exon_no],
                affected_intron_numbers=[],
                notes=["useful for rescue-style edits such as exon inclusion restoration"],
            )
        )
    out.sort(key=lambda e: (-float(e.score), e.affected_exon_numbers[0] if e.affected_exon_numbers else 0))
    return out


def _logic_thresholds() -> Step3LogicThresholds:
    return Step3LogicThresholds(
        general_spliceogenicity_delta=GENERAL_SPLICEOGENIC_DELTA,
        non_spliceogenicity_delta=NON_SPLICEOGENIC_DELTA,
        pseudoexon_pair_delta=PSEUDOEXON_PAIR_DELTA,
        weak_site_delta=WEAK_SITE_DELTA,
        site_alt_prob_min=SITE_ALT_PROB_MIN,
        site_alt_prob_strong=SITE_ALT_PROB_STRONG,
        pseudoexon_size_min_bp=PSEUDOEXON_MIN_BP,
        pseudoexon_size_max_bp=PSEUDOEXON_MAX_BP,
        relative_drop_ratio=RELATIVE_DROP_RATIO,
        notes=[
            "Use baseline delta as the primary signal; do not use absolute probability alone.",
            "0.2 follows common high-recall/general spliceogenicity guidance for SpliceAI-like delta scores.",
            "0.05 is retained for donor/acceptor pairing in deep-intronic pseudoexon-like events.",
            "25-500 bp is the preferred pseudoexon size window.",
        ],
    )


def interpret_step3(
    *,
    target_regions: Sequence[Dict[str, Any]],
    gene_exon_count: Optional[int],
    target_start_gene0: int,
    target_len: int,
    target_seq_ref: str,
    target_seq_alt: str,
    prob_ref: np.ndarray,
    prob_alt: np.ndarray,
    snv_pos_gene0: int,
    seed_mode: Optional[str] = None,
) -> Dict[str, Any]:
    canonical_sites = _build_canonical_sites(
        target_regions=target_regions,
        gene_exon_count=gene_exon_count,
        target_start_gene0=target_start_gene0,
        target_len=target_len,
        target_seq_ref=target_seq_ref,
        target_seq_alt=target_seq_alt,
        prob_ref=prob_ref,
        prob_alt=prob_alt,
        snv_pos_gene0=snv_pos_gene0,
    )
    canonical_lookup = _build_canonical_lookup(canonical_sites)
    novel_sites = _build_novel_sites(
        target_regions=target_regions,
        canonical_sites=canonical_sites,
        target_start_gene0=target_start_gene0,
        target_len=target_len,
        target_seq_ref=target_seq_ref,
        target_seq_alt=target_seq_alt,
        prob_ref=prob_ref,
        prob_alt=prob_alt,
        snv_pos_gene0=snv_pos_gene0,
    )

    pseudo_events = _pseudoexon_events(novel_sites)
    used_novel_positions: set[int] = set()
    for ev in pseudo_events:
        if ev.acceptor_pos_gene0 is not None:
            used_novel_positions.add(int(ev.acceptor_pos_gene0))
        if ev.donor_pos_gene0 is not None:
            used_novel_positions.add(int(ev.donor_pos_gene0))

    boundary_events = _boundary_shift_events(
        novel_sites=novel_sites,
        canonical_lookup=canonical_lookup,
        used_novel_positions=used_novel_positions,
    )
    exclusion_events = _exon_exclusion_events(
        canonical_sites=canonical_sites,
        boundary_events=boundary_events,
        snv_pos_gene0=snv_pos_gene0,
    )
    strengthening_events = _canonical_strengthening_events(canonical_sites)

    all_events = pseudo_events + exclusion_events + boundary_events + strengthening_events
    all_events.sort(key=lambda ev: (-float(ev.score), ev.event_type, ev.summary))
    all_events = all_events[:MAX_EVENTS]

    if all_events:
        primary = all_events[0]
        headline = primary.summary
        if seed_mode == "reference_is_current" and primary.event_type == "CANONICAL_STRENGTHENING":
            headline = primary.summary + " (reference_is_current case: rescue-style interpretation is preferred)."
        frontend_summary = Step3FrontendSummary(
            primary_event_type=primary.event_type,
            primary_subtype=primary.subtype,
            confidence=primary.confidence,
            headline=headline,
            interpretation_basis=(
                "delta-first heuristics combining canonical-site loss, novel-site gain, site pairing, "
                "local motif sanity, and region context"
            ),
        )
    else:
        frontend_summary = Step3FrontendSummary(
            primary_event_type="NONE",
            primary_subtype=None,
            confidence="low",
            headline="No strong STEP3 event heuristic was triggered; inspect site-level deltas and plot directly.",
            interpretation_basis="delta-first heuristics; ambiguous / low-signal cases remain plot-driven",
        )

    return {
        "canonical_sites": canonical_sites,
        "novel_sites": novel_sites,
        "interpreted_events": all_events,
        "frontend_summary": frontend_summary,
        "logic_thresholds": _logic_thresholds(),
    }
