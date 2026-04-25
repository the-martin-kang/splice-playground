// Step 3 data contracts: Step 2 snapshot, backend state/splicing responses, and transcript UI blocks.
// 타입 정의
export interface Edit {
  pos: number;
  from: string;
  to: string;
}

export interface Region {
  region_id: string;
  region_type: 'exon' | 'intron';
  region_number: number;
  gene_start_idx: number;
  gene_end_idx: number;
  length: number;
  rel?: number;
}

export interface InterpretedEvent {
  event_type: string;
  subtype?: string;
  confidence: string;
  summary: string;
  affected_exon_numbers?: number[];
  affected_intron_numbers?: number[];
}

export interface FrontendSummary {
  primary_event_type: string;
  primary_subtype?: string;
  confidence: string;
  headline: string;
  interpretation_basis: string;
}

export interface SplicingResponse {
  state_id: string;
  disease_id: string;
  gene_id: string;
  focus_region: Region;
  target_regions: Region[];
  interpreted_events: InterpretedEvent[];
  frontend_summary: FrontendSummary;
  warnings: string[];
}

export interface DiseaseDetail {
  disease: {
    disease_id: string;
    disease_name: string;
    gene_id: string;
    seed_mode?: string | null;
  };
  gene: {
    gene_id: string;
    gene_symbol: string;
    chromosome: string;
    strand: string;
    exon_count: number;
  };
  splice_altering_snv: {
    pos_gene0: number;
    ref: string;
    alt: string;
  } | null;
  target: {
    focus_region: Region;
    context_regions: Region[];
  };
}

export interface Step2Data {
  diseaseId: string;
  diseaseDetail: DiseaseDetail;
  editedSequences: { [regionId: string]: string };
  originalSequences: { [regionId: string]: string };
  snvSequences: { [regionId: string]: string };
}

export interface MutantTranscriptBlock {
  key: string;
  kind: 'canonical' | 'pseudo_exon';
  exonNumber?: number;
  label: string;
  state?: 'normal' | 'excluded' | 'shifted';
}
