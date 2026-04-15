'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

interface Edit {
  pos: number;
  from: string;
  to: string;
}

interface Region {
  region_id: string;
  region_type: 'exon' | 'intron';
  region_number: number;
  gene_start_idx: number;
  gene_end_idx: number;
  length: number;
  rel?: number;
}

interface InterpretedEvent {
  event_type: string;
  subtype?: string;
  confidence: string;
  summary: string;
  affected_exon_numbers?: number[];
  affected_intron_numbers?: number[];
  size_bp?: number | null;
}

interface FrontendSummary {
  primary_event_type: string;
  primary_subtype?: string;
  confidence: string;
  headline: string;
  interpretation_basis: string;
}

interface SplicingResponse {
  state_id: string;
  disease_id: string;
  gene_id: string;
  focus_region: Region;
  target_regions: Region[];
  interpreted_events: InterpretedEvent[];
  frontend_summary: FrontendSummary;
  warnings: string[];
}

interface DiseaseDetail {
  disease: {
    disease_id: string;
    disease_name: string;
    gene_id: string;
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

interface Step2Data {
  diseaseId: string;
  diseaseDetail: DiseaseDetail;
  editedSequences: { [regionId: string]: string };
  originalSequences: { [regionId: string]: string };
  snvSequences: { [regionId: string]: string };
}

interface DisplayBlock {
  key: string;
  kind: 'canonical' | 'excluded' | 'pseudo_exon';
  label: string;
  exonNumber?: number;
  sizeBp?: number | null;
}

function buildDisplayBlocks(exonNumbers: number[], events: InterpretedEvent[]): { blocks: DisplayBlock[]; excluded: number[] } {
  const excluded = new Set<number>();
  const pseudoInsertions: Array<{ afterExon: number; sizeBp?: number | null; label: string }> = [];

  for (const event of events || []) {
    if (event.event_type === 'EXON_EXCLUSION') {
      for (const exonNumber of event.affected_exon_numbers || []) {
        excluded.add(exonNumber);
      }
      continue;
    }

    if (event.event_type === 'PSEUDO_EXON') {
      let afterExon: number | null = null;
      const intronNumbers = event.affected_intron_numbers || [];
      if (intronNumbers.length > 0) {
        afterExon = intronNumbers[0];
      } else if ((event.affected_exon_numbers || []).length >= 2) {
        const sorted = [...(event.affected_exon_numbers || [])].sort((a, b) => a - b);
        if (sorted[1] === sorted[0] + 1) {
          afterExon = sorted[0];
        }
      }

      if (afterExon != null) {
        pseudoInsertions.push({
          afterExon,
          sizeBp: event.size_bp ?? null,
          label: event.size_bp ? `PseudoExon (+${event.size_bp} bp)` : 'PseudoExon',
        });
      }
    }
  }

  const blocks: DisplayBlock[] = [];
  exonNumbers.forEach((exonNumber) => {
    blocks.push({
      key: `exon-${exonNumber}`,
      kind: excluded.has(exonNumber) ? 'excluded' : 'canonical',
      exonNumber,
      label: `Exon${exonNumber}`,
    });

    pseudoInsertions
      .filter((item) => item.afterExon === exonNumber)
      .forEach((item, idx) => {
        blocks.push({
          key: `pseudo-${exonNumber}-${idx}`,
          kind: 'pseudo_exon',
          label: item.label,
          sizeBp: item.sizeBp,
        });
      });
  });

  return { blocks, excluded: [...excluded] };
}

export default function MatureMRNA() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const diseaseId = searchParams.get('disease_id');

  const [step2Data, setStep2Data] = useState<Step2Data | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stateId, setStateId] = useState<string | null>(null);
  const [splicingResult, setSplicingResult] = useState<SplicingResponse | null>(null);
  const [normalExons, setNormalExons] = useState<number[]>([]);
  const [displayBlocks, setDisplayBlocks] = useState<DisplayBlock[]>([]);
  const [excludedExons, setExcludedExons] = useState<number[]>([]);
  const [eventSummary, setEventSummary] = useState<string>('');

  useEffect(() => {
    const loadDataAndPredict = async () => {
      try {
        const savedData = localStorage.getItem('step2Data');
        if (!savedData) {
          setError('Step2 데이터가 없습니다. Step2로 돌아가세요.');
          setIsLoading(false);
          return;
        }

        const data: Step2Data = JSON.parse(savedData);
        setStep2Data(data);

        const exonCount = data.diseaseDetail.gene.exon_count;
        const allExons = Array.from({ length: exonCount }, (_, i) => i + 1);
        setNormalExons(allExons);
        setDisplayBlocks(allExons.map((exonNumber) => ({
          key: `fallback-${exonNumber}`,
          kind: 'canonical',
          exonNumber,
          label: `Exon${exonNumber}`,
        })));

        const edits: Edit[] = [];

        if (data.snvSequences && data.editedSequences) {
          for (const regionId of Object.keys(data.editedSequences)) {
            const snvSeq = data.snvSequences[regionId] || '';
            const edited = data.editedSequences[regionId] || '';

            const allRegions = [
              data.diseaseDetail.target.focus_region,
              ...data.diseaseDetail.target.context_regions,
            ];
            const region = allRegions.find((r) => r.region_id === regionId);
            if (!region) continue;

            const regionStart = region.gene_start_idx;
            for (let i = 0; i < Math.max(snvSeq.length, edited.length); i += 1) {
              const fromChar = snvSeq[i] || '';
              const toChar = edited[i] || '';
              if (fromChar !== toChar && fromChar !== '') {
                edits.push({
                  pos: regionStart + i,
                  from: fromChar,
                  to: toChar || 'N',
                });
              }
            }
          }
        }

        const createStateResponse = await fetch(
          `${API_BASE_URL}/api/diseases/${encodeURIComponent(data.diseaseId)}/states`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              applied_edit: {
                type: 'user',
                edits: edits.length > 0 ? edits : [],
              },
            }),
          }
        );

        if (!createStateResponse.ok) {
          const errorText = await createStateResponse.text();
          throw new Error(`State 생성 실패: ${createStateResponse.status} - ${errorText}`);
        }

        const stateData = await createStateResponse.json();
        const newStateId = stateData.state_id;
        setStateId(newStateId);

        const splicingResponse = await fetch(
          `${API_BASE_URL}/api/states/${encodeURIComponent(newStateId)}/splicing`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              region_radius: 3,
              flank: 5000,
              include_disease_snv: true,
              include_parent_chain: true,
              strict_ref_check: false,
              return_target_sequence: false,
            }),
          }
        );

        if (!splicingResponse.ok) {
          throw new Error(`Splicing 예측 실패: ${splicingResponse.status}`);
        }

        const splicingData: SplicingResponse = await splicingResponse.json();
        setSplicingResult(splicingData);

        const display = buildDisplayBlocks(allExons, splicingData.interpreted_events || []);
        setDisplayBlocks(display.blocks);
        setExcludedExons(display.excluded);

        if (splicingData.frontend_summary?.headline) {
          setEventSummary(splicingData.frontend_summary.headline);
        } else if (splicingData.interpreted_events?.length > 0) {
          const firstEvent = splicingData.interpreted_events[0];
          setEventSummary(firstEvent.summary || firstEvent.event_type);
        }

        setIsLoading(false);
      } catch (err) {
        console.error('Error:', err);
        setError(err instanceof Error ? err.message : '오류가 발생했습니다.');
        setIsLoading(false);
      }
    };

    void loadDataAndPredict();
  }, [diseaseId]);

  const handleMakeProtein = () => {
    const step3Data = {
      ...step2Data,
      stateId,
      splicingResult,
      normalExons,
      excludedExons,
      displayBlocks,
      eventSummary,
    };
    localStorage.setItem('step3Data', JSON.stringify(step3Data));

    router.push(`/step4?disease_id=${encodeURIComponent(diseaseId || '')}&state_id=${encodeURIComponent(stateId || '')}`);
  };

  const mutantBlocks = useMemo(() => {
    if (displayBlocks.length > 0) return displayBlocks;
    return normalExons.map((exonNumber) => ({
      key: `fallback-${exonNumber}`,
      kind: 'canonical' as const,
      exonNumber,
      label: `Exon${exonNumber}`,
    }));
  }, [displayBlocks, normalExons]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-transparent px-4">
        <div className="w-full max-w-md rounded-[24px] border border-white/18 bg-white/5 p-10 text-center shadow-[0_30px_120px_rgba(15,23,42,0.16)] backdrop-blur-lg">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
          <p className="mt-4 font-semibold text-slate-950">Splicing 예측 중...</p>
        </div>
      </div>
    );
  }

  if (error || !step2Data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-transparent px-4">
        <div className="w-full max-w-md rounded-[24px] border border-white/18 bg-white/5 p-10 text-center shadow-[0_30px_120px_rgba(15,23,42,0.16)] backdrop-blur-lg">
          <p className="mb-4 text-rose-900">{error || '데이터를 불러올 수 없습니다'}</p>
          <button
            onClick={() => router.push('/select-mutant')}
            className="rounded-[14px] border border-black/10 bg-white/10 px-6 py-2 font-bold text-slate-900 shadow-[0_12px_30px_rgba(15,23,42,0.06)] transition hover:bg-white/12"
          >
            Step 1로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  const geneSymbol = step2Data.diseaseDetail.gene.gene_symbol;

  return (
    <div className="relative min-h-screen overflow-hidden bg-transparent px-4 py-8 sm:px-6 lg:px-8">
      <div className="relative mx-auto max-w-6xl">
        <div className="mb-8 rounded-[24px] border border-white/18 bg-white/5 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          <div className="mb-4 inline-flex rounded-[14px] border border-black/10 bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.32em] text-slate-800">
            Splice Playground
          </div>
          <h1 className="text-4xl font-black tracking-tight text-slate-950 sm:text-5xl">3. Mature mRNA</h1>
        </div>

        <div className="relative rounded-[28px] border border-white/18 bg-white/5 p-5 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          <div className="mb-12">
            <p className="mb-4 text-xl font-bold text-slate-950">{geneSymbol} (정상)</p>
            <div className="flex flex-wrap items-center gap-1">
              {normalExons.map((exonNum) => (
                <div
                  key={`normal-${exonNum}`}
                  className="min-w-16 rounded-xl border border-white/16 bg-white/5 px-4 py-2 text-center shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm"
                >
                  <span className="text-sm font-semibold text-slate-950">Exon{exonNum}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="mb-12">
            <p className="mb-4 text-xl font-bold italic text-rose-800">{geneSymbol} (비정상)</p>
            <div className="relative">
              <div className="flex flex-wrap items-center gap-1">
                {mutantBlocks.map((block) => {
                  if (block.kind === 'pseudo_exon') {
                    return (
                      <div
                        key={block.key}
                        className="min-w-20 rounded-xl border border-amber-300/40 bg-amber-100/12 px-3 py-2 text-center shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm"
                      >
                        <span className="text-sm font-semibold text-amber-900">{block.label}</span>
                        {block.sizeBp ? <div className="text-[11px] text-amber-800">{block.sizeBp} bp</div> : null}
                      </div>
                    );
                  }

                  if (block.kind === 'excluded') {
                    return (
                      <div key={block.key} className="relative">
                        <div className="min-w-16 rounded-xl border border-dashed border-rose-300/35 bg-rose-100/10 px-4 py-2 text-center opacity-70 shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm">
                          <span className="text-sm font-semibold text-rose-800 line-through">{block.label}</span>
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div
                      key={block.key}
                      className="min-w-16 rounded-xl border border-white/16 bg-white/5 px-4 py-2 text-center shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm"
                    >
                      <span className="text-sm font-semibold text-slate-950">{block.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {excludedExons.length > 0 ? (
              <p className="mt-3 text-xs text-rose-800">Excluded exons: {excludedExons.join(', ')}</p>
            ) : null}

            {eventSummary && (
              <div className="mt-16 rounded-[18px] border border-amber-300/30 bg-amber-100/10 p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
                <p className="font-semibold text-amber-900">{eventSummary}</p>
              </div>
            )}
          </div>

          <div className="mt-8 flex justify-end">
            <button
              onClick={handleMakeProtein}
              className="rounded-full border border-cyan-300/60 bg-[linear-gradient(135deg,rgba(14,165,233,0.95),rgba(37,99,235,0.92))] px-10 py-4 text-2xl font-bold text-white shadow-[0_18px_45px_rgba(2,132,199,0.35)] transition-all hover:brightness-105"
            >
              Make Protein
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
