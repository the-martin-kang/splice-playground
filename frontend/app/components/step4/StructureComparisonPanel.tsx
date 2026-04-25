import { formatNumber } from './step4Formatters';
import type { Step4StructureComparison } from './types';

interface StructureComparisonPanelProps {
  structureComparison: Step4StructureComparison | null;
  structureScoreLabel: string;
}

export default function StructureComparisonPanel({
  structureComparison,
  structureScoreLabel,
}: StructureComparisonPanelProps) {
  if (!structureComparison) return null;

  return (
    <section className="rounded-[24px] border border-white/18 bg-white/5 p-5 shadow-[0_24px_70px_rgba(15,23,42,0.10)] backdrop-blur-lg">
      <h2 className="text-xl font-black text-slate-950">Structure Comparison (3D)</h2>
      {structureComparison?.method ? <div className="mb-3 rounded-xl border border-white/12 bg-white/5 px-4 py-3 text-xs text-slate-700">Method: {structureComparison.method}</div> : null}
      <div className="mt-4 space-y-3 text-sm text-slate-800">
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>{structureScoreLabel} 1</span><span className="font-semibold">{formatNumber(structureComparison.tm_score_1, 3)}</span></div>
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>{structureScoreLabel} 2</span><span className="font-semibold">{formatNumber(structureComparison.tm_score_2, 3)}</span></div>
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>RMSD</span><span className="font-semibold">{formatNumber(structureComparison.rmsd, 3)}</span></div>
        <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>Aligned Length</span><span className="font-semibold">{structureComparison.aligned_length ?? '-'}</span></div>
      </div>
    </section>
  );
}
