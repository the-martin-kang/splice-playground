# app/db/repositories/snv_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.supabase_client import DBNotFoundError, execute, ensure_list, ensure_one, get_supabase_client


class SNVRepo:
    TABLE = "splice_altering_snv"

    DEFAULT_SELECT = (
        "snv_id,disease_id,gene_id,pos_gene0,ref,alt,is_representative,"
        "chromosome,pos_hg38_1,note,created_at,updated_at"
    )

    @staticmethod
    def list_snvs_by_disease(
        disease_id: str,
        *,
        select: str = DEFAULT_SELECT,
        order_by: str = "pos_gene0",
        ascending: bool = True,
    ) -> List[Dict[str, Any]]:
        sb = get_supabase_client()
        q = (
            sb.table(SNVRepo.TABLE)
            .select(select)
            .eq("disease_id", disease_id)
            .order(order_by, desc=not ascending)
        )
        res = execute(q)
        return ensure_list(res.data)

    @staticmethod
    def get_representative_snv_by_disease(
        disease_id: str,
        *,
        select: str = DEFAULT_SELECT,
        allow_none: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Return representative SNV (is_representative=true).
        - If allow_none=False: raise if missing
        - If allow_none=True: return None if missing
        """
        sb = get_supabase_client()
        q = (
            sb.table(SNVRepo.TABLE)
            .select(select)
            .eq("disease_id", disease_id)
            .eq("is_representative", True)
            .limit(1)
        )
        res = execute(q)
        rows = ensure_list(res.data)
        if not rows:
            if allow_none:
                return None
            raise DBNotFoundError(f"representative SNV not found for disease_id={disease_id}")
        return rows[0]
