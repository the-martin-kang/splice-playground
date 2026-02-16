# app/db/repositories/state_repo.py
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.db.supabase_client import DBNotFoundError, execute, ensure_list, ensure_one, get_supabase_client


class StateRepo:
    TABLE = "user_state"

    DEFAULT_SELECT = "state_id,disease_id,gene_id,parent_state_id,applied_edit,created_at,updated_at"

    @staticmethod
    def create_state(
        *,
        disease_id: str,
        gene_id: str,
        applied_edit: Dict[str, Any],
        parent_state_id: Optional[str] = None,
    ) -> str:
        """
        Create a user_state row and return state_id.

        IMPORTANT:
        - PostgREST insert returning이 환경에 따라 달라질 수 있어서,
          여기서는 state_id를 서버에서 생성해서 안정적으로 반환한다.
        """
        sb = get_supabase_client()
        state_id = str(uuid.uuid4())

        payload: Dict[str, Any] = {
            "state_id": state_id,
            "disease_id": disease_id,
            "gene_id": gene_id,
            "parent_state_id": parent_state_id,
            "applied_edit": applied_edit,
        }

        # insert가 실패하면 execute()에서 예외 발생
        q = sb.table(StateRepo.TABLE).insert(payload)
        execute(q)

        return state_id

    @staticmethod
    def get_state_by_id(
        state_id: str,
        *,
        select: str = DEFAULT_SELECT,
    ) -> Dict[str, Any]:
        sb = get_supabase_client()
        q = sb.table(StateRepo.TABLE).select(select).eq("state_id", state_id).limit(1)
        res = execute(q)
        rows = ensure_list(res.data)
        return ensure_one(rows, not_found_message=f"user_state not found: {state_id}")

    @staticmethod
    def list_states_by_disease(
        disease_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        select: str = DEFAULT_SELECT,
        newest_first: bool = True,
    ) -> List[Dict[str, Any]]:
        sb = get_supabase_client()
        q = (
            sb.table(StateRepo.TABLE)
            .select(select)
            .eq("disease_id", disease_id)
            .order("created_at", desc=newest_first)
            .range(offset, offset + max(limit, 1) - 1)
        )
        res = execute(q)
        return ensure_list(res.data)
