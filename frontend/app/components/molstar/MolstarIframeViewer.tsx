import { buildIframeViewerUrl } from './molstarUrls';
import { VIEWER_HEIGHT_CLASS, type MolstarStructureInput } from './types';

interface MolstarIframeViewerProps {
  primary: MolstarStructureInput;
}

export default function MolstarIframeViewer({ primary }: MolstarIframeViewerProps) {
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
