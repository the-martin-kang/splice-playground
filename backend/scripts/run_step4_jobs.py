#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.db.repositories.structure_job_repo import claim_job_if_queued, get_job, list_jobs, update_job
from app.services.storage_service import download_storage_bytes, upload_bytes_to_storage


_STRUCTURE_SUFFIXES = {".pdb", ".cif", ".mmcif"}
_JSON_SUFFIXES = {".json"}
_TEXT_SUFFIXES = {".txt", ".log", ".fasta", ".fa", ".a3m", ".csv"}


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)



def _worker_token() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"



def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None



def _guess_asset_kind(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in _STRUCTURE_SUFFIXES:
        return "structure"
    if suffix in _JSON_SUFFIXES and "pae" in name:
        return "pae"
    if suffix in _JSON_SUFFIXES:
        return "scores"
    if suffix in _TEXT_SUFFIXES and name.startswith("query"):
        return "input"
    if suffix in _TEXT_SUFFIXES:
        return "logs"
    return "other"



def _collect_output_files(out_dir: Path) -> List[Path]:
    keep: List[Path] = []
    for p in out_dir.rglob("*"):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf in _STRUCTURE_SUFFIXES or suf in _JSON_SUFFIXES or suf in _TEXT_SUFFIXES:
            keep.append(p)
    keep.sort()
    return keep



def _extract_confidence(files: Iterable[Path]) -> Dict[str, Any]:
    confidence: Dict[str, Any] = {}
    ranking_debug: Optional[Dict[str, Any]] = None
    for path in files:
        lowered = path.name.lower()
        if lowered == "ranking_debug.json":
            payload = _load_json(path) or {}
            ranking_debug = payload
            confidence["ranking_debug"] = payload
        elif path.suffix.lower() == ".json" and "scores" in lowered:
            payload = _load_json(path) or {}
            confidence.setdefault("score_files", []).append({"name": path.name, "payload": payload})
        elif path.suffix.lower() == ".json" and "pae" in lowered:
            payload = _load_json(path)
            if isinstance(payload, dict):
                confidence.setdefault("pae_files", []).append({"name": path.name, "keys": sorted(payload.keys())[:20]})
    if isinstance(ranking_debug, dict):
        if isinstance(ranking_debug.get("plddts"), dict):
            values = [float(v) for v in ranking_debug["plddts"].values() if v is not None]
            if values:
                confidence["best_plddt"] = max(values)
        if ranking_debug.get("order") is not None:
            confidence["order"] = ranking_debug.get("order")
    return confidence


_TM_RE = re.compile(r"TM-score\s*=\s*([0-9.]+)")
_RMSD_RE = re.compile(r"RMSD\s*=\s*([0-9.]+)")
_ALEN_RE = re.compile(r"Aligned length\s*=\s*([0-9]+)")



def _run_alignment(*, alignment_bin: str, pred_path: Path, baseline_path: Path) -> Optional[Dict[str, Any]]:
    try:
        proc = subprocess.run(
            [alignment_bin, str(pred_path), str(baseline_path)],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except Exception as e:
        return {"method": Path(alignment_bin).name, "raw_text_excerpt": f"alignment_failed: {e}"}

    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    tm_scores = [float(x) for x in _TM_RE.findall(text)]
    rmsd_match = _RMSD_RE.search(text)
    alen_match = _ALEN_RE.search(text)
    return {
        "method": Path(alignment_bin).name,
        "tm_score_1": tm_scores[0] if len(tm_scores) >= 1 else None,
        "tm_score_2": tm_scores[1] if len(tm_scores) >= 2 else None,
        "rmsd": float(rmsd_match.group(1)) if rmsd_match else None,
        "aligned_length": int(alen_match.group(1)) if alen_match else None,
        "raw_text_excerpt": text[:2000],
    }



def _prepare_baseline_alignment_file(payload: Dict[str, Any], tmpdir: Path) -> Optional[Path]:
    assets = payload.get("baseline_structure_assets") or []
    if not isinstance(assets, list) or not assets:
        return None
    default = next((a for a in assets if isinstance(a, dict) and a.get("is_default")), None)
    chosen = default or next((a for a in assets if isinstance(a, dict)), None)
    if not chosen:
        return None
    bucket = str(chosen.get("bucket") or "")
    path = str(chosen.get("path") or "")
    if not bucket or not path:
        return None
    ext = Path(path).suffix or ".cif"
    data = download_storage_bytes(bucket, path)
    out = tmpdir / f"baseline{ext}"
    out.write_bytes(data)
    return out



def _structure_score(path: Path, *, ranking_order: List[str]) -> Tuple[int, int, str]:
    name = path.name.lower()
    # Prefer CIF/mmCIF for Mol* first, then PDB.
    ext_rank = 0 if name.endswith(".cif") or name.endswith(".mmcif") else 1
    if "rank_001" in name:
        return (0, ext_rank, name)
    for idx, token in enumerate(ranking_order):
        tok = str(token).lower()
        if tok and tok in name:
            return (1 + idx, ext_rank, name)
    return (999, ext_rank, name)



def _pick_default_structure_file(files: Iterable[Path]) -> Optional[Path]:
    files = list(files)
    structure_files = [p for p in files if p.suffix.lower() in _STRUCTURE_SUFFIXES]
    if not structure_files:
        return None
    ranking_order: List[str] = []
    ranking_debug = next((p for p in files if p.name.lower() == "ranking_debug.json"), None)
    if ranking_debug is not None:
        payload = _load_json(ranking_debug) or {}
        order = payload.get("order")
        if isinstance(order, list):
            ranking_order = [str(x) for x in order]
    scored = sorted(structure_files, key=lambda p: _structure_score(p, ranking_order=ranking_order))
    return scored[0]



def _should_upload_output(path: Path, *, default_structure: Optional[Path], artifact_policy: str) -> bool:
    policy = (artifact_policy or "minimal").strip().lower()
    if policy == "full":
        return True

    name = path.name.lower()
    if default_structure is not None and path.resolve() == default_structure.resolve():
        return True
    if name == "ranking_debug.json":
        return True
    if name == "config.json":
        return True
    if "predicted_aligned_error" in name or "pae" in name:
        return True
    if name.endswith('.done.txt'):
        return True
    return False


def _compact_result_payload(payload: Dict[str, Any], *, assets: List[Dict[str, Any]], confidence: Dict[str, Any], worker_token: str, command: List[str], default_structure: Path) -> Dict[str, Any]:
    compact: Dict[str, Any] = {
        "gene_id": payload.get("gene_id"),
        "disease_id": payload.get("disease_id"),
        "state_id": payload.get("state_id"),
        "user_protein_sha256": payload.get("user_protein_sha256"),
        "user_protein_length": payload.get("user_protein_length"),
        "reused_baseline_structure": False,
        "comparison_to_normal": payload.get("comparison_to_normal") or {},
        "translation_sanity": payload.get("translation_sanity") or {},
        "predicted_transcript": payload.get("predicted_transcript") or {},
        "baseline_protein_reference_id": payload.get("baseline_protein_reference_id"),
        "baseline_default_structure_asset_id": payload.get("baseline_default_structure_asset_id"),
        "assets": assets,
        "confidence": confidence,
        "default_structure_name": default_structure.name,
        "worker": {
            "token": worker_token,
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "command": command,
        },
    }
    if payload.get("structure_comparison") is not None:
        compact["structure_comparison"] = payload.get("structure_comparison")
    return compact


def _upload_outputs(*, job_row: Dict[str, Any], workdir: Path, out_dir: Path, stdout_text: str, stderr_text: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[Path]]:
    settings = get_settings()
    bucket = settings.STEP4_STRUCTURE_BUCKET
    payload = job_row.get("result_payload") or {}
    gene_id = str(payload.get("gene_id") or "unknown")
    state_id = str(payload.get("state_id") or job_row.get("state_id") or "unknown")
    job_id = str(job_row.get("job_id") or "unknown")
    storage_prefix = f"user/{gene_id}/{state_id}/{job_id}"

    # Persist input / logs for reproducibility.
    input_fasta = workdir / "query.fasta"
    if input_fasta.exists():
        upload_bytes_to_storage(
            bucket=bucket,
            object_path=f"{storage_prefix}/inputs/{input_fasta.name}",
            data=input_fasta.read_bytes(),
            content_type="text/plain",
            upsert=True,
        )
    upload_bytes_to_storage(
        bucket=bucket,
        object_path=f"{storage_prefix}/logs/stdout.log",
        data=stdout_text.encode("utf-8", errors="replace"),
        content_type="text/plain",
        upsert=True,
    )
    upload_bytes_to_storage(
        bucket=bucket,
        object_path=f"{storage_prefix}/logs/stderr.log",
        data=stderr_text.encode("utf-8", errors="replace"),
        content_type="text/plain",
        upsert=True,
    )

    files = _collect_output_files(out_dir)
    default_structure = _pick_default_structure_file(files)
    artifact_policy = str(get_settings().STEP4_ARTIFACT_POLICY or "minimal")
    files = [f for f in files if _should_upload_output(f, default_structure=default_structure, artifact_policy=artifact_policy)]
    assets: List[Dict[str, Any]] = [
        {
            "kind": "input",
            "bucket": bucket,
            "path": f"{storage_prefix}/inputs/query.fasta",
            "file_format": "fasta",
            "name": "query.fasta",
            "is_default": False,
        },
        {
            "kind": "logs",
            "bucket": bucket,
            "path": f"{storage_prefix}/logs/stdout.log",
            "file_format": "log",
            "name": "stdout.log",
            "is_default": False,
        },
    ]
    if stderr_text:
        assets.append(
            {
                "kind": "logs",
                "bucket": bucket,
                "path": f"{storage_prefix}/logs/stderr.log",
                "file_format": "log",
                "name": "stderr.log",
                "is_default": False,
            }
        )

    for f in files:
        rel = f.relative_to(out_dir)
        object_path = f"{storage_prefix}/outputs/{rel.as_posix()}"
        kind = _guess_asset_kind(f)
        content_type = "application/octet-stream"
        if f.suffix.lower() == ".json":
            content_type = "application/json"
        elif f.suffix.lower() in {".log", ".txt", ".fasta", ".fa", ".csv", ".a3m"}:
            content_type = "text/plain"
        upload_bytes_to_storage(bucket=bucket, object_path=object_path, data=f.read_bytes(), content_type=content_type, upsert=True)
        assets.append(
            {
                "kind": kind,
                "bucket": bucket,
                "path": object_path,
                "file_format": f.suffix.lower().lstrip("."),
                "name": f.name,
                "is_default": bool(default_structure is not None and f.resolve() == default_structure.resolve()),
            }
        )
    confidence = _extract_confidence(files)
    return assets, confidence, default_structure



def _run_colabfold(job_row: Dict[str, Any], *, worker_token: str) -> Dict[str, Any]:
    settings = get_settings()
    payload = dict(job_row.get("result_payload") or {})
    protein_seq = str(payload.get("user_protein_seq") or "").strip().upper()
    if not protein_seq:
        raise RuntimeError("result_payload.user_protein_seq is missing")

    workdir = Path(settings.STEP4_JOB_WORKDIR).expanduser().resolve() / str(job_row["job_id"])
    out_dir = workdir / "out"
    workdir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    fasta_path = workdir / "query.fasta"
    fasta_path.write_text(f">state_{job_row['state_id']}\n{protein_seq}\n")

    cmd = [settings.COLABFOLD_BATCH_CMD, str(fasta_path), str(out_dir)]
    if settings.COLABFOLD_EXTRA_ARGS:
        cmd.extend(shlex.split(settings.COLABFOLD_EXTRA_ARGS))

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=int(settings.STEP4_JOB_TIMEOUT_SECONDS),
        check=False,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        raise RuntimeError(f"colabfold_batch failed (exit={proc.returncode})\nSTDOUT:\n{stdout[-4000:]}\nSTDERR:\n{stderr[-4000:]}")

    assets, confidence, default_structure = _upload_outputs(
        job_row=job_row,
        workdir=workdir,
        out_dir=out_dir,
        stdout_text=stdout,
        stderr_text=stderr,
    )
    if default_structure is None:
        raise RuntimeError("ColabFold finished but no structure output (.cif/.mmcif/.pdb) was found.")

    structure_comparison = None
    if settings.STEP4_ALIGNMENT_BIN:
        with tempfile.TemporaryDirectory(prefix="step4_align_") as td:
            tmpdir = Path(td)
            baseline_file = _prepare_baseline_alignment_file(payload, tmpdir)
            if baseline_file is not None:
                structure_comparison = _run_alignment(
                    alignment_bin=settings.STEP4_ALIGNMENT_BIN,
                    pred_path=default_structure,
                    baseline_path=baseline_file,
                )

    compact_base = dict(payload)
    if structure_comparison is not None:
        compact_base["structure_comparison"] = structure_comparison
    result_payload = _compact_result_payload(
        compact_base,
        assets=assets,
        confidence=confidence,
        worker_token=worker_token,
        command=cmd,
        default_structure=default_structure,
    )
    return result_payload



def _process_claimed_job(job_row: Dict[str, Any], *, worker_token: str) -> Dict[str, Any]:
    provider = str(job_row.get("provider") or "")
    if provider != "colabfold":
        raise RuntimeError(f"Unsupported provider for worker: {provider}")
    result_payload = _run_colabfold(job_row, worker_token=worker_token)
    return update_job(str(job_row["job_id"]), status="succeeded", result_payload=result_payload, error_message=None, include_payload=False)



def main() -> None:
    ap = argparse.ArgumentParser(description="Run queued STEP4 structure jobs (ColabFold worker)")
    ap.add_argument("--once", action="store_true", help="Process a single batch and exit")
    ap.add_argument("--provider", default="colabfold")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--job-id", help="Run a specific job id instead of polling queued jobs")
    ap.add_argument("--poll-seconds", type=int, default=get_settings().STEP4_JOB_POLL_SECONDS)
    args = ap.parse_args()

    worker_token = _worker_token()
    processed_any = False
    try:
        while True:
            if args.job_id:
                row = get_job(args.job_id)
                if not row:
                    raise SystemExit(f"Job not found: {args.job_id}")
                rows = [row]
            else:
                rows = list_jobs(status="queued", provider=args.provider, limit=args.limit, include_payload=False)

            if not rows:
                if args.once:
                    break
                time.sleep(max(1, args.poll_seconds))
                continue

            for row in rows:
                job_id = str(row.get("job_id"))
                provider = str(row.get("provider") or "")
                claimed: Optional[Dict[str, Any]]
                if str(row.get("status") or "") == "queued":
                    claimed = claim_job_if_queued(job_id, worker_token=worker_token, provider=provider or None)
                    if claimed is None:
                        print(_json({"job_id": job_id, "status": "skipped", "reason": "already claimed by another worker"}))
                        continue
                else:
                    # Explicit --job-id fallback for a row already in running/succeeded state.
                    claimed = row

                print(f"[STEP4 worker] Processing job {job_id} provider={claimed.get('provider')} state_id={claimed.get('state_id')} worker={worker_token}")
                try:
                    updated = _process_claimed_job(claimed, worker_token=worker_token)
                    print(_json({
                        "job_id": updated.get("job_id"),
                        "status": updated.get("status"),
                        "state_id": updated.get("state_id"),
                    }))
                    processed_any = True
                except Exception as e:
                    update_job(job_id, status="failed", error_message=str(e), external_job_id=worker_token, include_payload=False)
                    print(_json({"job_id": job_id, "status": "failed", "error": str(e)}))
                if args.job_id:
                    break

            if args.once or args.job_id:
                break
    finally:
        if not processed_any and (args.once or args.job_id):
            print("[STEP4 worker] No jobs processed.")


if __name__ == "__main__":
    main()
