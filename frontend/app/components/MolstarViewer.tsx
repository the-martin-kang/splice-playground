'use client';

import { useEffect, useRef, useState } from 'react';

type MolstarFormat = 'mmcif' | 'bcif' | 'pdb' | string;

interface MolstarViewerProps {
  structureUrl: string | null;
  structureFormat?: MolstarFormat | null;
  structureLabel?: string | null;
}

function formatViewerError(error: unknown) {
  if (error instanceof Error) return error.message;
  return 'Mol* viewer를 초기화할 수 없습니다.';
}

const MOLSTAR_SCRIPT_ID = 'molstar-viewer-script';
const MOLSTAR_STYLE_ID = 'molstar-viewer-style';
const MOLSTAR_SCRIPT_SRC = '/vendor/molstar/molstar.js';
const MOLSTAR_STYLE_HREF = '/vendor/molstar/molstar.css';

type MolstarViewerInstance = {
  dispose: () => void;
  loadStructureFromUrl: (
    url: string,
    format?: string,
    isBinary?: boolean,
    options?: { label?: string }
  ) => Promise<void>;
};

type MolstarGlobal = {
  Viewer: {
    create: (
      elementOrId: string | HTMLElement,
      options?: Record<string, unknown>
    ) => Promise<MolstarViewerInstance>;
  };
};

declare global {
  interface Window {
    molstar?: MolstarGlobal;
  }
}

let molstarAssetsPromise: Promise<MolstarGlobal> | null = null;

function ensureMolstarAssets() {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('Mol* viewer는 브라우저에서만 초기화할 수 있습니다.'));
  }

  if (window.molstar) return Promise.resolve(window.molstar);
  if (molstarAssetsPromise) return molstarAssetsPromise;

  molstarAssetsPromise = new Promise<MolstarGlobal>((resolve, reject) => {
    if (!document.getElementById(MOLSTAR_STYLE_ID)) {
      const link = document.createElement('link');
      link.id = MOLSTAR_STYLE_ID;
      link.rel = 'stylesheet';
      link.href = MOLSTAR_STYLE_HREF;
      document.head.appendChild(link);
    }

    const existingScript = document.getElementById(MOLSTAR_SCRIPT_ID) as HTMLScriptElement | null;

    const handleReady = () => {
      if (window.molstar) {
        resolve(window.molstar);
      } else {
        reject(new Error('Mol* 브라우저 번들을 로드했지만 전역 객체를 찾지 못했습니다.'));
      }
    };

    if (existingScript) {
      if (window.molstar) {
        handleReady();
        return;
      }

      existingScript.addEventListener('load', handleReady, { once: true });
      existingScript.addEventListener(
        'error',
        () => reject(new Error('Mol* 브라우저 번들을 불러올 수 없습니다.')),
        { once: true }
      );
      return;
    }

    const script = document.createElement('script');
    script.id = MOLSTAR_SCRIPT_ID;
    script.src = MOLSTAR_SCRIPT_SRC;
    script.async = true;
    script.onload = handleReady;
    script.onerror = () => reject(new Error('Mol* 브라우저 번들을 불러올 수 없습니다.'));
    document.body.appendChild(script);
  });

  return molstarAssetsPromise;
}

export default function MolstarViewer({
  structureUrl,
  structureFormat,
  structureLabel,
}: MolstarViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [viewerError, setViewerError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current || !structureUrl) return;

    let disposed = false;
    let viewer: MolstarViewerInstance | null = null;

    const loadViewer = async () => {
      try {
        setViewerError(null);
        const molstar = await ensureMolstarAssets();

        if (!containerRef.current || disposed) return;

        containerRef.current.innerHTML = '';

        viewer = await molstar.Viewer.create(containerRef.current, {
          disabledExtensions: ['mp4-export'],
          layoutIsExpanded: true,
          layoutShowControls: false,
          layoutShowRemoteState: false,
          layoutShowSequence: false,
          layoutShowLog: false,
          layoutShowLeftPanel: false,
          collapseLeftPanel: true,
          viewportShowExpand: false,
          viewportShowSelectionMode: false,
          viewportShowAnimation: false,
          viewportShowTrajectoryControls: false,
          pdbProvider: 'pdbe',
          emdbProvider: 'pdbe',
        });

        if (disposed || !viewer) {
          viewer?.dispose();
          return;
        }

        const format = (structureFormat || 'mmcif') as MolstarFormat;
        const isBinary = format === 'bcif';

        await viewer.loadStructureFromUrl(structureUrl, format, isBinary, {
          label: structureLabel || 'Protein Structure',
        });
      } catch (error) {
        if (!disposed) {
          setViewerError(formatViewerError(error));
        }
      }
    };

    loadViewer();

    return () => {
      disposed = true;
      viewer?.dispose();
    };
  }, [structureUrl, structureFormat, structureLabel]);

  if (!structureUrl) {
    return (
      <div className="flex h-[520px] items-center justify-center rounded-[20px] border border-dashed border-white/14 bg-white/4 px-6 text-center text-slate-800 backdrop-blur-sm">
        표시할 구조 파일 URL이 아직 없습니다.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[20px] border border-white/14 bg-slate-950/12 shadow-[0_22px_70px_rgba(15,23,42,0.12)]">
      <div ref={containerRef} className="h-[520px] w-full" />
      {viewerError && (
        <div className="border-t border-white/10 bg-rose-500/10 px-4 py-3 text-sm text-rose-900">
          {viewerError}
        </div>
      )}
    </div>
  );
}
