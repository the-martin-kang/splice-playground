import type { MolstarStructureInput } from '../molstar/MolstarViewer';

// Step 4 data contracts: structure assets, prediction jobs, transcript/translation summaries, and API response shape.
export type StructureStrategy = 'reuse_baseline' | 'predict_user_structure';
export type ActiveStructureView = 'normal' | 'user' | 'overlay';

export interface MolstarTarget {
  structure_asset_id?: string | null;
  provider?: string | null;
  source_db?: string | null;
  source_id?: string | null;
  source_chain_id?: string | null;
  title?: string | null;
  url?: string | null;
  format?: string | null;
}

export interface StructureAsset {
  structure_asset_id: string;
  provider: string;
  source_db: string;
  source_id: string;
  source_chain_id?: string | null;
  structure_kind: string;
  title?: string | null;
  method?: string | null;
  resolution_angstrom?: number | null;
  mapped_coverage?: number | null;
  mean_plddt?: number | null;
  file_format: string;
  viewer_format?: string | null;
  is_default?: boolean;
  validation_status: string;
  signed_url?: string | null;
  signed_url_expires_in?: number | null;
}

export interface Step4StructureComparison {
  method?: string | null;
  tm_score_1?: number | null;
  tm_score_2?: number | null;
  rmsd?: number | null;
  aligned_length?: number | null;
}

export interface Step4StructureJob {
  job_id: string;
  state_id: string;
  provider: string;
  status: string;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  reused_baseline_structure?: boolean;
  molstar_default?: MolstarTarget | null;
  structure_comparison?: Step4StructureComparison | null;
}

export interface TranscriptBlock {
  block_id: string;
  block_kind: 'canonical_exon' | 'pseudo_exon' | 'boundary_shift';
  label: string;
  length: number;
  canonical_exon_number?: number | null;
  notes: string[];
}

export interface TranslationSanity {
  translation_ok: boolean;
  protein_length?: number;
  cds_length_nt?: number;
  frameshift_likely?: boolean | null;
  premature_stop_likely?: boolean | null;
  stop_codon_found?: boolean;
  multiple_of_three?: boolean;
  notes: string[];
}

export interface SequenceComparison {
  same_as_normal: boolean;
  normal_protein_length: number;
  user_protein_length: number;
  length_delta_aa: number;
  first_mismatch_aa_1?: number | null;
  normalized_edit_similarity: number;
  notes: string[];
}

export interface BaselineProtein {
  transcript_id: string;
  transcript_kind: string;
  refseq_protein_id?: string | null;
  uniprot_accession?: string | null;
  protein_length: number;
  validation_status: string;
}

export interface Step4StateResponse {
  disease_id: string;
  state_id: string;
  gene_id: string;
  gene_symbol?: string | null;
  normal_track: {
    baseline_protein: BaselineProtein;
    structures: StructureAsset[];
    default_structure_asset_id?: string | null;
    default_structure?: StructureAsset | null;
    molstar_default?: MolstarTarget | null;
  };
  user_track: {
    state_id: string;
    representative_snv_applied: boolean;
    predicted_transcript: {
      primary_event_type: string;
      primary_subtype?: string | null;
      blocks: TranscriptBlock[];
      included_exon_numbers: number[];
      excluded_exon_numbers: number[];
      inserted_block_count: number;
      warnings: string[];
    };
    translation_sanity: TranslationSanity;
    comparison_to_normal: SequenceComparison;
    structure_prediction_enabled: boolean;
    structure_prediction_message?: string | null;
    can_reuse_normal_structure: boolean;
    recommended_structure_strategy: StructureStrategy;
    latest_structure_job?: Step4StructureJob | null;
    structure_jobs: Step4StructureJob[];
    warnings: string[];
  };
  capabilities: {
    normal_structure_ready: boolean;
    user_track_available: boolean;
    structure_prediction_enabled: boolean;
    create_job_endpoint_enabled: boolean;
    prediction_mode: 'disabled' | 'job_queue';
    reason?: string | null;
  };
  ready_for_frontend: boolean;
  notes: string[];
}

export interface CreateJobResponse {
  created: boolean;
  reused_baseline_structure?: boolean;
  message: string;
  job?: Step4StructureJob | null;
  user_track?: Step4StateResponse['user_track'] | null;
}

export interface Step3SummaryEvent {
  event_type?: string;
  summary?: string;
  affected_exon_numbers?: number[];
}

export interface Step3Snapshot {
  eventSummary?: string;
  affectedExons?: number[];
  splicingResult?: {
    frontend_summary?: { headline?: string };
    interpreted_events?: Step3SummaryEvent[];
  };
}

export interface Step3SummaryState {
  diseaseName: string | null;
  step3AffectedExons: number[];
  step3EventHeadline: string | null;
  step3AffectedSummary: string | null;
}

export interface JobProgress {
  tone: 'slate' | 'amber' | 'emerald' | 'rose';
  title: string;
  body: string;
  meta?: string | null;
  spinning?: boolean;
}

export interface ViewerTargets {
  normalViewerTarget: MolstarStructureInput | null;
  overlaySecondary: MolstarTarget | null;
  userViewerTarget: MolstarStructureInput | null;
  singleDisplayedTarget: MolstarStructureInput | null;
}
