import type { InterpretedEvent, MutantTranscriptBlock, SplicingResponse, Step2Data } from './types';

// LOGIC: utility helpers for choosing the primary splicing event and deriving transcript blocks.
export function uniqueNumbers(values: number[] = []) {
  return Array.from(new Set(values));
}

export function getPrimaryEvent(splicingResult: SplicingResponse | null): InterpretedEvent | null {
  if (!splicingResult?.interpreted_events?.length) return null;

  const primaryType = splicingResult.frontend_summary?.primary_event_type;
  const primarySubtype = splicingResult.frontend_summary?.primary_subtype;

  if (!primaryType) {
    return splicingResult.interpreted_events[0] || null;
  }

  return (
    splicingResult.interpreted_events.find((event) => {
      if (event.event_type !== primaryType) return false;
      if (primarySubtype && event.subtype) return event.subtype === primarySubtype;
      return true;
    }) || splicingResult.interpreted_events[0] || null
  );
}

export function getBaseSequenceForRegion(step2Data: Step2Data, regionId: string) {
  const original = step2Data.originalSequences[regionId] || '';
  const snv = step2Data.snvSequences[regionId] || original;
  const seedMode = step2Data.diseaseDetail.disease.seed_mode || 'apply_alt';
  return seedMode === 'reference_is_current' ? original : snv;
}

// LOGIC: convert interpreted splicing events into the abnormal mRNA block sequence shown in the UI.
export function buildMutantTranscriptBlocks(
  normalExons: number[],
  primaryEvent: InterpretedEvent | null
): MutantTranscriptBlock[] {
  const baseBlocks: MutantTranscriptBlock[] = normalExons.map((exonNum) => ({
    key: `canonical-${exonNum}`,
    kind: 'canonical',
    exonNumber: exonNum,
    label: `Exon${exonNum}`,
    state: 'normal',
  }));

  if (!primaryEvent) return baseBlocks;

  if (primaryEvent.event_type === 'EXON_EXCLUSION') {
    const excluded = new Set(primaryEvent.affected_exon_numbers || []);
    return baseBlocks.map((block) =>
      block.exonNumber && excluded.has(block.exonNumber)
        ? { ...block, state: 'excluded' }
        : block
    );
  }

  if (primaryEvent.event_type === 'BOUNDARY_SHIFT') {
    const shifted = new Set(primaryEvent.affected_exon_numbers || []);
    return baseBlocks.map((block) =>
      block.exonNumber && shifted.has(block.exonNumber)
        ? { ...block, state: 'shifted' }
        : block
    );
  }

  if (primaryEvent.event_type === 'PSEUDO_EXON') {
    const affected = uniqueNumbers(primaryEvent.affected_exon_numbers || []);
    if (affected.length < 2) return baseBlocks;

    const leftExon = Math.min(...affected);
    const rightExon = Math.max(...affected);
    const insertIndex = baseBlocks.findIndex((block) => block.exonNumber === rightExon);
    if (insertIndex <= 0) return baseBlocks;

    const pseudoBlock: MutantTranscriptBlock = {
      key: `pseudo-${leftExon}-${rightExon}`,
      kind: 'pseudo_exon',
      label: 'PseudoExon',
    };

    return [
      ...baseBlocks.slice(0, insertIndex),
      pseudoBlock,
      ...baseBlocks.slice(insertIndex),
    ];
  }

  return baseBlocks;
}
