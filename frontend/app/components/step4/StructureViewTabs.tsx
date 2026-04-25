import type { ActiveStructureView } from './types';
import type { MolstarStructureInput } from '../molstar/MolstarViewer';

interface StructureViewTabsProps {
  activeStructureView: ActiveStructureView;
  setActiveStructureView: (view: ActiveStructureView) => void;
  normalViewerTarget: MolstarStructureInput | null;
  userViewerTarget: MolstarStructureInput | null;
}

export default function StructureViewTabs({
  activeStructureView,
  setActiveStructureView,
  normalViewerTarget,
  userViewerTarget,
}: StructureViewTabsProps) {
  return (
    <div className="relative z-10 flex flex-wrap gap-2">
      <button
        onClick={() => setActiveStructureView('normal')}
        className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${activeStructureView === 'normal' ? 'border-cyan-300/60 bg-cyan-100/12 text-cyan-900' : 'border-black/10 bg-white/10 text-slate-800 hover:bg-white/12'}`}
      >
        Normal Structure
      </button>
      <button
        onClick={() => setActiveStructureView('user')}
        disabled={!userViewerTarget}
        className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${activeStructureView === 'user' && userViewerTarget ? 'border-cyan-300/60 bg-cyan-100/12 text-cyan-900' : 'border-black/10 bg-white/10 text-slate-800 hover:bg-white/12 disabled:cursor-not-allowed disabled:opacity-40'}`}
      >
        User Structure
      </button>
      <button
        onClick={() => setActiveStructureView('overlay')}
        disabled={!normalViewerTarget || !userViewerTarget}
        className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${activeStructureView === 'overlay' && normalViewerTarget && userViewerTarget ? 'border-fuchsia-300/60 bg-fuchsia-100/12 text-fuchsia-900' : 'border-black/10 bg-white/10 text-slate-800 hover:bg-white/12 disabled:cursor-not-allowed disabled:opacity-40'}`}
      >
        Overlay Compare
      </button>
    </div>
  );
}
