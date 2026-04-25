import type { MutantTranscriptBlock } from './types';

interface TranscriptTrackProps {
  geneSymbol: string;
  normalExons: number[];
  mutantTranscriptBlocks: MutantTranscriptBlock[];
}

export default function TranscriptTrack({
  geneSymbol,
  normalExons,
  mutantTranscriptBlocks,
}: TranscriptTrackProps) {
  return (
    <>
      {/* (2) 정상 mRNA */}
      <div className="mb-12">
        <p className="mb-4 text-xl font-bold text-slate-950">{geneSymbol} (정상)</p>
        <div className="flex items-center gap-1 flex-wrap">
          {normalExons.map((exonNum) => (
            <div 
              key={`normal-${exonNum}`}
              className="min-w-16 rounded-xl border border-white/8 bg-white/[0.03] px-4 py-2 text-center shadow-none backdrop-blur-sm transition-colors hover:border-white/16 hover:bg-white/8"
            >
              <span className="text-sm font-semibold text-slate-950">Exon{exonNum}</span>
            </div>
          ))}
        </div>
      </div>

      {/* (3) 비정상 mRNA */}
      <div className="mb-12">
        <p className="mb-4 text-xl font-bold italic text-rose-800">{geneSymbol} (비정상)</p>
        <div className="relative">
          <div className="flex items-center gap-1 flex-wrap">
            {mutantTranscriptBlocks.map((block) => {
              if (block.kind === 'pseudo_exon') {
                return (
                  <div
                    key={block.key}
                    className="relative flex min-w-16 flex-col items-center"
                  >
                    <div className="min-w-16 animate-bounce rounded-xl border border-amber-400/75 bg-amber-100/20 px-4 py-2 text-center shadow-[0_12px_32px_rgba(245,158,11,0.18)] ring-1 ring-amber-300/45 backdrop-blur-sm transition-colors hover:bg-amber-100/28">
                      <span className="text-sm font-semibold text-amber-900">{block.label}</span>
                    </div>
                    <div className="pointer-events-none absolute left-1/2 top-full h-24 w-px -translate-x-1/2 bg-amber-300/60"></div>
                  </div>
                );
              }

              if (block.state === 'excluded') {
                return (
                  <div key={block.key} className="relative flex min-w-16 flex-col items-center">
                    <div className="min-w-16 animate-bounce rounded-xl border border-dashed border-rose-300/55 bg-rose-100/14 px-4 py-2 text-center opacity-80 shadow-[0_8px_24px_rgba(225,29,72,0.10)] backdrop-blur-sm transition-colors hover:bg-rose-100/20">
                      <span className="text-sm font-semibold text-rose-800 line-through">{block.label}</span>
                    </div>
                    <div className="pointer-events-none absolute left-1/2 top-full h-24 -translate-x-1/2 border-l border-dashed border-rose-300/60"></div>
                  </div>
                );
              }

              if (block.state === 'shifted') {
                return (
                  <div
                    key={block.key}
                    className="relative flex min-w-16 flex-col items-center"
                  >
                    <div className="min-w-16 animate-bounce rounded-xl border border-cyan-300/55 bg-cyan-100/14 px-4 py-2 text-center shadow-[0_8px_24px_rgba(8,145,178,0.10)] backdrop-blur-sm transition-colors hover:bg-cyan-100/20">
                      <span className="text-sm font-semibold text-cyan-900">{block.label}</span>
                    </div>
                    <div className="pointer-events-none absolute left-1/2 top-full h-24 w-px -translate-x-1/2 bg-cyan-300/60"></div>
                  </div>
                );
              }

              return (
                <div
                  key={block.key}
                  className="min-w-16 rounded-xl border border-white/8 bg-white/[0.03] px-4 py-2 text-center shadow-none backdrop-blur-sm transition-colors hover:border-white/16 hover:bg-white/8"
                >
                  <span className="text-sm font-semibold text-slate-950">{block.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
}
