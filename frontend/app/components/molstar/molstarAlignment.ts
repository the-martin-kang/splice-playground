import { importMolstarModules } from './molstarLoader';
import type { MolstarFormat, MolstarStructureInput } from './types';

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

export async function loadStructure(
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

export async function addCartoonRepresentation(
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

export function tryCreateCaLoci(
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

export async function applyTransform(
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
