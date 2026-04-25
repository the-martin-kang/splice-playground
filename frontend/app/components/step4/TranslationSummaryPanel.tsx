import { formatPercent } from './step4Formatters';
import { progressCardClasses } from './step4Transforms';
import type { JobProgress, SequenceComparison, Step4StateResponse, TranslationSanity } from './types';
import type { MolstarStructureInput } from '../molstar/MolstarViewer';

interface TranslationSummaryPanelProps {
  translation: TranslationSanity;
  comparison: SequenceComparison;
  structureSimilarityScore: number | null;
  progress: JobProgress | null;
  jobMessage: string | null;
  jobError: string | null;
  step4Data: Step4StateResponse;
  userViewerTarget: MolstarStructureInput | null;
  isSubmittingJob: boolean;
  onRefresh: () => void;
  onCreateStructureJob: () => void;
}

export default function TranslationSummaryPanel({
  translation,
  comparison,
  structureSimilarityScore,
  progress,
  jobMessage,
  jobError,
  step4Data,
  userViewerTarget,
  isSubmittingJob,
  onRefresh,
  onCreateStructureJob,
}: TranslationSummaryPanelProps) {
  return (
    <section className="rounded-[24px] border border-white/18 bg-white/5 p-5 shadow-[0_24px_70px_rgba(15,23,42,0.10)] backdrop-blur-lg xl:max-h-[calc(100vh-6rem)] xl:overflow-y-auto">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-black text-slate-950">Translation Summary</h2>
          <p className="mt-2 text-sm text-slate-800">STEP4 API의 `translation_sanity`, job status, 구조 비교 결과를 함께 요약합니다.</p>
        </div>
        <button
          onClick={onRefresh}
          className="rounded-[14px] border border-black/10 bg-white/10 px-4 py-2 text-sm font-semibold text-slate-800 transition hover:bg-white/12"
        >
          Refresh
        </button>
      </div>

      {progress ? (
        <div className={`mt-5 rounded-2xl border px-4 py-4 ${progressCardClasses(progress.tone)}`}>
          <div className="flex items-start gap-3">
            {progress.spinning ? <div className="mt-0.5 h-5 w-5 animate-spin rounded-full border-2 border-current/25 border-b-current" /> : null}
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{progress.title}</p>
              <p className="mt-2 text-sm leading-6">{progress.body}</p>
              {progress.meta ? <p className="mt-2 text-xs opacity-80">{progress.meta}</p> : null}
            </div>
          </div>
        </div>
      ) : null}

      <div className="mt-5 space-y-3 text-sm text-slate-800">
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>Translation OK</span><span className="font-semibold">{translation.translation_ok ? 'Yes' : 'No'}</span></div>
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>Frameshift Likely</span><span className="font-semibold">{translation.frameshift_likely ? 'Yes' : 'No'}</span></div>
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>Premature Stop</span><span className="font-semibold">{translation.premature_stop_likely ? 'Yes' : 'No'}</span></div>
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>First AA Mismatch</span><span className="font-semibold">{comparison.first_mismatch_aa_1 ?? '-'}</span></div>
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>CDS Length</span><span className="font-semibold">{translation.cds_length_nt ?? '-'} nt</span></div>
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>AA Similarity</span><span className="font-semibold">{formatPercent(comparison.normalized_edit_similarity)}</span></div>
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>3D Similarity Score</span><span className="font-semibold">{formatPercent(structureSimilarityScore)}</span></div>
      </div>

      {(jobMessage || jobError) && (
        <div className="mt-5 space-y-3">
          {jobMessage ? <div className="rounded-2xl border border-emerald-300/25 bg-emerald-100/10 px-4 py-3 text-sm text-emerald-900">{jobMessage}</div> : null}
          {jobError ? <div className="rounded-2xl border border-rose-300/25 bg-rose-100/10 px-4 py-3 text-sm text-rose-900">{jobError}</div> : null}
        </div>
      )}

      {step4Data.user_track.recommended_structure_strategy === 'predict_user_structure' && !userViewerTarget ? (
        <div className="mt-5">
          <button
            onClick={onCreateStructureJob}
            disabled={isSubmittingJob}
            className="w-full rounded-full border border-cyan-300/60 bg-[linear-gradient(135deg,rgba(14,165,233,0.95),rgba(37,99,235,0.92))] px-6 py-3 text-sm font-bold text-white shadow-[0_18px_45px_rgba(2,132,199,0.35)] transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmittingJob ? 'Predicting Structure...' : 'Run User Structure Prediction'}
          </button>
        </div>
      ) : null}
    </section>
  );
}
