'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import EventSummaryCard from './EventSummaryCard';
import { buildMutantTranscriptBlocks, getPrimaryEvent } from './splicingTransform';
import TranscriptTrack from './TranscriptTrack';
import { useSplicingPrediction } from './useSplicingPrediction';

export default function Step3MatureMrna() {
  // LOGIC: route params, Step 2 snapshot, generated backend state, and splicing prediction result.
  const router = useRouter();
  const searchParams = useSearchParams();
  const diseaseId = searchParams.get('disease_id');

  const {
    step2Data,
    isLoading,
    error,
    stateId,
    splicingResult,
    normalExons,
    affectedExons,
    eventSummary,
  } = useSplicingPrediction(diseaseId);

  // LOGIC: persist Step 3 output for Step 4 and navigate forward.
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

  // UI: Step 3 loading and fatal error states.
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

  // UI: normal mRNA, abnormal mRNA visualization, event summary, and Make Protein action.
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
          
          <TranscriptTrack
            geneSymbol={geneSymbol}
            normalExons={normalExons}
            mutantTranscriptBlocks={mutantTranscriptBlocks}
          />
          
          {/* 이벤트 요약 */}
          <EventSummaryCard eventSummary={eventSummary} />

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
