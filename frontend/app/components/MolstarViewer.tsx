'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

type MolstarFormat = 'mmcif' | 'bcif' | 'pdb' | string;

export interface MolstarStructureInput {
  url: string | null;
  format?: MolstarFormat | null;
  label?: string | null;
  chainId?: string | null;
  color?: number;
}

export interface MolstarComputedComparison {
  method: 'tm-align' | 'sequence-align' | 'identical-reuse' | 'unavailable';
  tm_score_1?: number | null;
  tm_score_2?: number | null;
  rmsd?: number | null;
  aligned_length?: number | null;
  note?: string | null;
}

interface MolstarViewerProps {
  primary: MolstarStructureInput | null;
  secondary?: MolstarStructureInput | null;
  mode?: 'single' | 'overlay';
  onComputedComparison?: (comparison: MolstarComputedComparison | null) => void;
}

function formatViewerError(error: unknown) {
  if (error instanceof Error) return error.message;
  return 'Mol* viewer를 초기화할 수 없습니다.';
}

const MOLSTAR_STYLE_ID = 'molstar-viewer-style';
const MOLSTAR_STYLE_HREF = '/vendor/molstar/molstar.css';
const DEFAULT_PRIMARY_COLOR = 0x22c55e;
const DEFAULT_SECONDARY_COLOR = 0xef4444;
const VIEWER_HEIGHT_CLASS = 'h-[560px]';
const USE_IFRAME_OVERLAY = process.env.NODE_ENV === 'production';

function isBinaryFormat(format?: MolstarFormat | null) {
  return (format || 'mmcif') === 'bcif';
}

function buildIframeViewerUrl(input: MolstarStructureInput) {
  const format = (input.format || 'mmcif').toLowerCase();
  const params = new URLSearchParams({
    'hide-controls': '1',
    'collapse-left-panel': '1',
    'show-toggle-fullscreen': '0',
    'structure-url': input.url || '',
    'structure-url-format': format,
  });

  if (isBinaryFormat(input.format)) {
    params.set('structure-url-is-binary', '1');
  }

  return `/vendor/molstar/index.html?${params.toString()}`;
}

function hashSignature(value: string) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function buildOverlayIframeViewerUrl(
  primary: MolstarStructureInput,
  secondary: MolstarStructureInput,
  signature: string
) {
  const params = new URLSearchParams({
    'hide-controls': '1',
    'collapse-left-panel': '1',
    'show-toggle-fullscreen': '0',
    'primary-url': primary.url || '',
    'primary-format': (primary.format || 'mmcif').toLowerCase(),
    'primary-label': primary.label || 'Normal Structure',
    'primary-chain': primary.chainId || '',
    'primary-color': String(primary.color ?? DEFAULT_PRIMARY_COLOR),
    'secondary-url': secondary.url || '',
    'secondary-format': (secondary.format || 'mmcif').toLowerCase(),
    'secondary-label': secondary.label || 'User Structure',
    'secondary-chain': secondary.chainId || '',
    'secondary-color': String(secondary.color ?? DEFAULT_SECONDARY_COLOR),
    signature,
  });

  if (isBinaryFormat(primary.format)) params.set('primary-is-binary', '1');
  if (isBinaryFormat(secondary.format)) params.set('secondary-is-binary', '1');

  return `/vendor/molstar/overlay.html?${params.toString()}`;
}

async function ensureMolstarStyle() {
  if (typeof window === 'undefined') return;
  if (document.getElementById(MOLSTAR_STYLE_ID)) return;

  const link = document.createElement('link');
  link.id = MOLSTAR_STYLE_ID;
  link.rel = 'stylesheet';
  link.href = MOLSTAR_STYLE_HREF;
  document.head.appendChild(link);
}

async function importMolstarModules() {
  const [
    pluginUi,
    spec,
    assets,
    color,
    structure,
    builder,
    compiler,
    transforms,
    tmAlignModule,
    react18,
  ] = await Promise.all([
    import('molstar/lib/mol-plugin-ui/index.js'),
    import('molstar/lib/mol-plugin-ui/spec.js'),
    import('molstar/lib/mol-util/assets.js'),
    import('molstar/lib/mol-util/color/index.js'),
    import('molstar/lib/mol-model/structure.js'),
    import('molstar/lib/mol-script/language/builder.js'),
    import('molstar/lib/mol-script/runtime/query/compiler.js'),
    import('molstar/lib/mol-plugin-state/transforms.js'),
    import('molstar/lib/mol-model/structure/structure/util/tm-align.js'),
    import('molstar/lib/mol-plugin-ui/react18.js'),
  ]);

  return {
    createPluginUI: pluginUi.createPluginUI,
    renderReact18: react18.renderReact18,
    DefaultPluginUISpec: spec.DefaultPluginUISpec,
    Asset: assets.Asset,
    Color: color.Color,
    QueryContext: structure.QueryContext,
    StructureSelection: structure.StructureSelection,
    StructureElement: structure.StructureElement,
    MolScriptBuilder: builder.MolScriptBuilder,
    compile: compiler.compile,
    StateTransforms: transforms.StateTransforms,
    tmAlign: tmAlignModule.tmAlign,
  };
}

function createExpression(MS: any, chainId?: string | null, atomName?: string | null) {
  const params: Record<string, unknown> = {};
  if (chainId) {
    params['chain-test'] = MS.core.rel.eq([
      MS.struct.atomProperty.macromolecular.auth_asym_id(),
      chainId,
    ]);
  }
  if (atomName) {
    params['atom-test'] = MS.core.rel.eq([
      MS.struct.atomProperty.macromolecular.label_atom_id(),
      atomName,
    ]);
  }
  return MS.struct.generator.atomGroups(params);
}

async function loadStructure(
  plugin: any,
  modules: Awaited<ReturnType<typeof importMolstarModules>>,
  input: MolstarStructureInput
) {
  const format = (input.format || 'mmcif') as MolstarFormat;
  const isBinary = format === 'bcif';
  if (!input.url) throw new Error('구조 URL이 없습니다.');
  const data = await plugin.builders.data.download(
    { url: modules.Asset.Url(input.url), isBinary, label: input.label || undefined },
    { state: { isGhost: true } }
  );
  const trajectory = await plugin.builders.structure.parseTrajectory(data, format);
  const model = await plugin.builders.structure.createModel(trajectory);
  const structure = await plugin.builders.structure.createStructure(model);
  return { data, trajectory, model, structure };
}

async function addCartoonRepresentation(
  plugin: any,
  modules: Awaited<ReturnType<typeof importMolstarModules>>,
  structureCell: any,
  input: MolstarStructureInput,
  fallbackLabel: string,
  fallbackColor: number
) {
  const expression = createExpression(modules.MolScriptBuilder, input.chainId || undefined, null);
  const component = await plugin.builders.structure.tryCreateComponentFromExpression(
    structureCell,
    expression,
    input.label || fallbackLabel
  );

  const colorValue = modules.Color(input.color ?? fallbackColor);
  const target = component || structureCell;

  await plugin.builders.structure.representation.addRepresentation(target, {
    type: 'cartoon',
    color: 'uniform',
    colorParams: { value: colorValue },
  });

  return target;
}

function tryCreateCaLoci(
  modules: Awaited<ReturnType<typeof importMolstarModules>>,
  structureCell: any,
  chainId?: string | null
) {
  const data = structureCell?.cell?.obj?.data ?? structureCell?.obj?.data;
  if (!data) return null;

  const attempt = (candidateChain?: string | null) => {
    const query = modules.compile(createExpression(modules.MolScriptBuilder, candidateChain, 'CA'));
    const selection = query(new modules.QueryContext(data));
    const loci = modules.StructureSelection.toLociWithCurrentUnits(selection);
    return modules.StructureElement.Loci.size(loci) > 0 ? loci : null;
  };

  return attempt(chainId) || attempt(null);
}

async function applyTransform(
  plugin: any,
  modules: Awaited<ReturnType<typeof importMolstarModules>>,
  structureCell: any,
  matrix: any
) {
  const update = plugin.state.data
    .build()
    .to(structureCell)
    .insert(modules.StateTransforms.Model.TransformStructureConformation, {
      transform: { name: 'matrix', params: { data: matrix, transpose: false } },
    });
  await plugin.runTask(plugin.state.data.updateTree(update));
}

function buildSignature(
  mode: 'single' | 'overlay',
  primary: MolstarStructureInput | null,
  secondary?: MolstarStructureInput | null
) {
  return JSON.stringify({
    mode,
    primary: primary
      ? {
          url: primary.url,
          format: primary.format,
          label: primary.label,
          chainId: primary.chainId,
          color: primary.color,
        }
      : null,
    secondary: secondary
      ? {
          url: secondary.url,
          format: secondary.format,
          label: secondary.label,
          chainId: secondary.chainId,
          color: secondary.color,
        }
      : null,
  });
}

export default function MolstarViewer({
  primary,
  secondary,
  mode = 'single',
  onComputedComparison,
}: MolstarViewerProps) {
  const overlayHostRef = useRef<HTMLDivElement | null>(null);
  const pluginRef = useRef<any>(null);
  const signatureRef = useRef<string>('');
  const comparisonCallbackRef = useRef<typeof onComputedComparison>(onComputedComparison);
  const [viewerError, setViewerError] = useState<string | null>(null);

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
    comparisonCallbackRef.current = onComputedComparison;
  }, [onComputedComparison]);

  useEffect(() => {
    if (mode === 'single' || USE_IFRAME_OVERLAY) {
      pluginRef.current?.dispose?.();
      pluginRef.current = null;
      signatureRef.current = buildSignature(mode, primary, secondary);
      setViewerError(null);
      comparisonCallbackRef.current?.(null);
      if (overlayHostRef.current) overlayHostRef.current.replaceChildren();
      return;
    }

    if (!overlayHostRef.current || !primary?.url || !secondary?.url) return;

    let disposed = false;

    const loadViewer = async () => {
      try {
        setViewerError(null);
        await ensureMolstarStyle();
        const modules = await importMolstarModules();
        if (disposed || !overlayHostRef.current) return;

        const nextSignature = buildSignature(mode, primary, secondary);
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
  ]);

  useEffect(() => {
    if (mode !== 'overlay' || !USE_IFRAME_OVERLAY) return;

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
  }, [mode, overlaySignature]);

  useEffect(() => {
    return () => {
      pluginRef.current?.dispose?.();
      pluginRef.current = null;
      if (overlayHostRef.current) overlayHostRef.current.replaceChildren();
    };
  }, []);

  if (!primary?.url) {
    return (
      <div className={`flex ${VIEWER_HEIGHT_CLASS} items-center justify-center rounded-[20px] border border-dashed border-white/14 bg-white/4 px-6 text-center text-slate-800 backdrop-blur-sm`}>
        표시할 구조 파일 URL이 아직 없습니다.
      </div>
    );
  }

  if (mode === 'single') {
    const iframeSrc = buildIframeViewerUrl(primary);
    return (
      <div className={`overflow-hidden rounded-[20px] border border-white/14 bg-slate-950/12 shadow-[0_22px_70px_rgba(15,23,42,0.12)] ${VIEWER_HEIGHT_CLASS}`}>
        <iframe
          key={iframeSrc}
          title={primary.label || 'Protein Structure'}
          src={iframeSrc}
          className="h-full w-full border-0"
          loading="eager"
          allow="fullscreen"
        />
      </div>
    );
  }

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
