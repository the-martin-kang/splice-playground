'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { API_BASE_URL } from '../lib/api';

// 타입 정의
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

interface Step2Data {
  diseaseId: string;
  diseaseDetail: DiseaseDetail;
  editedSequences: { [regionId: string]: string };
  originalSequences: { [regionId: string]: string };
  snvSequences: { [regionId: string]: string };
}

interface MutantTranscriptBlock {
  key: string;
  kind: 'canonical' | 'pseudo_exon';
  exonNumber?: number;
  label: string;
  state?: 'normal' | 'excluded' | 'shifted';
}

function uniqueNumbers(values: number[] = []) {
  return Array.from(new Set(values));
}

function getPrimaryEvent(splicingResult: SplicingResponse | null): InterpretedEvent | null {
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

function getBaseSequenceForRegion(step2Data: Step2Data, regionId: string) {
  const original = step2Data.originalSequences[regionId] || '';
  const snv = step2Data.snvSequences[regionId] || original;
  const seedMode = step2Data.diseaseDetail.disease.seed_mode || 'apply_alt';
  return seedMode === 'reference_is_current' ? original : snv;
}

function buildMutantTranscriptBlocks(normalExons: number[], primaryEvent: InterpretedEvent | null) {
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

export default function MatureMRNA() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const diseaseId = searchParams.get('disease_id');

  const [step2Data, setStep2Data] = useState<Step2Data | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // State & Splicing 결과
  const [stateId, setStateId] = useState<string | null>(null);
  const [splicingResult, setSplicingResult] = useState<SplicingResponse | null>(null);

  // 정상 mRNA exon 목록 (전체 exon)
  const [normalExons, setNormalExons] = useState<number[]>([]);
  
  // 비정상 mRNA - affected exons
  const [affectedExons, setAffectedExons] = useState<number[]>([]);
  
  // 이벤트 요약
  const [eventSummary, setEventSummary] = useState<string>('');

  useEffect(() => {
    const loadDataAndPredict = async () => {
      try {
        // Step2에서 저장한 데이터 로드
        const savedData = localStorage.getItem('step2Data');
        if (!savedData) {
          setError('Step2 데이터가 없습니다. Step2로 돌아가세요.');
          setIsLoading(false);
          return;
        }

        const data: Step2Data = JSON.parse(savedData);
        setStep2Data(data);

        // Exon 개수 가져오기
        const exonCount = data.diseaseDetail.gene.exon_count;
        const allExons = Array.from({ length: exonCount }, (_, i) => i + 1);
        setNormalExons(allExons);

        // Step2에서 편집한 내용을 edits 배열로 변환
        // current seed sequence(apply_alt면 representative SNV 적용, reference_is_current면 reference)와 사용자 편집 서열 비교
        const edits: Edit[] = [];
        
        if (data.snvSequences && data.editedSequences) {
          // 각 region별로 비교
          for (const regionId of Object.keys(data.editedSequences)) {
            const baseSeq = getBaseSequenceForRegion(data, regionId);
            const edited = data.editedSequences[regionId] || '';
            
            // region의 gene_start_idx 찾기
            const allRegions = [
              data.diseaseDetail.target.focus_region,
              ...data.diseaseDetail.target.context_regions
            ];
            const region = allRegions.find(r => r.region_id === regionId);
            
            if (!region) continue;
            
            const regionStart = region.gene_start_idx;
            
            // 각 위치별로 비교 (current seed sequence와 편집 서열)
            for (let i = 0; i < Math.max(baseSeq.length, edited.length); i++) {
              const fromChar = baseSeq[i] || '';
              const toChar = edited[i] || '';
              
              // SNV 적용 서열과 다르면 모두 edit으로 추가 (including N for deletions)
              if (fromChar !== toChar && fromChar !== '') {
                edits.push({
                  pos: regionStart + i,
                  from: fromChar,
                  to: toChar
                });
              }
            }
          }
        }

        // 1. Create State API 호출
        const createStateResponse = await fetch(
          `${API_BASE_URL}/api/diseases/${encodeURIComponent(data.diseaseId)}/states`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              applied_edit: {
                type: 'user',
                edits: edits.length > 0 ? edits : []
              }
            })
          }
        );

        if (!createStateResponse.ok) {
          const errorText = await createStateResponse.text();
          console.error('State 생성 에러:', errorText);
          throw new Error(`State 생성 실패: ${createStateResponse.status} - ${errorText}`);
        }

        const stateData = await createStateResponse.json();
        const newStateId = stateData.state_id;
        setStateId(newStateId);

        // 2. Predict Splicing API 호출
        const splicingResponse = await fetch(
          `${API_BASE_URL}/api/states/${encodeURIComponent(newStateId)}/splicing`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              region_radius: 3,
              flank: 5000,
              include_disease_snv: true,
              include_parent_chain: true,
              strict_ref_check: false,
              return_target_sequence: false
            })
          }
        );

        if (!splicingResponse.ok) {
          throw new Error(`Splicing 예측 실패: ${splicingResponse.status}`);
        }

        const splicingData: SplicingResponse = await splicingResponse.json();
        setSplicingResult(splicingData);

        const primaryEvent = getPrimaryEvent(splicingData);
        setAffectedExons(uniqueNumbers(primaryEvent?.affected_exon_numbers || []));

        // 이벤트 요약 설정
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

    loadDataAndPredict();
  }, [diseaseId]);

  // Step 4로 이동
  const handleMakeProtein = () => {
    // Step3 데이터 저장
    const step3Data = {
      ...step2Data,
      stateId,
      splicingResult,
      normalExons,
      affectedExons,
      eventSummary
    };
    localStorage.setItem('step3Data', JSON.stringify(step3Data));
    
    router.push(`/step4?disease_id=${encodeURIComponent(diseaseId || '')}&state_id=${encodeURIComponent(stateId || '')}`);
  };

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
  const primaryEvent = getPrimaryEvent(splicingResult);
  const mutantTranscriptBlocks = buildMutantTranscriptBlocks(normalExons, primaryEvent);

  return (
    <div className="relative min-h-screen overflow-hidden bg-transparent px-4 py-8 sm:px-6 lg:px-8">
      <div className="relative mx-auto max-w-6xl">
        {/* (1) 제목 */}
        <div className="mb-8 rounded-[24px] border border-white/18 bg-white/5 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          <div className="mb-4 inline-flex rounded-[14px] border border-black/10 bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.32em] text-slate-800">
            Splice Playground
          </div>
          <h1 className="text-4xl font-black tracking-tight text-slate-950 sm:text-5xl">3. Mature mRNA</h1>
        </div>

        {/* Main Container */}
        <div className="relative rounded-[28px] border border-white/18 bg-white/5 p-5 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          
          {/* (2) 정상 mRNA */}
          <div className="mb-12">
            <p className="mb-4 text-xl font-bold text-slate-950">{geneSymbol} (정상)</p>
            <div className="flex items-center gap-1 flex-wrap">
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

          {/* (3) 비정상 mRNA */}
          <div className="mb-12">
            <p className="mb-4 text-xl font-bold italic text-rose-800">{geneSymbol} (비정상)</p>
            <div className="relative">
              <div className="flex items-center gap-1 flex-wrap">
                {mutantTranscriptBlocks.map((block) => {
                  if (block.kind === 'pseudo_exon') {
                    return (
                      <div
                        key={block.key}
                        className="min-w-16 rounded-xl border border-amber-300/35 bg-amber-100/10 px-4 py-2 text-center shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm"
                      >
                        <span className="text-sm font-semibold text-amber-900">{block.label}</span>
                      </div>
                    );
                  }

                  if (block.state === 'excluded') {
                    return (
                      <div key={block.key} className="relative">
                        <div className="min-w-16 rounded-xl border border-dashed border-rose-300/35 bg-rose-100/10 px-4 py-2 text-center opacity-70 shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm">
                          <span className="text-sm font-semibold text-rose-800 line-through">{block.label}</span>
                        </div>
                      </div>
                    );
                  }

                  if (block.state === 'shifted') {
                    return (
                      <div
                        key={block.key}
                        className="min-w-16 rounded-xl border border-cyan-300/35 bg-cyan-100/10 px-4 py-2 text-center shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm"
                      >
                        <span className="text-sm font-semibold text-cyan-900">{block.label}</span>
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
            
            {/* 이벤트 요약 */}
            {eventSummary && (
              <div className="mt-16 rounded-[18px] border border-amber-300/30 bg-amber-100/10 p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
                <p className="font-semibold text-amber-900">{eventSummary}</p>
              </div>
            )}
          </div>

          {/* (4) Make Protein 버튼 */}
          <div className="flex justify-end mt-8">
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
