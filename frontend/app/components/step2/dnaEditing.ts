import type { DiseaseDetail, Region } from './types';

export const BASE_MAP: Record<string, string> = {
  A: 'A',
  C: 'C',
  G: 'G',
  T: 'T',
  N: 'N',
  a: 'A',
  c: 'C',
  g: 'G',
  t: 'T',
  n: 'N',
  'ㅁ': 'A',
  'ㅊ': 'C',
  'ㅎ': 'G',
  'ㅅ': 'T',
  'ㅜ': 'N',
};

// LOGIC: sanitize DNA input and Korean keyboard equivalents into fixed alphabet bases.
export function normalizeBases(input: string): string {
  let out = '';
  for (const char of input) {
    const mapped = BASE_MAP[char];
    if (mapped) out += mapped;
  }
  return out;
}

// LOGIC: preserve sequence length by replacing deleted/cleared ranges with N.
export function replaceRangeWithNs(sequence: string, start: number, end: number) {
  if (start >= end) return sequence;
  return sequence.slice(0, start) + 'N'.repeat(end - start) + sequence.slice(end);
}

// LOGIC: fixed-length overwrite editor behavior used by the sequence textarea.
export function overwriteSequence(
  original: string,
  start: number,
  end: number,
  insertedRaw: string
): { next: string; caret: number } {
  const inserted = normalizeBases(insertedRaw);
  if (!inserted) {
    return {
      next: replaceRangeWithNs(original, start, end),
      caret: start,
    };
  }

  const chars = original.split('');
  for (let i = start; i < end; i += 1) chars[i] = 'N';

  let cursor = start;
  for (const base of inserted) {
    if (cursor >= chars.length) break;
    chars[cursor] = base;
    cursor += 1;
  }

  return { next: chars.join(''), caret: cursor };
}

// LOGIC: apply the representative disease SNV to a region sequence when it falls inside that region.
export function applySnvToSequence(
  sequence: string,
  region: Region,
  diseaseDetail: DiseaseDetail | null
): string {
  if (!diseaseDetail?.splice_altering_snv) return sequence;

  const snvPos = diseaseDetail.splice_altering_snv.pos_gene0;
  const { gene_start_idx, gene_end_idx } = region;

  if (snvPos >= gene_start_idx && snvPos <= gene_end_idx) {
    const localIndex = snvPos - gene_start_idx;
    const alt = diseaseDetail.splice_altering_snv.alt;
    return sequence.substring(0, localIndex) + alt + sequence.substring(localIndex + 1);
  }

  return sequence;
}
