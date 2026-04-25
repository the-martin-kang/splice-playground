import type { DiseaseDetail } from './types';

interface ChromosomeBadgeProps {
  gene: DiseaseDetail['gene'];
}

export default function ChromosomeBadge({ gene }: ChromosomeBadgeProps) {
  return (
    <div className="absolute right-4 top-10 w-40">
      <div className="flex flex-col items-center">
        <img
          src="/images/choromosome_icon.png"
          alt={`${gene.chromosome} chromosome`}
          className="mb-2 h-36 w-24 object-contain drop-shadow-[0_18px_18px_rgba(15,23,42,0.35)]"
        />
        <div className="flex flex-col items-center gap-1.5">
          <p className="rounded-full border border-white/25 bg-white/15 px-3 py-1 text-center text-xs font-semibold text-slate-950 shadow-[0_10px_24px_rgba(15,23,42,0.10),inset_0_1px_0_rgba(255,255,255,0.35)] backdrop-blur-md">
            {gene.chromosome}
          </p>
          <p className="rounded-full border border-white/22 bg-white/10 px-3 py-1 text-center text-xs font-medium text-slate-800 shadow-[0_8px_20px_rgba(15,23,42,0.08),inset_0_1px_0_rgba(255,255,255,0.30)] backdrop-blur-md">
            {gene.gene_symbol}
          </p>
        </div>
      </div>
    </div>
  );
}
