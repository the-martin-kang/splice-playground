from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional


CODON_TABLE: Dict[str, str] = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


@dataclass(frozen=True)
class TranslationReport:
    normalized_cds: str
    protein_seq: str
    protein_length: int
    multiple_of_three: bool
    start_codon_ok: bool
    terminal_stop_present: bool
    internal_stop_positions_aa: List[int]
    trailing_stop_codon: Optional[str]
    has_ambiguous_bases: bool
    ok: bool
    reason: Optional[str] = None


def normalize_nt(seq: str) -> str:
    return "".join(ch for ch in (seq or "").upper() if not ch.isspace())


def normalize_aa(seq: str) -> str:
    s = "".join(ch for ch in (seq or "").upper() if not ch.isspace())
    return s[:-1] if s.endswith("*") else s


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def translate_cds(cds_seq: str) -> TranslationReport:
    cds = normalize_nt(cds_seq)
    if not cds:
        return TranslationReport(
            normalized_cds="",
            protein_seq="",
            protein_length=0,
            multiple_of_three=False,
            start_codon_ok=False,
            terminal_stop_present=False,
            internal_stop_positions_aa=[],
            trailing_stop_codon=None,
            has_ambiguous_bases=False,
            ok=False,
            reason="empty_cds",
        )

    has_ambiguous = any(b not in {"A", "C", "G", "T"} for b in cds)
    multiple_of_three = (len(cds) % 3 == 0)
    start_ok = cds.startswith("ATG")

    aa: List[str] = []
    internal_stops: List[int] = []
    trailing_stop_codon: Optional[str] = None
    terminal_stop_present = False

    usable_len = len(cds) - (len(cds) % 3)
    for i in range(0, usable_len, 3):
        codon = cds[i:i + 3]
        if len(codon) < 3:
            break
        aa_idx = (i // 3) + 1
        mapped = CODON_TABLE.get(codon, "X")
        if mapped == "*":
            if i == usable_len - 3:
                terminal_stop_present = True
                trailing_stop_codon = codon
            else:
                internal_stops.append(aa_idx)
            aa.append("*")
        else:
            aa.append(mapped)

    protein = "".join(aa)
    if protein.endswith("*"):
        protein = protein[:-1]

    ok = bool(multiple_of_three and start_ok and terminal_stop_present and not internal_stops and not has_ambiguous)
    reason: Optional[str] = None
    if not ok:
        if has_ambiguous:
            reason = "ambiguous_base_in_cds"
        elif not multiple_of_three:
            reason = "cds_length_not_multiple_of_three"
        elif not start_ok:
            reason = "missing_start_codon"
        elif internal_stops:
            reason = "internal_stop_codon"
        elif not terminal_stop_present:
            reason = "missing_terminal_stop_codon"
        else:
            reason = "translation_failed"

    return TranslationReport(
        normalized_cds=cds,
        protein_seq=protein,
        protein_length=len(protein),
        multiple_of_three=multiple_of_three,
        start_codon_ok=start_ok,
        terminal_stop_present=terminal_stop_present,
        internal_stop_positions_aa=internal_stops,
        trailing_stop_codon=trailing_stop_codon,
        has_ambiguous_bases=has_ambiguous,
        ok=ok,
        reason=reason,
    )


def compare_sequences(expected: str, observed: str) -> Dict[str, object]:
    exp = normalize_aa(expected)
    obs = normalize_aa(observed)
    same = exp == obs
    first_mismatch = None
    if not same:
        max_len = min(len(exp), len(obs))
        for i in range(max_len):
            if exp[i] != obs[i]:
                first_mismatch = i + 1  # 1-based AA position
                break
        if first_mismatch is None and len(exp) != len(obs):
            first_mismatch = max_len + 1
    return {
        "match": same,
        "expected_length": len(exp),
        "observed_length": len(obs),
        "first_mismatch_aa_1": first_mismatch,
    }
