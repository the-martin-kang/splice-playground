import { formatPercent } from './step4Formatters';
import type { SequenceComparison } from './types';

interface ProteinMetricCardsProps {
  comparison: SequenceComparison;
  structureSimilarityScore: number | null;
}

export default function ProteinMetricCards({ comparison, structureSimilarityScore }: ProteinMetricCardsProps) {
  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <div className="rounded-[18px] border border-white/16 bg-white/5 p-5 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
        <p className="text-xs uppercase tracking-[0.24em] text-slate-600">Normal Protein</p>
        <p className="mt-3 text-3xl font-black text-slate-950">{comparison.normal_protein_length}<span className="ml-2 text-sm font-semibold text-slate-600">aa</span></p>
      </div>
      <div className="rounded-[18px] border border-white/16 bg-white/5 p-5 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
        <p className="text-xs uppercase tracking-[0.24em] text-slate-600">User Protein</p>
        <p className="mt-3 text-3xl font-black text-slate-950">{comparison.user_protein_length}<span className="ml-2 text-sm font-semibold text-slate-600">aa</span></p>
      </div>
      <div className="rounded-[18px] border border-white/16 bg-white/5 p-5 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
        <p className="text-xs uppercase tracking-[0.24em] text-slate-600">Length Delta</p>
        <p className="mt-3 text-3xl font-black text-slate-950">{comparison.length_delta_aa > 0 ? '+' : ''}{comparison.length_delta_aa}<span className="ml-2 text-sm font-semibold text-slate-600">aa</span></p>
      </div>
      <div className="rounded-[18px] border border-white/16 bg-white/5 p-5 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
        <p className="text-xs uppercase tracking-[0.24em] text-slate-600">Structure Similarity</p>
        <p className="mt-3 text-3xl font-black text-slate-950">{formatPercent(structureSimilarityScore)}</p>
        <p className="mt-2 text-xs text-slate-600">3D 정렬 score max 기준 · AA 유사도 {formatPercent(comparison.normalized_edit_similarity)}</p>
      </div>
    </section>
  );
}
