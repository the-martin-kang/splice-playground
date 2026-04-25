'use client';

import { useEffect, useRef, useState } from 'react';
import {
  addCartoonRepresentation,
  applyTransform,
  loadStructure,
  tryCreateCaLoci,
} from './molstarAlignment';
import { ensureMolstarStyle, importMolstarModules } from './molstarLoader';
import { buildOverlayIframeViewerUrl, buildSignature } from './molstarUrls';
import {
  DEFAULT_PRIMARY_COLOR,
  DEFAULT_SECONDARY_COLOR,
  USE_IFRAME_OVERLAY,
  VIEWER_HEIGHT_CLASS,
  type MolstarComputedComparison,
  type MolstarStructureInput,
} from './types';

interface MolstarOverlayViewerProps {
  primary: MolstarStructureInput;
  secondary?: MolstarStructureInput | null;
  overlaySignature: string;
  onComputedComparison?: (comparison: MolstarComputedComparison | null) => void;
}

function formatViewerError(error: unknown) {
  if (error instanceof Error) return error.message;
  return 'Mol* viewer를 초기화할 수 없습니다.';
}

export default function MolstarOverlayViewer({
  primary,
  secondary,
  overlaySignature,
  onComputedComparison,
}: MolstarOverlayViewerProps) {
  // LOGIC: Mol* plugin lifecycle, overlay signature tracking, comparison callback, and viewer error state.
  const overlayHostRef = useRef<HTMLDivElement | null>(null);
  const pluginRef = useRef<any>(null);
  const signatureRef = useRef<string>('');
  const comparisonCallbackRef = useRef<typeof onComputedComparison>(onComputedComparison);
  const [viewerError, setViewerError] = useState<string | null>(null);

  useEffect(() => {
    comparisonCallbackRef.current = onComputedComparison;
  }, [onComputedComparison]);

  useEffect(() => {
    if (!USE_IFRAME_OVERLAY) return;
    pluginRef.current?.dispose?.();
    pluginRef.current = null;
    signatureRef.current = buildSignature('overlay', primary, secondary);
    setViewerError(null);
    comparisonCallbackRef.current?.(null);
    if (overlayHostRef.current) overlayHostRef.current.replaceChildren();
  }, [
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
  ]);

  // LOGIC: development overlay path. Loads Mol* directly, aligns structures, and reports comparison metrics.
  useEffect(() => {
    if (USE_IFRAME_OVERLAY) return;
    if (!overlayHostRef.current || !primary?.url || !secondary?.url) return;

    let disposed = false;

    const loadViewer = async () => {
      try {
        setViewerError(null);
        await ensureMolstarStyle();
        const modules = await importMolstarModules();
        if (disposed || !overlayHostRef.current) return;

        const nextSignature = buildSignature('overlay', primary, secondary);
        if (pluginRef.current && signatureRef.current === nextSignature) {
          return;
        }

        pluginRef.current?.dispose?.();
        pluginRef.current = null;

        const mountTarget = document.createElement('div');
        mountTarget.className = 'h-full w-full';
        overlayHostRef.current.replaceChildren(mountTarget);
        signatureRef.current = nextSignature;

        const plugin = await modules.createPluginUI({
          target: mountTarget,
          render: modules.renderReact18,
          spec: {
            ...modules.DefaultPluginUISpec(),
            layout: {
              initial: {
                isExpanded: false,
                showControls: false,
                regionState: {
                  top: 'hidden',
                  bottom: 'hidden',
                  left: 'hidden',
                  right: 'hidden',
                },
              },
            },
            components: {
              remoteState: 'none',
              controls: {
                top: 'none',
                bottom: 'none',
                left: 'none',
                right: 'none',
              },
            },
          },
        });

        if (disposed) {
          plugin.dispose?.();
          return;
        }

        pluginRef.current = plugin;

        await plugin.clear();

        const primaryLoaded = await loadStructure(plugin, modules, primary);
        const secondaryLoaded = await loadStructure(plugin, modules, secondary);

        const primaryLoci = tryCreateCaLoci(modules, primaryLoaded.structure, primary.chainId);
        const secondaryLoci = tryCreateCaLoci(modules, secondaryLoaded.structure, secondary.chainId);

        let comparison: MolstarComputedComparison | null = null;
        if (primaryLoci && secondaryLoci) {
          const result = modules.tmAlign(primaryLoci, secondaryLoci);
          await applyTransform(plugin, modules, secondaryLoaded.structure, result.bTransform);
          comparison = {
            method: 'tm-align',
            tm_score_1: result.tmScoreA,
            tm_score_2: result.tmScoreB,
            rmsd: result.rmsd,
            aligned_length: result.alignedLength,
            note: 'frontend TM-align overlay',
          };
        } else {
          comparison = {
            method: 'unavailable',
            note: 'C-alpha selection을 만들지 못해 overlay alignment를 생략했습니다.',
          };
        }

        await addCartoonRepresentation(
          plugin,
          modules,
          primaryLoaded.structure,
          { ...primary, color: primary.color ?? DEFAULT_PRIMARY_COLOR },
          primary.label || 'Normal Structure',
          DEFAULT_PRIMARY_COLOR
        );
        await addCartoonRepresentation(
          plugin,
          modules,
          secondaryLoaded.structure,
          { ...secondary, color: secondary.color ?? DEFAULT_SECONDARY_COLOR },
          secondary.label || 'User Structure',
          DEFAULT_SECONDARY_COLOR
        );

        if (!disposed) comparisonCallbackRef.current?.(comparison);
      } catch (error) {
        if (!disposed) {
          setViewerError(formatViewerError(error));
          comparisonCallbackRef.current?.({
            method: 'unavailable',
            note: 'overlay 비교를 계산하지 못했습니다. baseline 구조만 확인하세요.',
          });
        }
      }
    };

    void loadViewer();

    return () => {
      disposed = true;
    };
  }, [
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
  ]);

  // LOGIC: production iframe overlay path. Receives comparison/error messages from the bundled overlay page.
  useEffect(() => {
    if (!USE_IFRAME_OVERLAY) return;

    const handleMessage = (event: MessageEvent) => {
      const data = event.data as {
        type?: string;
        signature?: string;
        status?: string;
        comparison?: MolstarComputedComparison | null;
        message?: string;
      };

      if (data?.type !== 'splice-playground-molstar-overlay') return;
      if (data.signature !== overlaySignature) return;

      if (data.status === 'comparison') {
        setViewerError(null);
        comparisonCallbackRef.current?.(data.comparison || null);
        return;
      }

      if (data.status === 'error') {
        const message = data.message || 'overlay 비교를 계산하지 못했습니다.';
        setViewerError(message);
        comparisonCallbackRef.current?.({
          method: 'unavailable',
          note: message,
        });
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [overlaySignature]);

  // LOGIC: dispose Mol* plugin and clear DOM host when the component unmounts.
  useEffect(() => {
    return () => {
      pluginRef.current?.dispose?.();
      pluginRef.current = null;
      if (overlayHostRef.current) overlayHostRef.current.replaceChildren();
    };
  }, []);

  const overlayIframeSrc =
    USE_IFRAME_OVERLAY && secondary?.url
      ? buildOverlayIframeViewerUrl(primary, secondary, overlaySignature)
      : null;

  return (
    <div className={`relative overflow-hidden rounded-[20px] border border-white/14 bg-slate-950/12 shadow-[0_22px_70px_rgba(15,23,42,0.12)] ${VIEWER_HEIGHT_CLASS}`}>
      {overlayIframeSrc ? (
        <iframe
          key={overlayIframeSrc}
          title="Protein Overlay Compare"
          src={overlayIframeSrc}
          className="h-full w-full border-0"
          loading="eager"
          allow="fullscreen"
        />
      ) : (
        <div ref={overlayHostRef} className="h-full w-full" />
      )}
      {secondary?.url ? (
        <div className="pointer-events-none absolute left-4 top-4 z-10 flex flex-wrap gap-2 text-xs text-slate-200">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/35 px-3 py-1 backdrop-blur-sm">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#22c55e]" />
            정상 구조
          </span>
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/35 px-3 py-1 backdrop-blur-sm">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#ef4444]" />
            생성 구조
          </span>
        </div>
      ) : null}
      {viewerError && (
        <div className="absolute inset-x-0 bottom-0 z-10 border-t border-white/10 bg-rose-500/10 px-4 py-3 text-sm text-rose-900 backdrop-blur-sm">
          {viewerError}
        </div>
      )}
    </div>
  );
}
