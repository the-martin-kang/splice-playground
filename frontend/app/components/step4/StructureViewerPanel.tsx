import MolstarViewer, { type MolstarComputedComparison, type MolstarStructureInput } from '../molstar/MolstarViewer';
import PredictionJobCard from './PredictionJobCard';
import StructureViewTabs from './StructureViewTabs';
import type { ActiveStructureView, MolstarTarget, Step4StructureComparison, Step4StructureJob } from './types';

interface StructureViewerPanelProps {
  activeStructureView: ActiveStructureView;
  setActiveStructureView: (view: ActiveStructureView) => void;
  normalViewerTarget: MolstarStructureInput | null;
  userViewerTarget: MolstarStructureInput | null;
  singleDisplayedTarget: MolstarStructureInput | null;
  normalStructureTarget: MolstarTarget | null;
  userStructureTarget: MolstarTarget | null;
  overlaySecondary: MolstarTarget | null;
  structureComparison: Step4StructureComparison | null;
  job: Step4StructureJob | null;
  onComputedComparison: (comparison: MolstarComputedComparison | null) => void;
}

export default function StructureViewerPanel({
  activeStructureView,
  setActiveStructureView,
  normalViewerTarget,
  userViewerTarget,
  singleDisplayedTarget,
  normalStructureTarget,
  userStructureTarget,
  overlaySecondary,
  structureComparison,
  job,
  onComputedComparison,
}: StructureViewerPanelProps) {
  return (
    <div className="rounded-[24px] border border-white/18 bg-white/5 p-5 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-950">Mol* Structure Viewer</h2>
          <p className="mt-1 text-sm text-slate-800">정상 구조는 초록, 생성 구조는 빨강으로 표시하며, overlay 모드에서는 브라우저에서 두 구조를 직접 정렬해 겹쳐 비교합니다.</p>
        </div>
        <StructureViewTabs
          activeStructureView={activeStructureView}
          setActiveStructureView={setActiveStructureView}
          normalViewerTarget={normalViewerTarget}
          userViewerTarget={userViewerTarget}
        />
      </div>

      {activeStructureView === 'overlay' && normalViewerTarget && userViewerTarget ? (
        <MolstarViewer mode="overlay" primary={normalViewerTarget} secondary={userViewerTarget} onComputedComparison={onComputedComparison} />
      ) : (
        <MolstarViewer mode="single" primary={singleDisplayedTarget} onComputedComparison={onComputedComparison} />
      )}

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="rounded-[18px] border border-white/16 bg-white/5 p-4 text-sm text-slate-800">
          <p className="text-xs uppercase tracking-[0.24em] text-slate-600">Displayed Asset</p>
          <p className="mt-2 font-semibold text-slate-950">
            {activeStructureView === 'overlay'
              ? 'Normal + User overlay'
              : singleDisplayedTarget?.label || '구조 자산 없음'}
          </p>
          <p className="mt-2 text-slate-700">
            {activeStructureView === 'overlay'
              ? structureComparison?.method === 'tm-align'
                ? 'TM-align based superposition'
                : structureComparison?.method === 'sequence-align'
                  ? 'C-alpha sequence-aligned superposition'
                  : 'Structure overlay compare'
              : `${activeStructureView === 'user' ? userStructureTarget?.provider || '-' : normalStructureTarget?.provider || '-'} / ${activeStructureView === 'user' ? userStructureTarget?.source_db || '-' : normalStructureTarget?.source_db || '-'}`}
          </p>
          <p className="mt-1 text-slate-700">
            {activeStructureView === 'overlay'
              ? `${normalStructureTarget?.source_id || '-'} vs ${overlaySecondary?.source_id || '-'}`
              : (activeStructureView === 'user' ? userStructureTarget?.source_id : normalStructureTarget?.source_id) || '-'}
            {activeStructureView !== 'overlay' && (activeStructureView === 'user' ? userStructureTarget?.source_chain_id : normalStructureTarget?.source_chain_id)
              ? ` · Chain ${activeStructureView === 'user' ? userStructureTarget?.source_chain_id : normalStructureTarget?.source_chain_id}`
              : ''}
          </p>
        </div>
        <PredictionJobCard job={job} />
      </div>
    </div>
  );
}
