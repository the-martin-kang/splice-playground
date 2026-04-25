'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import ChromosomeBadge from './ChromosomeBadge';
import GeneDiagram from './GeneDiagram';
import SequenceEditor from './SequenceEditor';
import { useRegionSequenceEditor } from './useRegionSequenceEditor';
import { useStep2Disease } from './useStep2Disease';

export default function Step2DnaEditor() {
  // LOGIC: query params, route transition, fetched disease detail, selected region, and edited sequences.
  const router = useRouter();
  const searchParams = useSearchParams();
  const diseaseId = searchParams.get('disease_id');

  const {
    diseaseDetail,
    isLoading,
    error,
    diagramRegions,
  } = useStep2Disease(diseaseId);

  const sequenceEditor = useRegionSequenceEditor(diseaseId, diseaseDetail, diagramRegions);

  // LOGIC: persist Step 2 output for Step 3 and navigate forward.
  const handleNextStep = () => {
    const step2Data = {
      diseaseId,
      diseaseDetail,
      editedSequences: sequenceEditor.editedSequences,
      originalSequences: sequenceEditor.originalSequences,
      snvSequences: sequenceEditor.snvSequences,
    };
    localStorage.setItem('step2Data', JSON.stringify(step2Data));
    router.push(`/step3?disease_id=${encodeURIComponent(diseaseId || '')}`);
  };

  // UI: Step 2 loading and fatal error states.
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-transparent px-4">
        <div className="w-full max-w-md rounded-[24px] border border-white/18 bg-white/5 p-10 text-center shadow-[0_30px_120px_rgba(15,23,42,0.16)] backdrop-blur-lg">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
          <p className="mt-4 font-semibold text-slate-950">로딩 중...</p>
        </div>
      </div>
    );
  }

  if (error || !diseaseDetail) {
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

  // UI: Step 2 gene diagram, region selector, sequence comparison/editor, and Next action.
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-transparent px-4 py-8 sm:px-6 lg:px-8">
      <div className="relative mx-auto max-w-7xl">
        <div className="mb-8 rounded-[24px] border border-white/18 bg-white/5 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          <div className="mb-4 inline-flex rounded-[14px] border border-black/10 bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.32em] text-slate-800">
            Splice Playground
          </div>
          <h1 className="text-4xl font-black tracking-tight text-slate-950 sm:text-5xl">2. Manipulate DNA</h1>
        </div>

        <div className="relative rounded-[28px] border border-white/18 bg-white/5 p-8 pt-10 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-10 sm:pt-14">
          <ChromosomeBadge gene={diseaseDetail.gene} />

          <GeneDiagram
            gene={diseaseDetail.gene}
            diagramRegions={diagramRegions}
            selectedRegion={sequenceEditor.selectedRegion}
            hasSNV={sequenceEditor.hasSNV}
            hasEdits={sequenceEditor.hasEdits}
            onRegionClick={sequenceEditor.handleRegionClick}
          />

          <SequenceEditor
            selectedRegion={sequenceEditor.selectedRegion}
            isRegionLoading={sequenceEditor.isRegionLoading}
            currentSequence={sequenceEditor.currentSequence}
            currentOriginalSequence={sequenceEditor.currentOriginalSequence}
            editorDisplaySequence={sequenceEditor.editorDisplaySequence}
            editorDisplayOriginalSequence={sequenceEditor.editorDisplayOriginalSequence}
            onEditorLineLengthChange={sequenceEditor.handleEditorLineLengthChange}
            differenceSummary={sequenceEditor.differenceSummary}
            textareaRef={sequenceEditor.textareaRef}
            editorBackdropRef={sequenceEditor.editorBackdropRef}
            onRestoreDiseaseSnv={sequenceEditor.restoreDiseaseSnv}
            onRestoreReference={sequenceEditor.restoreReference}
            onEditorKeyDown={sequenceEditor.handleEditorKeyDown}
            onBeforeInput={sequenceEditor.handleBeforeInput}
            onPaste={sequenceEditor.handlePaste}
            onTextareaFallbackChange={sequenceEditor.handleTextareaFallbackChange}
            onEditorScroll={sequenceEditor.handleEditorScroll}
          />

          <div className="mt-8 flex justify-end">
            <button
              onClick={handleNextStep}
              className="rounded-full border border-cyan-300/60 bg-[linear-gradient(135deg,rgba(14,165,233,0.95),rgba(37,99,235,0.92))] px-12 py-4 text-2xl font-bold italic text-white shadow-[0_18px_45px_rgba(2,132,199,0.35)] transition-all hover:brightness-105"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
