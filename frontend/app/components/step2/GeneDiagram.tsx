import RegionButton from './RegionButton';
import type { DiseaseDetail, Region } from './types';

interface GeneDiagramProps {
  gene: DiseaseDetail['gene'];
  diagramRegions: Region[];
  selectedRegion: Region | null;
  hasSNV: (regionId: string) => boolean;
  hasEdits: (regionId: string) => boolean;
  onRegionClick: (region: Region) => void;
}

export default function GeneDiagram({
  gene,
  diagramRegions,
  selectedRegion,
  hasSNV,
  hasEdits,
  onRegionClick,
}: GeneDiagramProps) {
  return (
    <div className="relative mb-8 pr-3">
      <img
        src="/images/DNA_UI.png"
        alt="DNA UI"
        className="pointer-events-none absolute right-22 top-[46%] h-150 w-100 -translate-y-1/2 object-contain drop-shadow-[0_18px_18px_rgba(15,23,42,0.22)] [-webkit-mask-image:linear-gradient(to_right,transparent_0%,transparent_14%,rgba(0,0,0,0.28)_30%,black_50%,black_82%,rgba(0,0,0,0.35)_92%,transparent_100%)] [mask-image:linear-gradient(to_right,transparent_0%,transparent_14%,rgba(0,0,0,0.28)_30%,black_50%,black_82%,rgba(0,0,0,0.35)_92%,transparent_100%)]"
      />
      <div className="mb-4 flex items-center gap-4">
        <p className="w-36 whitespace-nowrap text-sm font-semibold text-slate-900">{gene.gene_symbol} (정상)</p>
        <div className="flex items-center gap-1">
          {diagramRegions.map((region) => (
            <div key={`normal-${region.region_id}`} className="flex items-center">
              {region.region_type === 'exon' ? (
                <div className="min-w-28 rounded-xl border border-white/16 bg-white/5 px-8 py-3 text-center shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm">
                  <span className="text-sm font-semibold text-slate-950">Exon{region.region_number}</span>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <div className="h-1 w-32 rounded-full bg-white/85"></div>
                  <span className="mt-1 text-xs text-slate-700">Intron{region.region_number}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-8 flex items-center gap-4">
        <p className="w-36 whitespace-nowrap text-sm font-semibold text-rose-800">{gene.gene_symbol} (편집 가능)</p>
        <div className="flex items-center gap-1">
          {diagramRegions.map((region) => (
            <div key={`mutant-${region.region_id}`} className="flex items-center">
              <RegionButton
                region={region}
                isSelected={selectedRegion?.region_id === region.region_id}
                hasSNV={hasSNV(region.region_id)}
                hasEdits={hasEdits(region.region_id)}
                onRegionClick={onRegionClick}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
