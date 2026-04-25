import type { Region } from './types';

interface RegionButtonProps {
  region: Region;
  isSelected: boolean;
  hasSNV: boolean;
  hasEdits: boolean;
  onRegionClick: (region: Region) => void;
}

export default function RegionButton({
  region,
  isSelected,
  hasSNV,
  hasEdits,
  onRegionClick,
}: RegionButtonProps) {
  if (region.region_type === 'exon') {
    return (
      <button
        onClick={() => onRegionClick(region)}
        className={`min-w-28 rounded-xl border px-8 py-3 text-center shadow-[0_10px_30px_rgba(15,23,42,0.10)] backdrop-blur-sm transition-all
          ${isSelected
            ? 'border-cyan-300/60 bg-cyan-100/12 ring-2 ring-cyan-300/40'
            : hasSNV
              ? 'border-rose-300/60 bg-rose-100/12'
              : 'border-white/16 bg-white/5 hover:bg-white/8'}
          ${hasEdits ? 'border-amber-300/80' : ''}
        `}
      >
        <span className={`text-sm font-semibold ${hasSNV ? 'text-rose-800' : hasEdits ? 'text-amber-800' : 'text-slate-950'}`}>
          Exon{region.region_number}
        </span>
        {hasSNV && <div className="text-xs text-rose-700">SNV</div>}
        {hasEdits && <div className="text-xs text-amber-700">edited</div>}
      </button>
    );
  }

  return (
    <button
      onClick={() => onRegionClick(region)}
      className={`flex flex-col items-center transition-all ${isSelected ? 'scale-110' : ''}`}
    >
      <div className={`w-32 rounded-full ${isSelected ? 'h-2 bg-cyan-200' : hasSNV ? 'h-1 bg-rose-400' : hasEdits ? 'h-1 bg-amber-400' : 'h-1 bg-slate-600'}`}></div>
      <span className={`mt-1 text-xs ${hasSNV ? 'font-semibold text-rose-700' : hasEdits ? 'text-amber-700' : 'text-slate-700'} ${isSelected ? 'font-semibold text-cyan-700' : ''}`}>
        Intron{region.region_number}
        {hasSNV && ' (SNV)'}
        {hasEdits && ' (edited)'}
      </span>
    </button>
  );
}
