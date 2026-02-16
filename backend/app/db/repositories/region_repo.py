# app/db/repositories/region_repo.py
from __future__ import annotations

from typing import Any, Dict, List

from app.db.supabase_client import execute, ensure_list, ensure_one, get_supabase_client


class RegionRepo:
    TABLE = "region"

    DEFAULT_SELECT_WITH_SEQ = (
        "region_id,gene_id,region_type,region_number,gene_start_idx,gene_end_idx,length,sequence,"
        "cds_start_offset,cds_end_offset,created_at,updated_at"
    )
    DEFAULT_SELECT_NO_SEQ = (
        "region_id,gene_id,region_type,region_number,gene_start_idx,gene_end_idx,length,"
        "cds_start_offset,cds_end_offset,created_at,updated_at"
    )

    @staticmethod
    def list_regions_by_gene(
        gene_id: str,
        *,
        include_sequence: bool = True,
        order_by: str = "gene_start_idx",
        ascending: bool = True,
    ) -> List[Dict[str, Any]]:
        sb = get_supabase_client()
        select = RegionRepo.DEFAULT_SELECT_WITH_SEQ if include_sequence else RegionRepo.DEFAULT_SELECT_NO_SEQ

        q = (
            sb.table(RegionRepo.TABLE)
            .select(select)
            .eq("gene_id", gene_id)
            .order(order_by, desc=not ascending)
        )
        res = execute(q)
        return ensure_list(res.data)

    @staticmethod
    def list_regions_intersecting_window(
        gene_id: str,
        start_gene0: int,
        end_gene0: int,
        *,
        include_sequence: bool = True,
        order_by: str = "gene_start_idx",
        ascending: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Return regions that intersect [start_gene0, end_gene0] (inclusive).
        Condition: region.gene_start_idx <= end AND region.gene_end_idx >= start
        """
        sb = get_supabase_client()
        select = RegionRepo.DEFAULT_SELECT_WITH_SEQ if include_sequence else RegionRepo.DEFAULT_SELECT_NO_SEQ

        q = (
            sb.table(RegionRepo.TABLE)
            .select(select)
            .eq("gene_id", gene_id)
            .lte("gene_start_idx", int(end_gene0))
            .gte("gene_end_idx", int(start_gene0))
            .order(order_by, desc=not ascending)
        )

        res = execute(q)
        return ensure_list(res.data)

    @staticmethod
    def get_region_containing_pos(
        gene_id: str,
        pos_gene0: int,
        *,
        include_sequence: bool = True,
    ) -> Dict[str, Any]:
        """
        Find region where gene_start_idx <= pos <= gene_end_idx.
        """
        sb = get_supabase_client()
        select = RegionRepo.DEFAULT_SELECT_WITH_SEQ if include_sequence else RegionRepo.DEFAULT_SELECT_NO_SEQ

        q = (
            sb.table(RegionRepo.TABLE)
            .select(select)
            .eq("gene_id", gene_id)
            .lte("gene_start_idx", int(pos_gene0))
            .gte("gene_end_idx", int(pos_gene0))
            .order("gene_start_idx", desc=False)
            .limit(1)
        )
        res = execute(q)
        rows = ensure_list(res.data)
        return ensure_one(rows, not_found_message=f"region not found containing pos={pos_gene0} for gene={gene_id}")
