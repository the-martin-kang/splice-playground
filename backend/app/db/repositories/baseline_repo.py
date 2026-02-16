# app/db/baseline_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.db.supabase_client import execute, ensure_list, ensure_one, get_supabase_client


class BaselineRepo:
    """
    baseline_result table access
    - primary key: (gene_id, step, model_version)
    """

    TABLE = "baseline_result"

    DEFAULT_SELECT = "gene_id,step,model_version,result_payload,created_at,updated_at"

    @staticmethod
    def get_baseline_result(
        *,
        gene_id: str,
        step: str,
        model_version: str,
        select: str = DEFAULT_SELECT,
    ) -> Dict[str, Any]:
        sb = get_supabase_client()
        q = (
            sb.table(BaselineRepo.TABLE)
            .select(select)
            .eq("gene_id", gene_id)
            .eq("step", step)
            .eq("model_version", model_version)
            .limit(1)
        )
        res = execute(q)
        rows = ensure_list(res.data)
        return ensure_one(
            rows,
            not_found_message=f"baseline_result not found: gene_id={gene_id}, step={step}, model_version={model_version}",
        )

    @staticmethod
    def list_baseline_results_by_gene(
        *,
        gene_id: str,
        step: Optional[str] = None,
        select: str = DEFAULT_SELECT,
        order_by: str = "created_at",
        ascending: bool = False,
    ) -> List[Dict[str, Any]]:
        sb = get_supabase_client()
        q = sb.table(BaselineRepo.TABLE).select(select).eq("gene_id", gene_id)

        if step is not None:
            q = q.eq("step", step)

        q = q.order(order_by, desc=not ascending)
        res = execute(q)
        return ensure_list(res.data)
