// Mol* viewer data contracts: structure inputs and computed comparison callback payload.
export type MolstarFormat = 'mmcif' | 'bcif' | 'pdb' | string;

export interface MolstarStructureInput {
  url: string | null;
  format?: MolstarFormat | null;
  label?: string | null;
  chainId?: string | null;
  color?: number;
}

export interface MolstarComputedComparison {
  method: 'tm-align' | 'sequence-align' | 'identical-reuse' | 'unavailable';
  tm_score_1?: number | null;
  tm_score_2?: number | null;
  rmsd?: number | null;
  aligned_length?: number | null;
  note?: string | null;
}

export interface MolstarViewerProps {
  primary: MolstarStructureInput | null;
  secondary?: MolstarStructureInput | null;
  mode?: 'single' | 'overlay';
  onComputedComparison?: (comparison: MolstarComputedComparison | null) => void;
}

export const DEFAULT_PRIMARY_COLOR = 0x22c55e;
export const DEFAULT_SECONDARY_COLOR = 0xef4444;
export const VIEWER_HEIGHT_CLASS = 'h-[560px]';
export const USE_IFRAME_OVERLAY = process.env.NODE_ENV === 'production';
