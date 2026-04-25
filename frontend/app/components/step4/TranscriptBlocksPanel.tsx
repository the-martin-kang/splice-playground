import type { TranscriptBlock } from './types';

interface TranscriptBlocksPanelProps {
  transcriptBlocks: TranscriptBlock[];
  affectedExons: number[];
  excludedExons: number[];
  transcriptHeadline: string | null;
}

export default function TranscriptBlocksPanel({
  transcriptBlocks,
  affectedExons,
  excludedExons,
  transcriptHeadline,
}: TranscriptBlocksPanelProps) {
  const involvedOnlyExons = affectedExons.filter(exonNo => !excludedExons.includes(exonNo));

  return (
    <section className="rounded-[24px] border border-white/18 bg-white/5 p-5 shadow-[0_24px_70px_rgba(15,23,42,0.10)] backdrop-blur-lg">
      <h2 className="text-xl font-black text-slate-950">Transcript Blocks</h2>
      {transcriptHeadline ? (
        <p className="mt-3 rounded-2xl border border-cyan-300/25 bg-cyan-100/10 px-4 py-3 text-sm leading-6 text-slate-900">
          {transcriptHeadline}
        </p>
      ) : null}
      {excludedExons.length > 0 || involvedOnlyExons.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-800">
          {excludedExons.map((exonNo) => (
            <span
              key={`excluded-exon-${exonNo}`}
              className="rounded-full border border-rose-300/35 bg-rose-100/10 px-3 py-1 font-semibold text-rose-900"
            >
              Exon {exonNo} excluded
            </span>
          ))}
          {involvedOnlyExons.map((exonNo) => (
            <span
              key={`involved-exon-${exonNo}`}
              className="rounded-full border border-cyan-300/30 bg-cyan-100/10 px-3 py-1 font-semibold text-cyan-900"
            >
              Exon {exonNo} involved
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-4 flex max-h-[280px] flex-wrap gap-2 overflow-y-auto pr-1">
        {transcriptBlocks.map((block) => {
          const exonNumber = block.canonical_exon_number ?? null;
          const isExcludedCanonical = exonNumber != null && excludedExons.includes(exonNumber);
          const blockClass =
            block.block_kind === 'pseudo_exon'
              ? 'border-amber-300/35 bg-amber-100/10 text-amber-900'
              : block.block_kind === 'boundary_shift'
                ? 'border-cyan-300/30 bg-cyan-100/10 text-cyan-900'
                : isExcludedCanonical
                  ? 'border-rose-300/35 bg-rose-100/10 text-rose-900'
                  : 'border-white/14 bg-white/5 text-slate-800';
          return (
            <div
              key={block.block_id}
              className={`rounded-full border px-3 py-2 text-xs font-semibold ${blockClass}`}
            >
              {block.label} · {block.length} nt
            </div>
          );
        })}
      </div>
    </section>
  );
}
