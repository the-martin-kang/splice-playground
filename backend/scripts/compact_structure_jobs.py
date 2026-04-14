#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Any, Dict, Iterable

from app.db.repositories.structure_job_repo import get_job, list_jobs, update_job


def _compact_assets(assets: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    out = []
    for a in assets or []:
        if not isinstance(a, dict):
            continue
        out.append({
            "kind": a.get("kind"),
            "bucket": a.get("bucket"),
            "path": a.get("path"),
            "file_format": a.get("file_format"),
            "name": a.get("name"),
            "is_default": bool(a.get("is_default")),
        })
    return out


def compact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    compact = {
        "gene_id": payload.get("gene_id"),
        "disease_id": payload.get("disease_id"),
        "state_id": payload.get("state_id"),
        "user_protein_sha256": payload.get("user_protein_sha256"),
        "user_protein_length": payload.get("user_protein_length"),
        "reused_baseline_structure": bool(payload.get("reused_baseline_structure")),
        "comparison_to_normal": payload.get("comparison_to_normal") or {},
        "translation_sanity": payload.get("translation_sanity") or {},
        "predicted_transcript": payload.get("predicted_transcript") or {},
        "baseline_protein_reference_id": payload.get("baseline_protein_reference_id"),
        "baseline_default_structure_asset_id": payload.get("baseline_default_structure_asset_id"),
        "default_structure_name": payload.get("default_structure_name"),
        "confidence": payload.get("confidence") or {},
        "assets": _compact_assets(payload.get("assets") or []),
        "worker": payload.get("worker") or {},
    }
    if payload.get("structure_comparison") is not None:
        compact["structure_comparison"] = payload.get("structure_comparison")
    return compact


def main() -> None:
    ap = argparse.ArgumentParser(description="Compact oversized structure_job payloads")
    ap.add_argument("--job-id")
    ap.add_argument("--provider")
    ap.add_argument("--status")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    rows = [get_job(args.job_id, include_payload=True)] if args.job_id else list_jobs(status=args.status, provider=args.provider, limit=args.limit, include_payload=False)
    rows = [r for r in rows if r]
    for row in rows:
        job_id = str(row.get("job_id"))
        detailed = get_job(job_id, include_payload=True)
        if not detailed:
            print({"job_id": job_id, "status": "missing"})
            continue
        payload = detailed.get("result_payload") or {}
        compact = compact_payload(payload)
        updated = update_job(job_id, result_payload=compact, include_payload=False)
        print({"job_id": updated.get("job_id"), "status": updated.get("status"), "compacted": True})


if __name__ == "__main__":
    main()
