import {
  DEFAULT_PRIMARY_COLOR,
  DEFAULT_SECONDARY_COLOR,
  type MolstarFormat,
  type MolstarStructureInput,
} from './types';

function isBinaryFormat(format?: MolstarFormat | null) {
  return (format || 'mmcif') === 'bcif';
}

export function buildIframeViewerUrl(input: MolstarStructureInput) {
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

export function hashSignature(value: string) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

export function buildOverlayIframeViewerUrl(
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

export function buildSignature(
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
