// Step 1 data contract: backend disease list/detail responses used by the selector UI.
// 질병 목록 타입 (새 API 구조)
export interface Disease {
  disease_id: string;
  disease_name: string;
  description: string | null;
  gene_id: string;
  image_path: string;
  image_url: string;
  image_expires_in: number;
}

// 질병 상세 타입 (새 API 구조)
export interface DiseaseDetail {
  disease: {
    disease_id: string;
    disease_name: string;
    description: string | null;
    gene_id: string;
    image_path: string;
    image_url: string;
    image_expires_in: number;
  };
  gene: {
    gene_id: string;
    gene_symbol: string;
    chromosome: string;
    strand: string;
    length: number;
    exon_count: number;
    canonical_transcript_id: string;
    canonical_source: string;
    source_version: string;
  };
  splice_altering_snv: {
    snv_id: string;
    pos_gene0: number;
    ref: string;
    alt: string;
    coordinate: {
      coordinate_system: string;
      assembly: string;
      chromosome: string;
      pos_hg38_1: number;
      genomic_position: string;
    };
    note: string;
    is_representative: boolean;
  } | null;
  target: {
    window: {
      start_gene0: number;
      end_gene0: number;
      label: string;
      chosen_by: string;
      note: string;
    };
    focus_region: {
      region_id: string;
      region_type: string;
      region_number: number;
      gene_start_idx: number;
      gene_end_idx: number;
      length: number;
      sequence: string | null;
    };
    context_regions: Array<{
      region_id: string;
      region_type: string;
      region_number: number;
      gene_start_idx: number;
      gene_end_idx: number;
      length: number;
      sequence: string | null;
      rel: number;
    }>;
    constraints: {
      sequence_alphabet: string[];
      edit_length_must_be_preserved: boolean;
      edit_type: string;
    };
  };
  ui_hints: {
    highlight: {
      type: string;
      pos_gene0: number;
    };
    default_view: string;
  };
}
