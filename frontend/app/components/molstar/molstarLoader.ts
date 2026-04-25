const MOLSTAR_STYLE_ID = 'molstar-viewer-style';
const MOLSTAR_STYLE_HREF = '/vendor/molstar/molstar.css';

export async function ensureMolstarStyle() {
  if (typeof window === 'undefined') return;
  if (document.getElementById(MOLSTAR_STYLE_ID)) return;

  const link = document.createElement('link');
  link.id = MOLSTAR_STYLE_ID;
  link.rel = 'stylesheet';
  link.href = MOLSTAR_STYLE_HREF;
  document.head.appendChild(link);
}

export async function importMolstarModules() {
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
