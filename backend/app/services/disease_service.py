# app/services/disease_service.py
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple
import re
from app.schemas.region import RegionBase, RegionContext, RegionDetailResponse

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
    TargetWindow, Window4000Response,
)
from app.schemas.gene import Gene
from app.schemas.region import RegionBase, RegionContext
from app.services.storage_service import StorageService

# app/services/disease_service.py (추가 코드)
def _compute_centers(window_size: int) -> tuple[int, int, int, int]:
    """
    Returns (left_center_0, right_center_0, used_center_0, used_center_1)
    Rule:
      - odd  : left==right==used==window_size//2
      - even : left=window_size//2 - 1, right=used=window_size//2
    """
    right = window_size // 2
    left = right if (window_size % 2 == 1) else (right - 1)
    used = right
    return left, right, used, used + 1


_BASE_COMP = str.maketrans({"A": "T", "C": "G", "G": "C", "T": "A", "N": "N"})


def _norm_base(b: str) -> str:
    if b is None:
        return "N"
    s = str(b).strip().upper()
    return s[0] if s else "N"


def _comp_base(b: str) -> str:
    return _norm_base(b).translate(_BASE_COMP)

@lru_cache(maxsize=256)
def _get_gene_sequence_cached(gene_id: str) -> Tuple[str, int]:
    """
    region 테이블의 exon/intron sequence를 gene_start_idx 순서로 concat하여
    gene0 전체 서열을 만든다.

    ✅ 변경점:
    - 첫 region이 0에서 시작하지 않아도 허용 (prefix를 'N'으로 패딩)
      예: MSH2는 first exon start가 gene0=89
    - 중간 gap(누락)은 여전히 에러로 처리 (DB 누락 잡기)
    """
    region_rows = RegionRepo.list_regions_by_gene(gene_id, include_sequence=True)
    if not region_rows:
        raise ValueError(f"No regions found for gene_id={gene_id}")

    region_rows = sorted(region_rows, key=lambda r: int(r["gene_start_idx"]))

    seq_parts: List[str] = []
    prev_end: Optional[int] = None
    total_len = 0

    for r in region_rows:
        seq = r.get("sequence")
        if not isinstance(seq, str) or len(seq) == 0:
            raise ValueError(f"Missing region.sequence for region_id={r.get('region_id')}")

        start = int(r["gene_start_idx"])
        end = int(r["gene_end_idx"])
        length = int(r.get("length") or (end - start + 1))

        if len(seq) != length:
            raise ValueError(
                f"Region length mismatch: region_id={r.get('region_id')} "
                f"len(sequence)={len(seq)} vs length={length} (start={start}, end={end})"
            )

        # ✅ 첫 조각이 0에서 시작하지 않는 경우: prefix를 'N'으로 채움
        if prev_end is None:
            prev_end = -1
            if start > 0:
                seq_parts.append("N" * start)
                total_len += start
                prev_end = start - 1

        # ✅ 이후는 연속성 강제(중간 누락이면 DB가 불완전한 것)
        if start != prev_end + 1:
            raise ValueError(
                f"Non-contiguous regions for gene_id={gene_id}: "
                f"prev_end={prev_end}, next_start={start}"
            )

        seq_parts.append(seq.upper())
        total_len += len(seq)
        prev_end = end

    gene_seq = "".join(seq_parts)
    return gene_seq, total_len


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

    # 2.16 Region type by gene을 위해 추가
    @staticmethod
    def get_region_detail(
        *,
        disease_id: str,
        region_type: str,
        region_number: int,
        include_sequence: bool = True,
    ) -> RegionDetailResponse:
        disease_row = DiseaseRepo.get_disease_by_id(disease_id)
        gene_id = str(disease_row["gene_id"])

        if region_type.lower() not in ("exon", "intron"):
            raise ValueError("region_type must be 'exon' or 'intron'")
        if int(region_number) < 1:
            raise ValueError("region_number must be >= 1")

        region_row = RegionRepo.get_region_by_gene_type_number(
            gene_id=gene_id,
            region_type=region_type,
            region_number=int(region_number),
            include_sequence=include_sequence,
        )
        region_model = RegionBase.model_validate(region_row)

        return RegionDetailResponse(
            disease_id=disease_id,
            gene_id=gene_id,
            region=region_model,
        )

    @staticmethod
    def get_window_4000(
        *,
        disease_id: str,
        window_size: int = 4000,
        strict_ref_check: bool = True,
    ) -> Window4000Response:
        """
        Variable-length window generator.

        Center index rule:
          - odd  : center = window_size//2
          - even : choose the larger of the two centers => center = window_size//2
        """
        if not isinstance(window_size, int) or window_size < 1:
            raise ValueError("window_size must be a positive integer")
        if window_size > 20000:
            # 안전장치: 응답이 너무 커지는 것을 막기 위한 상한(원하면 늘려도 됨)
            raise ValueError("window_size too large (max=20000)")

        disease_row = DiseaseRepo.get_disease_by_id(disease_id)
        gene_id = str(disease_row["gene_id"])

        gene_row = GeneRepo.get_gene_by_id(gene_id, select="gene_id,chromosome,strand,length")
        strand = str(gene_row["strand"])
        chromosome = gene_row.get("chromosome")
        gene_length = int(gene_row["length"])

        snv_row = SNVRepo.get_representative_snv_by_disease(disease_id, allow_none=False)
        pos_gene0 = int(snv_row["pos_gene0"])
        pos_hg38_1 = snv_row.get("pos_hg38_1")
        ref_pos = _norm_base(snv_row["ref"])  # positive strand base
        alt_pos = _norm_base(snv_row["alt"])  # positive strand base

        # gene0 full sequence from regions
        gene_seq, assembled_len = _get_gene_sequence_cached(gene_id)
        # assembled_len이 gene_length보다 짧으면 suffix를 N으로 패딩해서 gene0 인덱스 일치시킴
        if assembled_len < gene_length:
            gene_seq = gene_seq + ("N" * (gene_length - assembled_len))
            assembled_len = gene_length

        # assembled_len이 더 길면 DB 좌표/길이 정의가 꼬인 것이라 에러
        if assembled_len > gene_length or len(gene_seq) != gene_length:
            raise ValueError(
                f"Gene length mismatch for {gene_id}: gene.length={gene_length}, assembled={assembled_len}"
            )

        left_center_0, right_center_0, center_0, center_1 = _compute_centers(window_size)

        # window boundary in gene0 coordinates
        window_start = pos_gene0 - center_0
        window_end_excl = window_start + window_size

        left_pad = max(0, -window_start)
        right_pad = max(0, window_end_excl - gene_length)

        start_in_gene = max(0, window_start)
        end_in_gene = min(gene_length, window_end_excl)

        ref_seq = ("N" * left_pad) + gene_seq[start_in_gene:end_in_gene] + ("N" * right_pad)
        if len(ref_seq) != window_size:
            raise ValueError(f"Internal error: ref_seq length != window_size (len={len(ref_seq)})")

        # expected ref/alt in gene0 orientation
        if strand == "-":
            expected_ref_gene0 = _comp_base(ref_pos)
            alt_gene0 = _comp_base(alt_pos)
        else:
            expected_ref_gene0 = ref_pos
            alt_gene0 = alt_pos

        actual_center = ref_seq[center_0]
        ref_matches = (actual_center == expected_ref_gene0)

        if strict_ref_check and not ref_matches:
            raise ValueError(
                f"Reference base mismatch at center for {disease_id}: "
                f"expected={expected_ref_gene0} (from ref={ref_pos}, strand={strand}) "
                f"but got={actual_center}. Check region sequences / coordinates."
            )

        alt_seq = ref_seq[:center_0] + alt_gene0 + ref_seq[center_0 + 1 :]
        if len(alt_seq) != window_size:
            raise ValueError(f"Internal error: alt_seq length != window_size (len={len(alt_seq)})")

        return Window4000Response(
            disease_id=disease_id,
            gene_id=gene_id,
            chromosome=chromosome,
            strand=strand,
            pos_gene0=pos_gene0,
            pos_hg38_1=pos_hg38_1,
            ref=ref_pos,
            alt=alt_pos,
            window_size=window_size,
            left_center_index_0=left_center_0,
            right_center_index_0=right_center_0,
            center_index_0=center_0,
            center_index_1=center_1,
            window_start_gene0=window_start,
            window_end_gene0_exclusive=window_end_excl,
            gene_length=gene_length,
            left_pad=left_pad,
            right_pad=right_pad,
            expected_ref_at_center=expected_ref_gene0,
            actual_ref_at_center=actual_center,
            ref_matches=ref_matches,
            ref_seq_4000=ref_seq,
            alt_seq_4000=alt_seq,
        )
