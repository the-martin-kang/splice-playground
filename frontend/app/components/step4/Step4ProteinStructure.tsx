'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import type { MolstarComputedComparison } from '../molstar/MolstarViewer';
import ProteinMetricCards from './ProteinMetricCards';
import StructureComparisonPanel from './StructureComparisonPanel';
import StructureViewerPanel from './StructureViewerPanel';
import TranscriptBlocksPanel from './TranscriptBlocksPanel';
import TranslationSummaryPanel from './TranslationSummaryPanel';
import {
  buildJobProgress,
  buildStructureComparison,
  buildViewerTargets,
  getStructureScoreDetails,
} from './step4Transforms';
import { useStep3Snapshot } from './useStep3Snapshot';
import { useStep4State } from './useStep4State';
import { useStructureJob } from './useStructureJob';
import type { Step4StructureComparison } from './types';

export default function Step4ProteinStructure() {
  // LOGIC: route params, Step 4 API state, structure job state, viewer target state, and Step 3 summary state.
  const router = useRouter();
  const searchParams = useSearchParams();
  const diseaseId = searchParams.get('disease_id');
  const stateId = searchParams.get('state_id');

  const {
    diseaseName,
    step3AffectedExons,
    step3EventHeadline,
    step3AffectedSummary,
  } = useStep3Snapshot();

  const {
    step4Data,
    isLoading,
    error,
    activeStructureView,
    setActiveStructureView,
    stableNormalTarget,
    stableUserTarget,
    setStableUserTarget,
    fetchStep4,
  } = useStep4State(diseaseId, stateId);

  const {
    job,
    jobError,
    jobMessage,
    isSubmittingJob,
    createStructureJob,
  } = useStructureJob(stateId, step4Data, setStableUserTarget, fetchStep4);

  const [frontendStructureComparison, setFrontendStructureComparison] = useState<Step4StructureComparison | null>(null);
  const hasAutoSelectedUserStructureRef = useRef(false);

  // LOGIC: receive frontend Mol* overlay comparison and normalize it into Step 4 comparison shape.
  const handleComputedComparison = useCallback((nextComparison: MolstarComputedComparison | null) => {
    if (!nextComparison) {
      setFrontendStructureComparison(null);
      return;
    }
    setFrontendStructureComparison({
      method: nextComparison.method,
      tm_score_1: nextComparison.tm_score_1 ?? null,
      tm_score_2: nextComparison.tm_score_2 ?? null,
      rmsd: nextComparison.rmsd ?? null,
      aligned_length: nextComparison.aligned_length ?? null,
    });
  }, []);

  const autoViewUserUrl = step4Data
    ? buildViewerTargets(
        stableNormalTarget,
        stableUserTarget,
        step4Data.user_track.comparison_to_normal,
        activeStructureView
      ).userViewerTarget?.url || null
    : null;
  const autoViewSameAsNormal = step4Data?.user_track.comparison_to_normal.same_as_normal ?? false;

  // LOGIC: when a predicted/reused user structure becomes available, move from baseline view to the useful compare view once.
  useEffect(() => {
    if (hasAutoSelectedUserStructureRef.current) return;
    if (!autoViewUserUrl) return;
    if (activeStructureView !== 'normal') return;

    hasAutoSelectedUserStructureRef.current = true;
    setActiveStructureView(autoViewSameAsNormal ? 'user' : 'overlay');
  }, [activeStructureView, autoViewSameAsNormal, autoViewUserUrl, setActiveStructureView]);

  // UI: Step 4 loading and fatal error states.
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-transparent px-4">
        <div className="w-full max-w-md rounded-[24px] border border-white/18 bg-white/5 p-10 text-center shadow-[0_30px_120px_rgba(15,23,42,0.16)] backdrop-blur-lg">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
          <p className="mt-4 font-semibold text-slate-950">Step 4 데이터를 불러오는 중...</p>
        </div>
      </div>
    );
  }

  if (error || !step4Data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-transparent px-4">
        <div className="w-full max-w-md rounded-[24px] border border-white/18 bg-white/5 p-10 text-center shadow-[0_30px_120px_rgba(15,23,42,0.16)] backdrop-blur-lg">
          <p className="mb-4 text-rose-900">{error || 'Step 4 데이터를 불러올 수 없습니다.'}</p>
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

  const comparison = step4Data.user_track.comparison_to_normal;
  const translation = step4Data.user_track.translation_sanity;
  const normalStructureTarget = stableNormalTarget;
  const userStructureTarget = stableUserTarget;

  const {
    normalViewerTarget,
    overlaySecondary,
    userViewerTarget,
    singleDisplayedTarget,
  } = buildViewerTargets(
    normalStructureTarget,
    userStructureTarget,
    comparison,
    activeStructureView
  );

  const structureComparison = buildStructureComparison(job, frontendStructureComparison, comparison);
  const {
    structureSimilarityScore,
    structureScoreLabel,
  } = getStructureScoreDetails(structureComparison);

  const transcriptBlocks = step4Data.user_track.predicted_transcript.blocks;
  const excludedExons = step4Data.user_track.predicted_transcript.excluded_exon_numbers || [];
  const affectedExons = Array.from(new Set(step3AffectedExons));
  const transcriptHeadline = step3EventHeadline || step3AffectedSummary || null;

  const progress = buildJobProgress(job, step4Data, Boolean(userViewerTarget?.url));

  // UI: Step 4 dashboard, Mol* viewer controls, translation summary, job controls, and transcript/structure metrics.
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-transparent px-4 py-8 pb-16 sm:px-6 lg:px-8">
      <div className="relative mx-auto max-w-7xl space-y-8">
        <section className="rounded-[24px] border border-white/18 bg-white/5 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          <div className="mb-4 inline-flex rounded-[14px] border border-black/10 bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.32em] text-slate-800">
            Splice Playground
          </div>
          <h1 className="text-4xl font-black tracking-tight text-slate-950 sm:text-5xl">4. Protein Structure</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-800 sm:text-base">
            {diseaseName || step4Data.disease_id}의 정상 단백질 구조와 사용자 편집 상태에서 예측된 단백질 결과를 비교합니다.
          </p>
          <div className="mt-6 flex flex-wrap gap-3 text-xs text-slate-800">
            <span className="rounded-[12px] border border-black/10 bg-white/10 px-3 py-1">Gene: {step4Data.gene_symbol || step4Data.gene_id}</span>
            <span className="rounded-[12px] border border-black/10 bg-white/10 px-3 py-1">State: {step4Data.state_id}</span>
            <span className="rounded-[12px] border border-black/10 bg-white/10 px-3 py-1">Strategy: {step4Data.user_track.recommended_structure_strategy}</span>
          </div>
        </section>

        <ProteinMetricCards
          comparison={comparison}
          structureSimilarityScore={structureSimilarityScore}
        />

        <section className="grid gap-8 xl:grid-cols-[1.5fr_0.9fr]">
          <StructureViewerPanel
            activeStructureView={activeStructureView}
            setActiveStructureView={setActiveStructureView}
            normalViewerTarget={normalViewerTarget}
            userViewerTarget={userViewerTarget}
            singleDisplayedTarget={singleDisplayedTarget}
            normalStructureTarget={normalStructureTarget}
            userStructureTarget={userStructureTarget}
            overlaySecondary={overlaySecondary}
            structureComparison={structureComparison}
            job={job}
            onComputedComparison={handleComputedComparison}
          />

          <div className="space-y-6">
            <TranslationSummaryPanel
              translation={translation}
              comparison={comparison}
              structureSimilarityScore={structureSimilarityScore}
              progress={progress}
              jobMessage={jobMessage}
              jobError={jobError}
              step4Data={step4Data}
              userViewerTarget={userViewerTarget}
              isSubmittingJob={isSubmittingJob}
              onRefresh={() => fetchStep4(false)}
              onCreateStructureJob={createStructureJob}
            />

            <TranscriptBlocksPanel
              transcriptBlocks={transcriptBlocks}
              affectedExons={affectedExons}
              excludedExons={excludedExons}
              transcriptHeadline={transcriptHeadline}
            />

            <StructureComparisonPanel
              structureComparison={structureComparison}
              structureScoreLabel={structureScoreLabel}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
