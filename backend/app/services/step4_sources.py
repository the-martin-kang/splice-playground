from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from app.core.config import get_settings
from app.services.protein_translation import compare_sequences, normalize_aa, normalize_nt, translate_cds


@dataclass(frozen=True)
class TranscriptReferenceBundle:
    gene_symbol: str
    transcript_selection_reason: str
    transcript_kind: str
    canonical_source: Optional[str]

    ensembl_gene_id: Optional[str]
    ensembl_transcript_id: str
    ensembl_protein_id: Optional[str]

    refseq_transcript_id: Optional[str]
    refseq_protein_id: Optional[str]
    uniprot_accession: Optional[str]

    cdna_seq: str
    cds_seq: str
    protein_seq: str
    cds_start_cdna_1: Optional[int]
    cds_end_cdna_1: Optional[int]

    provenance: Dict[str, Any]


class HttpClient:
    def __init__(self) -> None:
        s = get_settings()
        self.settings = s
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": s.HTTP_USER_AGENT,
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        })

    def get_json(self, url: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        res = self.session.get(url, params=params, timeout=self.settings.EXTERNAL_API_TIMEOUT_SECONDS)
        res.raise_for_status()
        return res.json()

    def get_text(self, url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> str:
        hdrs = dict(self.session.headers)
        if headers:
            hdrs.update(headers)
        res = self.session.get(url, params=params, headers=hdrs, timeout=self.settings.EXTERNAL_API_TIMEOUT_SECONDS)
        res.raise_for_status()
        return res.text

    def get_bytes(self, url: str, *, headers: Optional[Dict[str, str]] = None) -> bytes:
        hdrs = dict(self.session.headers)
        if headers:
            hdrs.update(headers)
        res = self.session.get(url, headers=hdrs, timeout=self.settings.EXTERNAL_API_TIMEOUT_SECONDS)
        res.raise_for_status()
        return res.content


def _norm_id(x: Optional[str]) -> Optional[str]:
    if not x:
        return None
    return str(x).split(".", 1)[0]


def _pick_first(values: Iterable[Optional[str]]) -> Optional[str]:
    for v in values:
        if v:
            return str(v)
    return None


def _as_list(obj: Any) -> List[Any]:
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    return [obj]


def _parse_fasta_sequence(text: str) -> str:
    seq_lines: List[str] = []
    for line in (text or "").splitlines():
        if not line or line.startswith(">"):
            continue
        seq_lines.append(line.strip())
    return "".join(seq_lines).upper()


class EnsemblClient(HttpClient):
    def _url(self, path: str) -> str:
        return self.settings.ENSEMBL_REST_BASE.rstrip("/") + path

    def lookup_symbol(self, symbol: str) -> Dict[str, Any]:
        return self.get_json(
            self._url(f"/lookup/symbol/homo_sapiens/{symbol}"),
            params={"expand": 1, "mane": 1},
        )

    def lookup_id(self, stable_id: str) -> Dict[str, Any]:
        return self.get_json(
            self._url(f"/lookup/id/{stable_id}"),
            params={"expand": 1, "mane": 1},
        )

    def xrefs_id(self, stable_id: str) -> List[Dict[str, Any]]:
        data = self.get_json(self._url(f"/xrefs/id/{stable_id}"))
        return data if isinstance(data, list) else []

    def xrefs_name(self, name: str) -> List[Dict[str, Any]]:
        data = self.get_json(self._url(f"/xrefs/name/homo_sapiens/{name}"))
        return data if isinstance(data, list) else []

    def sequence_id(self, stable_id: str, seq_type: str) -> str:
        return self.get_text(
            self._url(f"/sequence/id/{stable_id}"),
            params={"type": seq_type},
            headers={"Accept": "text/plain"},
        ).strip().upper()


class UniProtClient(HttpClient):
    def _url(self, path: str) -> str:
        return self.settings.UNIPROT_REST_BASE.rstrip("/") + path

    def entry_json(self, accession: str) -> Dict[str, Any]:
        return self.get_json(self._url(f"/uniprotkb/{accession}.json"))


class NCBIClient(HttpClient):
    def __init__(self) -> None:
        super().__init__()
        self._last_request_ts = 0.0

    def _courtesy_sleep(self) -> None:
        # Stay comfortably below 3 req/s without an API key.
        elapsed = time.time() - self._last_request_ts
        min_interval = 0.35 if not self.settings.NCBI_API_KEY else 0.11
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_ts = time.time()

    def efetch_fasta(self, *, db: str, accession: str) -> str:
        self._courtesy_sleep()
        params: Dict[str, Any] = {
            "db": db,
            "id": accession,
            "rettype": "fasta",
            "retmode": "text",
        }
        if self.settings.NCBI_TOOL:
            params["tool"] = self.settings.NCBI_TOOL
        if self.settings.NCBI_EMAIL:
            params["email"] = self.settings.NCBI_EMAIL
        if self.settings.NCBI_API_KEY:
            params["api_key"] = self.settings.NCBI_API_KEY
        txt = self.get_text("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params=params)
        return _parse_fasta_sequence(txt)


class PDBeClient(HttpClient):
    def _url(self, path: str) -> str:
        return self.settings.PDBe_API_BASE.rstrip("/") + path

    def best_structures(self, uniprot_accession: str) -> List[Dict[str, Any]]:
        data = self.get_json(self._url(f"/uniprot/best_structures/{uniprot_accession}"))
        if isinstance(data, dict):
            # Common shape: {"P38398": [{...}, {...}]}
            rows = data.get(uniprot_accession) or data.get(uniprot_accession.upper())
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
            # Other shapes: a single dict with key "best_structures"
            rows = data.get("best_structures")
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
        return data if isinstance(data, list) else []


class AlphaFoldClient(HttpClient):
    def _url(self, accession: str) -> str:
        return self.settings.ALPHAFOLD_API_BASE.rstrip("/") + f"/{accession}"

    def prediction(self, accession: str) -> List[Dict[str, Any]]:
        data = self.get_json(self._url(accession))
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict):
            if isinstance(data.get("results"), list):
                return [r for r in data["results"] if isinstance(r, dict)]
            return [data]
        return []


def _transcripts_from_lookup(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("Transcript", "transcripts", "Transcripts"):
        vals = obj.get(key)
        if isinstance(vals, list):
            return [v for v in vals if isinstance(v, dict)]
    return []


def _extract_translation_obj(transcript_obj: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("Translation", "translation"):
        val = transcript_obj.get(key)
        if isinstance(val, dict):
            return val
    return {}


def _transcript_kind_from_obj(t: Dict[str, Any], fallback_source: Optional[str]) -> str:
    if any(k in t for k in ("MANE_Select", "mane_select")):
        return "MANE_Select"
    if any(k in t for k in ("MANE_Plus_Clinical", "mane_plus_clinical")):
        return "MANE_Plus_Clinical"
    if bool(t.get("is_canonical")):
        return "Ensembl_canonical"
    if fallback_source:
        return str(fallback_source)
    return "other"


def _match_transcript_candidate(
    transcripts: List[Dict[str, Any]],
    canonical_transcript_id: Optional[str],
    ensembl_client: EnsemblClient,
) -> Tuple[Optional[Dict[str, Any]], str]:
    target = _norm_id(canonical_transcript_id)
    if target:
        if target.startswith("ENST"):
            for t in transcripts:
                if _norm_id(t.get("id")) == target:
                    return t, "matched_gene.canonical_transcript_id(ENST)"
        elif target.startswith(("NM_", "NR_", "XM_", "XR_")):
            for probe in (canonical_transcript_id, target):
                if not probe:
                    continue
                try:
                    xrefs = ensembl_client.xrefs_name(probe)
                except Exception:
                    xrefs = []
                for x in xrefs:
                    if str(x.get("type") or "").lower() == "transcript":
                        xid = _norm_id(x.get("id") or x.get("primary_id"))
                        for t in transcripts:
                            if _norm_id(t.get("id")) == xid:
                                return t, f"mapped_refseq_to_ensembl({probe})"
    for t in transcripts:
        if any(k in t for k in ("MANE_Select", "mane_select")):
            return t, "first_MANE_Select_from_gene_lookup"
    for t in transcripts:
        if any(k in t for k in ("MANE_Plus_Clinical", "mane_plus_clinical")):
            return t, "first_MANE_Plus_Clinical_from_gene_lookup"
    for t in transcripts:
        if bool(t.get("is_canonical")):
            return t, "first_ensembl_canonical_from_gene_lookup"
    if transcripts:
        return transcripts[0], "fallback_first_transcript_from_gene_lookup"
    return None, "no_transcript_found"


def _find_unique_subsequence(haystack: str, needle: str) -> Tuple[Optional[int], Optional[int], str]:
    h = normalize_nt(haystack)
    n = normalize_nt(needle)
    if not h or not n:
        return None, None, "empty_sequence"
    idx = h.find(n)
    if idx < 0:
        return None, None, "cds_not_found_in_cdna"
    second = h.find(n, idx + 1)
    if second >= 0:
        return None, None, "cds_occurs_multiple_times_in_cdna"
    return idx + 1, idx + len(n), "found_unique"


_XREF_DB_UNIPROT = {"Uniprot/SWISSPROT", "UniProtKB/Swiss-Prot", "SWISSPROT", "Uniprot_gn", "UniProtKB"}
_XREF_DB_REFSEQ_RNA = {"RefSeq_mRNA", "RefSeq RNA", "RefSeq_rna"}
_XREF_DB_REFSEQ_PEPTIDE = {"RefSeq_peptide", "RefSeq Protein", "RefSeq_pep"}


def _extract_xref_primary_id(xref: Dict[str, Any]) -> Optional[str]:
    return _pick_first([
        xref.get("primary_id"),
        xref.get("display_id"),
        xref.get("dbname_id"),
        xref.get("id"),
    ])


def _parse_xrefs(xrefs: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {
        "uniprot_accession": None,
        "refseq_transcript_id": None,
        "refseq_protein_id": None,
    }
    for x in xrefs:
        dbname = str(x.get("dbname") or x.get("db_display_name") or x.get("db") or "")
        primary = _extract_xref_primary_id(x)
        if not primary:
            continue
        if dbname in _XREF_DB_UNIPROT and not out["uniprot_accession"]:
            out["uniprot_accession"] = primary.split("-")[0]
        if dbname in _XREF_DB_REFSEQ_RNA and not out["refseq_transcript_id"]:
            out["refseq_transcript_id"] = primary
        if dbname in _XREF_DB_REFSEQ_PEPTIDE and not out["refseq_protein_id"]:
            out["refseq_protein_id"] = primary
    return out


def resolve_transcript_reference_bundle(gene_row: Dict[str, Any]) -> TranscriptReferenceBundle:
    gene_symbol = str(gene_row.get("gene_symbol") or gene_row.get("gene_id") or "")
    canonical_transcript_id = gene_row.get("canonical_transcript_id")
    canonical_source = gene_row.get("canonical_source")

    if not gene_symbol:
        raise ValueError("gene_symbol missing from gene row")

    ensembl = EnsemblClient()
    gene_lookup = ensembl.lookup_symbol(gene_symbol)
    transcripts = _transcripts_from_lookup(gene_lookup)
    transcript_obj, selection_reason = _match_transcript_candidate(transcripts, canonical_transcript_id, ensembl)
    if not transcript_obj:
        raise ValueError(f"Unable to resolve transcript for gene_symbol={gene_symbol}")

    ensembl_gene_id = _pick_first([gene_lookup.get("id"), gene_lookup.get("gene_id")])
    ensembl_transcript_id = _norm_id(_pick_first([transcript_obj.get("id"), transcript_obj.get("transcript_id")]))
    if not ensembl_transcript_id:
        raise ValueError(f"Resolved transcript for {gene_symbol} has no Ensembl transcript id")

    translation_obj = _extract_translation_obj(transcript_obj)
    ensembl_protein_id = _norm_id(_pick_first([translation_obj.get("id"), transcript_obj.get("translation_id")]))

    cdna_seq = ensembl.sequence_id(ensembl_transcript_id, "cdna")
    cds_seq = ensembl.sequence_id(ensembl_transcript_id, "cds")
    protein_seq = ""
    if ensembl_protein_id:
        try:
            protein_seq = ensembl.sequence_id(ensembl_protein_id, "protein")
        except Exception:
            protein_seq = ""
    if not protein_seq:
        protein_seq = ensembl.sequence_id(ensembl_transcript_id, "protein")

    transcript_xrefs = ensembl.xrefs_id(ensembl_transcript_id)
    protein_xrefs = ensembl.xrefs_id(ensembl_protein_id) if ensembl_protein_id else []
    xref_meta = _parse_xrefs(transcript_xrefs + protein_xrefs)

    cds_start_1 = None
    cds_end_1 = None
    for key in ("start", "cdna_start", "transcript_start"):
        val = translation_obj.get(key)
        if isinstance(val, int):
            cds_start_1 = int(val)
            break
    for key in ("end", "cdna_end", "transcript_end"):
        val = translation_obj.get(key)
        if isinstance(val, int):
            cds_end_1 = int(val)
            break
    if cds_start_1 is None or cds_end_1 is None:
        cds_start_1, cds_end_1, _ = _find_unique_subsequence(cdna_seq, cds_seq)

    provenance = {
        "ensembl_lookup_gene_id": ensembl_gene_id,
        "ensembl_transcript_id": ensembl_transcript_id,
        "ensembl_translation_id": ensembl_protein_id,
        "transcript_selection_reason": selection_reason,
        "transcript_kind": _transcript_kind_from_obj(transcript_obj, canonical_source),
        "canonical_transcript_id_from_db": canonical_transcript_id,
        "canonical_source_from_db": canonical_source,
        "transcript_xref_count": len(transcript_xrefs),
        "protein_xref_count": len(protein_xrefs),
    }

    return TranscriptReferenceBundle(
        gene_symbol=gene_symbol,
        transcript_selection_reason=selection_reason,
        transcript_kind=_transcript_kind_from_obj(transcript_obj, canonical_source),
        canonical_source=canonical_source,
        ensembl_gene_id=ensembl_gene_id,
        ensembl_transcript_id=ensembl_transcript_id,
        ensembl_protein_id=ensembl_protein_id,
        refseq_transcript_id=xref_meta.get("refseq_transcript_id"),
        refseq_protein_id=xref_meta.get("refseq_protein_id"),
        uniprot_accession=xref_meta.get("uniprot_accession"),
        cdna_seq=normalize_nt(cdna_seq),
        cds_seq=normalize_nt(cds_seq),
        protein_seq=normalize_aa(protein_seq),
        cds_start_cdna_1=cds_start_1,
        cds_end_cdna_1=cds_end_1,
        provenance=provenance,
    )


def build_sequence_validation_report(bundle: TranscriptReferenceBundle) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "transcript_selection_reason": bundle.transcript_selection_reason,
        "transcript_kind": bundle.transcript_kind,
        "cross_source": {},
        "translation": {},
    }

    tr = translate_cds(bundle.cds_seq)
    report["translation"] = {
        "ok": tr.ok,
        "reason": tr.reason,
        "protein_length": tr.protein_length,
        "start_codon_ok": tr.start_codon_ok,
        "terminal_stop_present": tr.terminal_stop_present,
        "internal_stop_positions_aa": tr.internal_stop_positions_aa,
        "multiple_of_three": tr.multiple_of_three,
        "has_ambiguous_bases": tr.has_ambiguous_bases,
        "cds_start_cdna_1": bundle.cds_start_cdna_1,
        "cds_end_cdna_1": bundle.cds_end_cdna_1,
    }
    report["cross_source"]["ensembl_translation_vs_cds_translation"] = compare_sequences(bundle.protein_seq, tr.protein_seq)

    ncbi = NCBIClient()
    if bundle.refseq_protein_id:
        try:
            refseq_protein_seq = ncbi.efetch_fasta(db="protein", accession=bundle.refseq_protein_id)
            report["cross_source"]["refseq_protein_id"] = bundle.refseq_protein_id
            report["cross_source"]["refseq_protein_vs_cds_translation"] = compare_sequences(refseq_protein_seq, tr.protein_seq)
        except Exception as e:
            report["cross_source"]["refseq_protein_fetch_error"] = str(e)

    if bundle.refseq_transcript_id:
        try:
            refseq_rna_seq = ncbi.efetch_fasta(db="nuccore", accession=bundle.refseq_transcript_id)
            report["cross_source"]["refseq_transcript_id"] = bundle.refseq_transcript_id
            report["cross_source"]["refseq_cdna_vs_ensembl_cdna"] = {
                "match": normalize_nt(refseq_rna_seq) == bundle.cdna_seq,
                "expected_length": len(bundle.cdna_seq),
                "observed_length": len(normalize_nt(refseq_rna_seq)),
            }
        except Exception as e:
            report["cross_source"]["refseq_rna_fetch_error"] = str(e)

    if bundle.uniprot_accession:
        try:
            uniprot = UniProtClient().entry_json(bundle.uniprot_accession)
            up_seq = normalize_aa(str((uniprot.get("sequence") or {}).get("value") or ""))
            report["cross_source"]["uniprot_accession"] = bundle.uniprot_accession
            report["cross_source"]["uniprot_reviewed"] = "Swiss-Prot" in str(uniprot.get("entryType") or "")
            report["cross_source"]["uniprot_primaryAccession"] = uniprot.get("primaryAccession")
            report["cross_source"]["uniprot_vs_cds_translation"] = compare_sequences(up_seq, tr.protein_seq)
        except Exception as e:
            report["cross_source"]["uniprot_fetch_error"] = str(e)

    return report


def summarize_validation_status(report: Dict[str, Any]) -> str:
    tr_ok = bool(((report.get("translation") or {}).get("ok")))
    ensembl_match = bool((((report.get("cross_source") or {}).get("ensembl_translation_vs_cds_translation") or {}).get("match")))
    refseq_info = ((report.get("cross_source") or {}).get("refseq_protein_vs_cds_translation") or {})
    uniprot_info = ((report.get("cross_source") or {}).get("uniprot_vs_cds_translation") or {})

    refseq_available = bool(refseq_info)
    refseq_match = bool(refseq_info.get("match")) if refseq_available else False
    uniprot_available = bool(uniprot_info)
    uniprot_match = bool(uniprot_info.get("match")) if uniprot_available else False

    if tr_ok and ensembl_match and refseq_available and refseq_match and uniprot_available and uniprot_match:
        return "pass_strict"
    if tr_ok and ensembl_match and refseq_available and refseq_match and not uniprot_available:
        return "pass_refseq_only"
    if tr_ok and ensembl_match and not refseq_available and not uniprot_available:
        return "pass_transcript_only"
    if tr_ok and ensembl_match and refseq_available and refseq_match and uniprot_available and not uniprot_match:
        return "review_required_uniprot_mismatch"
    return "review_required"


def pdbe_structure_candidates(uniprot_accession: str) -> List[Dict[str, Any]]:
    rows = PDBeClient().best_structures(uniprot_accession)
    out: List[Dict[str, Any]] = []
    for r in rows:
        pdb_id = str(r.get("pdb_id") or r.get("pdbid") or r.get("pdb") or "").lower()
        if not pdb_id:
            continue
        chain_id = str(r.get("chain_id") or r.get("chain") or r.get("struct_asym_id") or "")
        coverage = r.get("coverage")
        if coverage is None:
            # Sometimes only residue coordinates are returned.
            try:
                u_start = int(r.get("unp_start") or r.get("start") or 0)
                u_end = int(r.get("unp_end") or r.get("end") or 0)
                coverage = max(0.0, float(u_end - u_start + 1))
            except Exception:
                coverage = None
        try:
            coverage_f = float(coverage) if coverage is not None else None
        except Exception:
            coverage_f = None
        try:
            resolution = float(r.get("resolution")) if r.get("resolution") is not None else None
        except Exception:
            resolution = None
        try:
            seq_identity = float(r.get("experimental_sequence_identity") or r.get("sequence_identity") or 1.0)
        except Exception:
            seq_identity = None
        out.append(
            {
                "provider": "pdbe_best_structures",
                "source_db": "PDB",
                "source_id": pdb_id,
                "source_chain_id": chain_id,
                "structure_kind": "experimental",
                "method": r.get("experimental_method") or r.get("method"),
                "resolution_angstrom": resolution,
                "mapped_coverage": coverage_f,
                "mapped_start": r.get("unp_start") or r.get("start"),
                "mapped_end": r.get("unp_end") or r.get("end"),
                "sequence_identity": seq_identity,
                "title": r.get("title"),
                "source_payload": r,
            }
        )
    out.sort(key=lambda x: (
        -(x.get("mapped_coverage") or 0.0),
        (x.get("resolution_angstrom") or 999.0),
        x.get("source_id") or "",
    ))
    return out


def alphafold_structure_candidates(uniprot_accession: str) -> List[Dict[str, Any]]:
    rows = AlphaFoldClient().prediction(uniprot_accession)
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "provider": "alphafold_db",
                "source_db": "AlphaFoldDB",
                "source_id": _pick_first([
                    r.get("entryId"),
                    r.get("alphafoldDbId"),
                    r.get("model_id"),
                    f"AF-{uniprot_accession}",
                ]),
                "source_chain_id": "",
                "structure_kind": "predicted",
                "method": "AlphaFoldDB",
                "resolution_angstrom": None,
                "mapped_coverage": None,
                "mapped_start": r.get("uniprotStart") or r.get("uniprot_start") or 1,
                "mapped_end": r.get("uniprotEnd") or r.get("uniprot_end"),
                "sequence_identity": 1.0,
                "title": r.get("entryId") or r.get("model_id") or f"AlphaFold prediction for {uniprot_accession}",
                "cif_url": r.get("cifUrl") or r.get("cif_url"),
                "pdb_url": r.get("pdbUrl") or r.get("pdb_url"),
                "pae_url": r.get("paeDocUrl") or r.get("pae_url") or r.get("paeDocURL"),
                "source_payload": r,
            }
        )
    return out


def download_rcsb_cif(pdb_id: str) -> bytes:
    s = get_settings()
    url = s.RCSB_DOWNLOAD_BASE.rstrip("/") + f"/{pdb_id.upper()}.cif"
    return HttpClient().get_bytes(url)


def download_url_bytes(url: str) -> bytes:
    return HttpClient().get_bytes(url)


def mean_plddt_from_pdb_bytes(data: bytes) -> Optional[float]:
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return None
    vals: List[float] = []
    for line in text.splitlines():
        if not (line.startswith("ATOM  ") or line.startswith("HETATM")):
            continue
        if len(line) < 66:
            continue
        raw = line[60:66].strip()
        if not raw:
            continue
        try:
            vals.append(float(raw))
        except Exception:
            continue
    if not vals:
        return None
    return round(sum(vals) / len(vals), 3)


def choose_default_structure(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None

    experimental = [c for c in candidates if c.get("structure_kind") == "experimental"]
    experimental_good = [
        c for c in experimental
        if (c.get("mapped_coverage") or 0.0) >= 0.70 and ((c.get("resolution_angstrom") or 999.0) <= 4.0)
    ]
    if experimental_good:
        experimental_good.sort(key=lambda x: (
            -(x.get("mapped_coverage") or 0.0),
            (x.get("resolution_angstrom") or 999.0),
        ))
        return experimental_good[0]

    predicted = [c for c in candidates if c.get("structure_kind") == "predicted"]
    if predicted:
        return predicted[0]

    experimental.sort(key=lambda x: (
        -(x.get("mapped_coverage") or 0.0),
        (x.get("resolution_angstrom") or 999.0),
    ))
    return experimental[0] if experimental else candidates[0]


def structure_download_filename(candidate: Dict[str, Any], file_format: str) -> str:
    source_id = str(candidate.get("source_id") or "unknown")
    chain = str(candidate.get("source_chain_id") or "")
    chain_suffix = f"_{chain}" if chain else ""
    return f"{source_id}{chain_suffix}.{file_format.lstrip('.')}"


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)
