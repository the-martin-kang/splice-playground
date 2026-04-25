// Step 2 data contracts: disease detail, target regions, and per-region sequence payloads.
export interface Region {
  region_id: string;
  region_type: 'exon' | 'intron';
  region_number: number;
  gene_start_idx: number;
  gene_end_idx: number;
  length: number;
  sequence: string | null;
  rel?: number;
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

export interface RegionData {
  disease_id: string;
  gene_id: string;
  region: Region;
}

export interface DifferenceSummary {
  toReference: number;
  toSeed: number;
}
