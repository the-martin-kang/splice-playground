# app/db/repositories/disease_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.db.supabase_client import DBNotFoundError, execute, ensure_list, ensure_one, get_supabase_client


class DiseaseRepo:
    TABLE = "disease"

    DEFAULT_SELECT = "disease_id,disease_name,description,image_path,gene_id,created_at,updated_at"

    @staticmethod
    def list_diseases(
        *,
        limit: int = 100,
        offset: int = 0,
        select: str = DEFAULT_SELECT,
        order_by: str = "disease_name",
        ascending: bool = True,
        include_count: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Returns (items, count)
        - count is exact if include_count=True and postgrest supports it, else len(items)
        """
        sb = get_supabase_client()
        q = sb.table(DiseaseRepo.TABLE)

        # count="exact" 지원 여부가 버전별로 다를 수 있어 방어적으로 처리
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

    @staticmethod
    def get_disease_by_id(
        disease_id: str,
        *,
        select: str = DEFAULT_SELECT,
    ) -> Dict[str, Any]:
        sb = get_supabase_client()
        q = (
            sb.table(DiseaseRepo.TABLE)
            .select(select)
            .eq("disease_id", disease_id)
            .limit(1)
        )
        res = execute(q)
        rows = ensure_list(res.data)
        return ensure_one(rows, not_found_message=f"disease not found: {disease_id}")

    @staticmethod
    def require_image_path(disease_row: Dict[str, Any]) -> str:
        """
        Helper: disease_row에서 image_path를 강제.
        (B 방식 signed URL 생성은 services/storage_service.py에서 수행)
        """
        image_path = disease_row.get("image_path")
        if not image_path:
            raise DBNotFoundError(f"image_path is empty for disease_id={disease_row.get('disease_id')}")
        return str(image_path)
