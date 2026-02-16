# app/db/repositories/window_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.supabase_client import DBNotFoundError, execute, ensure_list, get_supabase_client


class WindowRepo:
    TABLE = "editing_target_window"

    DEFAULT_SELECT = (
        "window_id,disease_id,gene_id,start_gene0,end_gene0,label,chosen_by,note,created_at,updated_at"
    )

    @staticmethod
    def list_windows_by_disease(
        disease_id: str,
        *,
        select: str = DEFAULT_SELECT,
        order_by: str = "created_at",
        ascending: bool = True,
    ) -> List[Dict[str, Any]]:
        sb = get_supabase_client()
        q = (
            sb.table(WindowRepo.TABLE)
            .select(select)
            .eq("disease_id", disease_id)
            .order(order_by, desc=not ascending)
        )
        res = execute(q)
        return ensure_list(res.data)

    @staticmethod
    def get_primary_window_by_disease(
        disease_id: str,
        *,
        select: str = DEFAULT_SELECT,
        allow_none: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        MVP: disease당 window가 1개라고 가정.
        다수면 created_at 오름차순(가장 먼저 생성된) 1개를 primary로 사용.
        """
        sb = get_supabase_client()
        q = (
            sb.table(WindowRepo.TABLE)
            .select(select)
            .eq("disease_id", disease_id)
            .order("created_at", desc=False)
            .limit(1)
        )
        res = execute(q)
        rows = ensure_list(res.data)
        if not rows:
            if allow_none:
                return None
            raise DBNotFoundError(f"editing_target_window not found for disease_id={disease_id}")
        return rows[0]
