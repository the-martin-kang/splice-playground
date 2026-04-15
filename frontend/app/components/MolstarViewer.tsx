'use client';

import { useMemo, useState } from 'react';

type MolstarFormat = 'mmcif' | 'bcif' | 'pdb' | string;

interface MolstarViewerProps {
  structureUrl: string | null;
  structureFormat?: MolstarFormat | null;
  structureLabel?: string | null;
}

const MOLSTAR_VIEWER_PAGE = '/vendor/molstar/index.html';

function normalizeFormat(format?: MolstarFormat | null) {
  if (!format) return 'mmcif';
  if (format === 'cif') return 'mmcif';
  return format;
}

function buildViewerSrc(structureUrl: string | null, structureFormat?: MolstarFormat | null) {
  if (!structureUrl) return null;
  const params = new URLSearchParams({
    'hide-controls': '1',
    'collapse-left-panel': '1',
    'pdb-provider': 'pdbe',
    'emdb-provider': 'pdbe',
    'show-toggle-fullscreen': '0',
    'structure-url': structureUrl,
    'structure-url-format': normalizeFormat(structureFormat),
  });
  return `${MOLSTAR_VIEWER_PAGE}?${params.toString()}`;
}

export default function MolstarViewer({
  structureUrl,
  structureFormat,
  structureLabel,
}: MolstarViewerProps) {
  const [loaded, setLoaded] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const viewerSrc = useMemo(() => buildViewerSrc(structureUrl, structureFormat), [structureUrl, structureFormat]);

  if (!viewerSrc) {
    return (
      <div className="flex h-[520px] items-center justify-center rounded-[20px] border border-dashed border-white/14 bg-white/4 px-6 text-center text-slate-800 backdrop-blur-sm">
        표시할 구조 파일 URL이 아직 없습니다.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[20px] border border-white/14 bg-slate-950/12 shadow-[0_22px_70px_rgba(15,23,42,0.12)]">
      <div className="relative h-[520px] w-full bg-slate-950/20">
        {!loaded && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/30 text-sm font-semibold text-slate-100 backdrop-blur-sm">
            단백질 구조를 불러오는 중...
          </div>
        )}
        <iframe
          key={viewerSrc}
          title={structureLabel || 'Protein Structure'}
          src={viewerSrc}
          className="h-full w-full border-0"
          loading="lazy"
          referrerPolicy="no-referrer"
          allowFullScreen
          onLoad={() => {
            setLoaded(true);
            setViewerError(null);
          }}
          onError={() => {
            setLoaded(true);
            setViewerError('Mol* viewer를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.');
          }}
        />
      </div>
      {viewerError && (
        <div className="border-t border-white/10 bg-rose-500/10 px-4 py-3 text-sm text-rose-900">
          {viewerError}
        </div>
      )}
    </div>
  );
}
