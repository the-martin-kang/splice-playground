# app/db/repositories/gene_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.db.supabase_client import execute, ensure_list, ensure_one, get_supabase_client


class GeneRepo:
    TABLE = "gene"

    DEFAULT_SELECT = (
        "gene_id,gene_symbol,chromosome,strand,length,exon_count,"
        "canonical_transcript_id,canonical_source,source_version,created_at,updated_at"
    )

    @staticmethod
    def get_gene_by_id(
        gene_id: str,
        *,
        select: str = DEFAULT_SELECT,
    ) -> Dict[str, Any]:
        sb = get_supabase_client()
        q = sb.table(GeneRepo.TABLE).select(select).eq("gene_id", gene_id).limit(1)
        res = execute(q)
        rows = ensure_list(res.data)
        return ensure_one(rows, not_found_message=f"gene not found: {gene_id}")

    @staticmethod
    def list_genes(
        *,
        limit: int = 200,
        offset: int = 0,
        select: str = DEFAULT_SELECT,
        order_by: str = "gene_id",
        ascending: bool = True,
        include_count: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        sb = get_supabase_client()
        q = sb.table(GeneRepo.TABLE)
        if include_count:
            try:
                q = q.select(select, count="exact")
            except TypeError:
                q = q.select(select)
        else:
            q = q.select(select)

        q = q.order(order_by, desc=not ascending).range(offset, offset + max(limit, 1) - 1)
        res = execute(q)
        items = ensure_list(res.data)
        count = res.count if (include_count and res.count is not None) else len(items)
        return items, count
