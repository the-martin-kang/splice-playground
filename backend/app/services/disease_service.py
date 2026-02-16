# app/services/disease_service.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.db.repositories.disease_repo import DiseaseRepo
from app.db.repositories.gene_repo import GeneRepo
from app.db.repositories.region_repo import RegionRepo
from app.db.repositories.snv_repo import SNVRepo
from app.db.repositories.window_repo import WindowRepo
from app.schemas.common import Constraints, Coordinate, Highlight, UIHints
from app.schemas.disease import (
    DiseaseListResponse,
    DiseasePublic,
    SpliceAlteringSNV,
    Step2PayloadResponse,
    Step2Target,
    TargetWindow,
)
from app.schemas.gene import Gene
from app.schemas.region import RegionBase, RegionContext
from app.services.storage_service import StorageService


def _pick_5_region_window(center_idx: int, total: int) -> Tuple[int, int]:
    if total <= 0:
        return (0, -1)
    if total <= 5:
        return (0, total - 1)

    start = center_idx - 2
    end = start + 4
    if start < 0:
        start = 0
        end = 4
    if end >= total:
        end = total - 1
        start = end - 4
    return (max(0, start), min(total - 1, end))


def _find_focus_index_by_region_id(regions: List[Dict[str, Any]], focus_region_id: str) -> int:
    for i, r in enumerate(regions):
        if str(r.get("region_id")) == str(focus_region_id):
            return i
    return -1


def _to_snv_model(snv: Dict[str, Any]) -> SpliceAlteringSNV:
    chrom = snv.get("chromosome")
    pos1 = snv.get("pos_hg38_1")
    genomic_position = f"{chrom}:{pos1}" if chrom and pos1 else None

    coord = Coordinate(
        coordinate_system="gene0",
        assembly="GRCh38",
        chromosome=chrom,
        pos_hg38_1=pos1,
        genomic_position=genomic_position,
    )

    return SpliceAlteringSNV(
        snv_id=str(snv.get("snv_id")) if snv.get("snv_id") else None,
        pos_gene0=int(snv["pos_gene0"]),
        ref=str(snv["ref"]),
        alt=str(snv["alt"]),
        coordinate=coord,
        note=snv.get("note"),
        is_representative=snv.get("is_representative"),
    )


class DiseaseService:
    @staticmethod
    def list_diseases(*, limit: int = 100, offset: int = 0) -> DiseaseListResponse:
        rows, count = DiseaseRepo.list_diseases(limit=limit, offset=offset, include_count=False)

        items: List[DiseasePublic] = []
        for d in rows:
            image_url = None
            image_expires_in = None
            if d.get("image_path"):
                signed = StorageService.create_signed_url_for_image_path(str(d["image_path"]))
                image_url = signed.url
                image_expires_in = signed.expires_in

            items.append(
                DiseasePublic(
                    disease_id=str(d["disease_id"]),
                    disease_name=str(d["disease_name"]),
                    description=d.get("description"),
                    gene_id=d.get("gene_id"),
                    image_path=d.get("image_path"),
                    image_url=image_url,
                    image_expires_in=image_expires_in,
                )
            )

        return DiseaseListResponse(items=items, count=int(count))

    @staticmethod
    def get_step2_payload(*, disease_id: str, include_sequence: bool = True) -> Step2PayloadResponse:
        disease_row = DiseaseRepo.get_disease_by_id(disease_id)
        gene_id = str(disease_row["gene_id"])
        gene_row = GeneRepo.get_gene_by_id(gene_id)

        image_url = None
        image_expires_in = None
        if disease_row.get("image_path"):
            signed = StorageService.create_signed_url_for_image_path(str(disease_row["image_path"]))
            image_url = signed.url
            image_expires_in = signed.expires_in

        disease_model = DiseasePublic(
            disease_id=str(disease_row["disease_id"]),
            disease_name=str(disease_row["disease_name"]),
            description=disease_row.get("description"),
            gene_id=gene_id,
            image_path=disease_row.get("image_path"),
            image_url=image_url,
            image_expires_in=image_expires_in,
        )

        gene_model = Gene.model_validate(gene_row)

        snv_row = SNVRepo.get_representative_snv_by_disease(disease_id, allow_none=False)
        snv_model = _to_snv_model(snv_row)
        pos_gene0 = int(snv_row["pos_gene0"])

        # focus region
        focus_region_row = RegionRepo.get_region_containing_pos(gene_id, pos_gene0, include_sequence=False)
        focus_region_model = RegionBase.model_validate(focus_region_row)

        # window (DB 우선, 없으면 runtime fallback)
        window_row = WindowRepo.get_primary_window_by_disease(disease_id, allow_none=True)

        if window_row:
            start_gene0 = int(window_row["start_gene0"])
            end_gene0 = int(window_row["end_gene0"])
            region_rows = RegionRepo.list_regions_intersecting_window(
                gene_id,
                start_gene0,
                end_gene0,
                include_sequence=include_sequence,
            )
            window_model = TargetWindow(
                start_gene0=start_gene0,
                end_gene0=end_gene0,
                label=window_row.get("label"),
                chosen_by=window_row.get("chosen_by"),
                note=window_row.get("note"),
            )
        else:
            all_regions = RegionRepo.list_regions_by_gene(gene_id, include_sequence=include_sequence)
            if not all_regions:
                raise ValueError(f"No regions found for gene_id={gene_id}")

            focus_idx_all = _find_focus_index_by_region_id(all_regions, str(focus_region_row["region_id"]))
            if focus_idx_all < 0:
                focus_idx_all = 0
                for i, r in enumerate(all_regions):
                    if int(r["gene_start_idx"]) <= pos_gene0 <= int(r["gene_end_idx"]):
                        focus_idx_all = i
                        break

            ws, we = _pick_5_region_window(focus_idx_all, len(all_regions))
            region_rows = all_regions[ws : we + 1]

            start_gene0 = int(region_rows[0]["gene_start_idx"])
            end_gene0 = int(region_rows[-1]["gene_end_idx"])

            window_model = TargetWindow(
                start_gene0=start_gene0,
                end_gene0=end_gene0,
                label="default_context_5_regions",
                chosen_by="runtime_fallback:+/-2_regions",
                note="generated at runtime because no editing_target_window row exists",
            )

        focus_idx_ctx = _find_focus_index_by_region_id(region_rows, str(focus_region_row["region_id"]))
        if focus_idx_ctx < 0:
            focus_idx_ctx = 0
            for i, r in enumerate(region_rows):
                if int(r["gene_start_idx"]) <= pos_gene0 <= int(r["gene_end_idx"]):
                    focus_idx_ctx = i
                    break

        context_models: List[RegionContext] = []
        for i, rr in enumerate(region_rows):
            ctx_dict = dict(rr)
            ctx_dict["rel"] = i - focus_idx_ctx
            context_models.append(RegionContext.model_validate(ctx_dict))

        target = Step2Target(
            window=window_model,
            focus_region=focus_region_model,
            context_regions=context_models,
            constraints=Constraints(),
        )

        ui_hints = UIHints(
            highlight=Highlight(type="snv", pos_gene0=pos_gene0),
            default_view="sequence",
        )

        return Step2PayloadResponse(
            disease=disease_model,
            gene=gene_model,
            splice_altering_snv=snv_model,
            target=target,
            ui_hints=ui_hints,
        )
