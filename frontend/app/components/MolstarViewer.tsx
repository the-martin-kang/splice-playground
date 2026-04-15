'use client';

import { useEffect, useRef, useState } from 'react';

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
    react18,
    spec,
    assets,
    color,
    structure,
    builder,
    compiler,
    transforms,
    tmAlignModule,
  ] = await Promise.all([
    import('molstar/lib/mol-plugin-ui/index.js'),
    import('molstar/lib/mol-plugin-ui/react18.js'),
    import('molstar/lib/mol-plugin-ui/spec.js'),
    import('molstar/lib/mol-util/assets.js'),
    import('molstar/lib/mol-util/color/index.js'),
    import('molstar/lib/mol-model/structure.js'),
    import('molstar/lib/mol-script/language/builder.js'),
    import('molstar/lib/mol-script/runtime/query/compiler.js'),
    import('molstar/lib/mol-plugin-state/transforms.js'),
    import('molstar/lib/mol-model/structure/structure/util/tm-align.js'),
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

async function loadStructure(plugin: any, modules: Awaited<ReturnType<typeof importMolstarModules>>, input: MolstarStructureInput) {
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

function tryCreateCaLoci(modules: Awaited<ReturnType<typeof importMolstarModules>>, structureCell: any, chainId?: string | null) {
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

async function applyTransform(plugin: any, modules: Awaited<ReturnType<typeof importMolstarModules>>, structureCell: any, matrix: any) {
  const update = plugin.state.data
    .build()
    .to(structureCell)
    .insert(modules.StateTransforms.Model.TransformStructureConformation, {
      transform: { name: 'matrix', params: { data: matrix, transpose: false } },
    });
  await plugin.runTask(plugin.state.data.updateTree(update));
}

export default function MolstarViewer({
  primary,
  secondary,
  mode = 'single',
  onComputedComparison,
}: MolstarViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [viewerError, setViewerError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current || !primary?.url) return;

    let disposed = false;
    let plugin: any = null;

    const loadViewer = async () => {
      try {
        setViewerError(null);
        await ensureMolstarStyle();
        const modules = await importMolstarModules();
        if (disposed || !containerRef.current) return;

        containerRef.current.innerHTML = '';

        plugin = await modules.createPluginUI({
          target: containerRef.current,
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

        await plugin.clear();

        if (mode === 'overlay' && secondary?.url) {
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

          if (!disposed) onComputedComparison?.(comparison);
        } else {
          const loaded = await loadStructure(plugin, modules, primary);
          await addCartoonRepresentation(
            plugin,
            modules,
            loaded.structure,
            { ...primary, color: primary.color ?? DEFAULT_PRIMARY_COLOR },
            primary.label || 'Protein Structure',
            DEFAULT_PRIMARY_COLOR
          );
          if (!disposed) onComputedComparison?.(null);
        }
      } catch (error) {
        if (!disposed) {
          setViewerError(formatViewerError(error));
          onComputedComparison?.(null);
        }
      }
    };

    void loadViewer();

    return () => {
      disposed = true;
      plugin?.dispose?.();
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
    mode,
    onComputedComparison,
  ]);

  if (!primary?.url) {
    return (
      <div className="flex h-[560px] items-center justify-center rounded-[20px] border border-dashed border-white/14 bg-white/4 px-6 text-center text-slate-800 backdrop-blur-sm">
        표시할 구조 파일 URL이 아직 없습니다.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[20px] border border-white/14 bg-slate-950/12 shadow-[0_22px_70px_rgba(15,23,42,0.12)]">
      <div ref={containerRef} className="h-[560px] w-full" />
      {viewerError && (
        <div className="border-t border-white/10 bg-rose-500/10 px-4 py-3 text-sm text-rose-900">
          {viewerError}
        </div>
      )}
      {mode === 'overlay' && secondary?.url ? (
        <div className="flex flex-wrap gap-3 border-t border-white/10 px-4 py-3 text-xs text-slate-200">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#22c55e]" />
            정상 구조
          </span>
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#ef4444]" />
            생성 구조
          </span>
        </div>
      ) : null}
    </div>
  );
}
