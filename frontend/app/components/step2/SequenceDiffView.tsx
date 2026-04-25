interface SequenceDiffViewProps {
  source: string;
  compareTo: string;
  options?: {
    changedClassName?: string;
    sameClassName?: string;
    snvPosition?: number | null;
    snvClassName?: string;
  };
}

// UI helper: render per-base highlights by comparing two sequences.
export default function SequenceDiffView({ source, compareTo, options }: SequenceDiffViewProps) {
  const changedClassName =
    options?.changedClassName || 'bg-amber-300/55 text-slate-950';
  const sameClassName = options?.sameClassName || '';
  const snvClassName =
    options?.snvClassName || 'bg-rose-300/55 text-rose-950';

  return source.split('').map((char, idx) => {
    const isChanged = char !== compareTo[idx];
    const isSnv = options?.snvPosition === idx;
    const className = isChanged ? (isSnv ? `${changedClassName} ${snvClassName}` : changedClassName) : isSnv ? snvClassName : sameClassName;

    return (
      <span key={idx} className={className}>
        {char}
      </span>
    );
  });
}
