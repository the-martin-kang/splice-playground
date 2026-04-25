'use client';

import { useEffect, useMemo } from 'react';
import MolstarIframeViewer from './MolstarIframeViewer';
import MolstarOverlayViewer from './MolstarOverlayViewer';
import { buildSignature, hashSignature } from './molstarUrls';
import {
  VIEWER_HEIGHT_CLASS,
  type MolstarComputedComparison,
  type MolstarStructureInput,
  type MolstarViewerProps,
} from './types';

export type { MolstarComputedComparison, MolstarStructureInput };

export default function MolstarViewer({
  primary,
  secondary,
  mode = 'single',
  onComputedComparison,
}: MolstarViewerProps) {
  // LOGIC: stable signature for iframe overlay messages and reload keys.
  const overlaySignature = useMemo(
    () => hashSignature(buildSignature(mode, primary, secondary)),
    [
      mode,
      primary?.url,
      primary?.format,
      primary?.label,
      primary?.chainId,
      primary?.color,
      secondary?.url,
      secondary?.format,
      secondary?.label,
      secondary?.chainId,
      secondary?.color,
    ]
  );

  useEffect(() => {
    if (mode === 'single') onComputedComparison?.(null);
  }, [
    mode,
    primary?.url,
    primary?.format,
    primary?.label,
    primary?.chainId,
    primary?.color,
    onComputedComparison,
  ]);

  // UI: empty state when no structure URL is available.
  if (!primary?.url) {
    return (
      <div className={`flex ${VIEWER_HEIGHT_CLASS} items-center justify-center rounded-[20px] border border-dashed border-white/14 bg-white/4 px-6 text-center text-slate-800 backdrop-blur-sm`}>
        표시할 구조 파일 URL이 아직 없습니다.
      </div>
    );
  }

  // UI: single-structure iframe viewer.
  if (mode === 'single') {
    return <MolstarIframeViewer primary={primary} />;
  }

  // UI: overlay viewer, legend, and viewer error banner.
  return (
    <MolstarOverlayViewer
      primary={primary}
      secondary={secondary}
      overlaySignature={overlaySignature}
      onComputedComparison={onComputedComparison}
    />
  );
}
