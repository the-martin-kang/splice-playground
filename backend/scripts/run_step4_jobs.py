#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.db.repositories.structure_job_repo import get_job, list_jobs, update_job
from app.services.storage_service import download_storage_bytes, upload_bytes_to_storage


_STRUCTURE_SUFFIXES = {".pdb", ".cif", ".mmcif"}
_JSON_SUFFIXES = {".json"}


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)



def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None



def _guess_asset_kind(path: Path) -> str:
    name = path.name.lower()
    if path.suffix.lower() in _STRUCTURE_SUFFIXES:
        return "structure"
    if path.suffix.lower() in _JSON_SUFFIXES and "pae" in name:
        return "pae"
    if path.suffix.lower() in _JSON_SUFFIXES:
        return "scores"
    return "other"



def _collect_output_files(out_dir: Path) -> List[Path]:
    keep: List[Path] = []
    for p in out_dir.rglob("*"):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf in _STRUCTURE_SUFFIXES or suf in _JSON_SUFFIXES:
            keep.append(p)
    keep.sort()
    return keep



def _extract_confidence(files: Iterable[Path]) -> Dict[str, Any]:
    confidence: Dict[str, Any] = {}
    for path in files:
        if path.name.lower() == "ranking_debug.json":
            payload = _load_json(path) or {}
            confidence["ranking_debug"] = payload
        elif path.suffix.lower() == ".json" and "scores" in path.name.lower():
            payload = _load_json(path) or {}
            confidence.setdefault("score_files", []).append({"name": path.name, "payload": payload})
        elif path.suffix.lower() == ".json" and "pae" in path.name.lower():
            payload = _load_json(path)
            if isinstance(payload, dict):
                confidence.setdefault("pae_files", []).append({"name": path.name, "keys": sorted(payload.keys())[:20]})
    if isinstance(confidence.get("ranking_debug"), dict):
        rd = confidence["ranking_debug"]
        if isinstance(rd.get("plddts"), dict):
            values = [float(v) for v in rd["plddts"].values() if v is not None]
            if values:
                confidence["best_plddt"] = max(values)
        order = rd.get("order")
        if order is not None:
            confidence["order"] = order
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



def _upload_outputs(*, job_row: Dict[str, Any], out_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[Path]]:
    settings = get_settings()
    bucket = settings.STEP4_STRUCTURE_BUCKET
    payload = job_row.get("result_payload") or {}
    gene_id = str(payload.get("gene_id") or "unknown")
    state_id = str(payload.get("state_id") or job_row.get("state_id") or "unknown")
    job_id = str(job_row.get("job_id") or "unknown")
    storage_prefix = f"user/{gene_id}/{state_id}/{job_id}"

    files = _collect_output_files(out_dir)
    assets: List[Dict[str, Any]] = []
    first_structure: Optional[Path] = None
    for f in files:
        rel = f.relative_to(out_dir)
        object_path = f"{storage_prefix}/{rel.as_posix()}"
        kind = _guess_asset_kind(f)
        if kind == "structure" and first_structure is None:
            first_structure = f
        content_type = "application/octet-stream"
        if f.suffix.lower() == ".json":
            content_type = "application/json"
        upload_bytes_to_storage(bucket=bucket, object_path=object_path, data=f.read_bytes(), content_type=content_type, upsert=True)
        assets.append(
            {
                "kind": kind,
                "bucket": bucket,
                "path": object_path,
                "file_format": f.suffix.lower().lstrip("."),
                "name": f.name,
            }
        )
    confidence = _extract_confidence(files)
    return assets, confidence, first_structure



def _run_colabfold(job_row: Dict[str, Any]) -> Dict[str, Any]:
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

    assets, confidence, first_structure = _upload_outputs(job_row=job_row, out_dir=out_dir)
    result_payload = dict(payload)
    result_payload["assets"] = assets
    result_payload["confidence"] = confidence
    result_payload["stdout_excerpt"] = stdout[-4000:]
    result_payload["stderr_excerpt"] = stderr[-4000:] if stderr else ""

    if settings.STEP4_ALIGNMENT_BIN and first_structure is not None:
        with tempfile.TemporaryDirectory(prefix="step4_align_") as td:
            tmpdir = Path(td)
            baseline_file = _prepare_baseline_alignment_file(payload, tmpdir)
            if baseline_file is not None:
                result_payload["structure_comparison"] = _run_alignment(
                    alignment_bin=settings.STEP4_ALIGNMENT_BIN,
                    pred_path=first_structure,
                    baseline_path=baseline_file,
                )
    return result_payload



def _process_job(job_row: Dict[str, Any]) -> Dict[str, Any]:
    provider = str(job_row.get("provider") or "")
    if provider != "colabfold":
        raise RuntimeError(f"Unsupported provider for worker: {provider}")

    update_job(str(job_row["job_id"]), status="running", error_message=None)
    result_payload = _run_colabfold(job_row)
    return update_job(str(job_row["job_id"]), status="succeeded", result_payload=result_payload, error_message=None)



def main() -> None:
    ap = argparse.ArgumentParser(description="Run queued STEP4 structure jobs (ColabFold worker)")
    ap.add_argument("--once", action="store_true", help="Process a single batch and exit")
    ap.add_argument("--provider", default="colabfold")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--job-id", help="Run a specific job id instead of polling queued jobs")
    args = ap.parse_args()

    processed_any = False
    try:
        while True:
            if args.job_id:
                row = get_job(args.job_id)
                if not row:
                    raise SystemExit(f"Job not found: {args.job_id}")
                rows = [row]
            else:
                rows = list_jobs(status="queued", provider=args.provider, limit=args.limit)

            if not rows:
                if args.once:
                    break
                import time
                time.sleep(5)
                continue

            for row in rows:
                job_id = str(row.get("job_id"))
                print(f"[STEP4 worker] Processing job {job_id} provider={row.get('provider')} state_id={row.get('state_id')}")
                try:
                    updated = _process_job(row)
                    print(_json({
                        "job_id": updated.get("job_id"),
                        "status": updated.get("status"),
                        "state_id": updated.get("state_id"),
                    }))
                    processed_any = True
                except Exception as e:
                    update_job(job_id, status="failed", error_message=str(e))
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
