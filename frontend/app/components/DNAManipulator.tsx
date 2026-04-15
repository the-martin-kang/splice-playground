'use client';

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

interface Region {
  region_id: string;
  region_type: 'exon' | 'intron';
  region_number: number;
  gene_start_idx: number;
  gene_end_idx: number;
  length: number;
  sequence: string | null;
  rel?: number;
}

interface DiseaseDetail {
  disease: {
    disease_id: string;
    disease_name: string;
    gene_id: string;
  };
  gene: {
    gene_id: string;
    gene_symbol: string;
    chromosome: string;
    strand: string;
    exon_count: number;
  };
  splice_altering_snv: {
    pos_gene0: number;
    ref: string;
    alt: string;
  } | null;
  target: {
    focus_region: Region;
    context_regions: Region[];
  };
}

interface RegionData {
  disease_id: string;
  gene_id: string;
  region: Region;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
const BASE_MAP: Record<string, string> = {
  A: 'A',
  C: 'C',
  G: 'G',
  T: 'T',
  N: 'N',
  a: 'A',
  c: 'C',
  g: 'G',
  t: 'T',
  n: 'N',
  'ㅁ': 'A',
  'ㅊ': 'C',
  'ㅎ': 'G',
  'ㅅ': 'T',
  'ㅜ': 'N',
};

function normalizeBases(input: string): string {
  let out = '';
  for (const char of input) {
    const mapped = BASE_MAP[char];
    if (mapped) out += mapped;
  }
  return out;
}

function replaceRangeWithNs(sequence: string, start: number, end: number) {
  if (start >= end) return sequence;
  return sequence.slice(0, start) + 'N'.repeat(end - start) + sequence.slice(end);
}

function overwriteSequence(
  original: string,
  start: number,
  end: number,
  insertedRaw: string
): { next: string; caret: number } {
  const inserted = normalizeBases(insertedRaw);
  if (!inserted) {
    return {
      next: replaceRangeWithNs(original, start, end),
      caret: start,
    };
  }

  const chars = original.split('');
  for (let i = start; i < end; i += 1) chars[i] = 'N';

  let cursor = start;
  for (const base of inserted) {
    if (cursor >= chars.length) break;
    chars[cursor] = base;
    cursor += 1;
  }

  return { next: chars.join(''), caret: cursor };
}

function renderDiffSpans(
  source: string,
  compareTo: string,
  options?: {
    changedClassName?: string;
    sameClassName?: string;
    snvPosition?: number | null;
    snvClassName?: string;
  }
) {
  const changedClassName =
    options?.changedClassName || 'rounded bg-amber-300/70 px-[1px] font-bold text-slate-950';
  const sameClassName = options?.sameClassName || '';
  const snvClassName =
    options?.snvClassName || 'rounded bg-rose-300/70 px-[1px] font-bold text-rose-950';

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

export default function DNAManipulator() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const diseaseId = searchParams.get('disease_id');

  const [diseaseDetail, setDiseaseDetail] = useState<DiseaseDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedRegion, setSelectedRegion] = useState<Region | null>(null);
  const [isRegionLoading, setIsRegionLoading] = useState(false);

  const [editedSequences, setEditedSequences] = useState<{ [regionId: string]: string }>({});
  const [originalSequences, setOriginalSequences] = useState<{ [regionId: string]: string }>({});
  const [snvSequences, setSnvSequences] = useState<{ [regionId: string]: string }>({});
  const [currentSequence, setCurrentSequence] = useState('');
  const [diagramRegions, setDiagramRegions] = useState<Region[]>([]);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const editorBackdropRef = useRef<HTMLDivElement | null>(null);
  const pendingCaretRef = useRef<number | null>(null);

  useLayoutEffect(() => {
    if (pendingCaretRef.current == null || !textareaRef.current) return;
    textareaRef.current.setSelectionRange(pendingCaretRef.current, pendingCaretRef.current);
    pendingCaretRef.current = null;
  }, [currentSequence]);

  useEffect(() => {
    if (!diseaseId) {
      setError('disease_id가 없습니다');
      setIsLoading(false);
      return;
    }

    const fetchDiseaseDetail = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/diseases/${encodeURIComponent(diseaseId)}?include_sequence=true`
        );

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data: DiseaseDetail = await response.json();
        setDiseaseDetail(data);

        const allRegions = [...data.target.context_regions];
        allRegions.sort((a, b) => (a.rel || 0) - (b.rel || 0));
        const focusWithRel = { ...data.target.focus_region, rel: 0 };
        const regionsWithoutFocus = allRegions.filter(r => r.region_id !== focusWithRel.region_id);
        const finalRegions = [...regionsWithoutFocus, focusWithRel].sort(
          (a, b) => (a.rel || 0) - (b.rel || 0)
        );
        setDiagramRegions(finalRegions);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : '데이터를 불러올 수 없습니다';
        setError(errorMessage);
        console.error('Error fetching disease detail:', err);
      } finally {
        setIsLoading(false);
      }
    };

    void fetchDiseaseDetail();
  }, [diseaseId]);

  const applySnvToSequence = (sequence: string, region: Region): string => {
    if (!diseaseDetail?.splice_altering_snv) return sequence;

    const snvPos = diseaseDetail.splice_altering_snv.pos_gene0;
    const { gene_start_idx, gene_end_idx } = region;

    if (snvPos >= gene_start_idx && snvPos <= gene_end_idx) {
      const localIndex = snvPos - gene_start_idx;
      const alt = diseaseDetail.splice_altering_snv.alt;
      return sequence.substring(0, localIndex) + alt + sequence.substring(localIndex + 1);
    }

    return sequence;
  };

  const commitSequence = (regionId: string, nextSequence: string, caret?: number | null) => {
    setCurrentSequence(nextSequence);
    setEditedSequences(prev => ({ ...prev, [regionId]: nextSequence }));
    pendingCaretRef.current = caret ?? null;
  };

  const handleRegionClick = async (region: Region) => {
    if (!diseaseId) return;

    if (editedSequences[region.region_id]) {
      setSelectedRegion(region);
      setCurrentSequence(editedSequences[region.region_id]);
      return;
    }

    if (region.sequence) {
      setSelectedRegion(region);
      const originalSeq = region.sequence;
      const snvSeq = applySnvToSequence(originalSeq, region);

      setOriginalSequences(prev => ({ ...prev, [region.region_id]: originalSeq }));
      setSnvSequences(prev => ({ ...prev, [region.region_id]: snvSeq }));
      setEditedSequences(prev => ({ ...prev, [region.region_id]: snvSeq }));
      setCurrentSequence(snvSeq);
      return;
    }

    setIsRegionLoading(true);
    setSelectedRegion(region);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/diseases/${encodeURIComponent(diseaseId)}/regions/${region.region_type}/${region.region_number}?include_sequence=true`
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: RegionData = await response.json();
      const originalSeq = data.region.sequence || '';
      const snvSeq = applySnvToSequence(originalSeq, region);

      setOriginalSequences(prev => ({ ...prev, [region.region_id]: originalSeq }));
      setSnvSequences(prev => ({ ...prev, [region.region_id]: snvSeq }));
      setEditedSequences(prev => ({ ...prev, [region.region_id]: snvSeq }));
      setCurrentSequence(snvSeq);
    } catch (err) {
      console.error('Error fetching region:', err);
      setCurrentSequence('시퀀스를 불러올 수 없습니다');
    } finally {
      setIsRegionLoading(false);
    }
  };

  const restoreDiseaseSnv = () => {
    if (!selectedRegion) return;
    const snvSeq = snvSequences[selectedRegion.region_id];
    if (!snvSeq) return;
    commitSequence(selectedRegion.region_id, snvSeq);
  };

  const restoreReference = () => {
    if (!selectedRegion) return;
    const originalSeq = originalSequences[selectedRegion.region_id];
    if (!originalSeq) return;
    commitSequence(selectedRegion.region_id, originalSeq);
  };

  const handleEditorKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!selectedRegion) return;
    if (event.nativeEvent.isComposing) return;

    const regionId = selectedRegion.region_id;
    const target = event.currentTarget;
    const start = target.selectionStart ?? 0;
    const end = target.selectionEnd ?? start;
    const lowerKey = event.key.toLowerCase();
    const blockedKeys = new Set([
      'Shift', 'CapsLock', 'Alt', 'AltGraph', 'Control', 'Meta',
      'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown',
      'Home', 'End', 'PageUp', 'PageDown', 'Insert', 'Escape',
      'Enter', 'Tab',
    ]);

    if ((event.ctrlKey || event.metaKey) && ['a', 'c', 'v'].includes(lowerKey)) {
      return;
    }

    if (event.ctrlKey || event.metaKey || event.altKey || blockedKeys.has(event.key)) {
      event.preventDefault();
      return;
    }

    if (event.key === 'Backspace') {
      event.preventDefault();
      if (start !== end) {
        commitSequence(regionId, replaceRangeWithNs(currentSequence, start, end), start);
        return;
      }
      if (start <= 0) return;
      const pos = start - 1;
      const next = currentSequence.slice(0, pos) + 'N' + currentSequence.slice(pos + 1);
      commitSequence(regionId, next, pos);
      return;
    }

    if (event.key === 'Delete') {
      event.preventDefault();
      if (start !== end) {
        commitSequence(regionId, replaceRangeWithNs(currentSequence, start, end), start);
        return;
      }
      if (start >= currentSequence.length) return;
      const next = currentSequence.slice(0, start) + 'N' + currentSequence.slice(start + 1);
      commitSequence(regionId, next, start);
      return;
    }

    if (event.key.length !== 1) {
      event.preventDefault();
      return;
    }

    const normalized = BASE_MAP[event.key];
    if (!normalized) {
      event.preventDefault();
      return;
    }

    event.preventDefault();
    const { next, caret } = overwriteSequence(currentSequence, start, end, normalized);
    commitSequence(regionId, next, caret);
  };

  const handleBeforeInput = (event: React.FormEvent<HTMLTextAreaElement>) => {
    if (!selectedRegion) return;
    const nativeEvent = event.nativeEvent as InputEvent;
    if (!nativeEvent || nativeEvent.isComposing) return;

    if (nativeEvent.inputType === 'insertLineBreak') {
      event.preventDefault();
      return;
    }

    if (!nativeEvent.inputType.startsWith('insert')) return;

    const inserted = normalizeBases(nativeEvent.data || '');
    if (!inserted) {
      event.preventDefault();
      return;
    }

    event.preventDefault();

    const target = event.currentTarget;
    const start = target.selectionStart ?? 0;
    const end = target.selectionEnd ?? start;
    const { next, caret } = overwriteSequence(currentSequence, start, end, inserted);
    commitSequence(selectedRegion.region_id, next, caret);
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!selectedRegion) return;
    event.preventDefault();

    const pasted = normalizeBases(event.clipboardData.getData('text'));
    if (!pasted) return;

    const target = event.currentTarget;
    const start = target.selectionStart ?? 0;
    const end = target.selectionEnd ?? start;
    const { next, caret } = overwriteSequence(currentSequence, start, end, pasted);
    commitSequence(selectedRegion.region_id, next, caret);
  };

  const handleTextareaFallbackChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    if (!selectedRegion) return;
    const sanitized = normalizeBases(event.target.value);
    if (!sanitized) {
      commitSequence(selectedRegion.region_id, currentSequence);
      return;
    }

    const truncated = sanitized.slice(0, currentSequence.length).padEnd(currentSequence.length, 'N');
    commitSequence(selectedRegion.region_id, truncated, Math.min(event.target.selectionStart ?? 0, truncated.length));
  };


  const handleEditorScroll = (event: React.UIEvent<HTMLTextAreaElement>) => {
    if (!editorBackdropRef.current) return;
    editorBackdropRef.current.scrollTop = event.currentTarget.scrollTop;
    editorBackdropRef.current.scrollLeft = event.currentTarget.scrollLeft;
  };


  const handleNextStep = () => {
    const step2Data = {
      diseaseId,
      diseaseDetail,
      editedSequences,
      originalSequences,
      snvSequences,
    };
    localStorage.setItem('step2Data', JSON.stringify(step2Data));
    router.push(`/step3?disease_id=${encodeURIComponent(diseaseId || '')}`);
  };

  const hasEdits = (regionId: string): boolean => {
    if (!snvSequences[regionId]) return false;
    if (!editedSequences[regionId]) return false;
    return editedSequences[regionId] !== snvSequences[regionId];
  };

  const hasSNV = (regionId: string): boolean => {
    if (!diseaseDetail?.splice_altering_snv) return false;
    const region = diagramRegions.find(r => r.region_id === regionId);
    if (!region) return false;
    const snvPos = diseaseDetail.splice_altering_snv.pos_gene0;
    return snvPos >= region.gene_start_idx && snvPos <= region.gene_end_idx;
  };

  const currentOriginalSequence = selectedRegion ? originalSequences[selectedRegion.region_id] || '' : '';
  const currentSeedSequence = selectedRegion ? snvSequences[selectedRegion.region_id] || '' : '';
  const differenceSummary = useMemo(() => {
    if (!selectedRegion || !currentOriginalSequence || !currentSequence) return { toReference: 0, toSeed: 0 };
    let toReference = 0;
    let toSeed = 0;
    for (let i = 0; i < currentSequence.length; i += 1) {
      if (currentSequence[i] !== currentOriginalSequence[i]) toReference += 1;
      if (currentSequence[i] !== currentSeedSequence[i]) toSeed += 1;
    }
    return { toReference, toSeed };
  }, [selectedRegion, currentOriginalSequence, currentSeedSequence, currentSequence]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-transparent px-4">
        <div className="w-full max-w-md rounded-[24px] border border-white/18 bg-white/5 p-10 text-center shadow-[0_30px_120px_rgba(15,23,42,0.16)] backdrop-blur-lg">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
          <p className="mt-4 font-semibold text-slate-950">로딩 중...</p>
        </div>
      </div>
    );
  }

  if (error || !diseaseDetail) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-transparent px-4">
        <div className="w-full max-w-md rounded-[24px] border border-white/18 bg-white/5 p-10 text-center shadow-[0_30px_120px_rgba(15,23,42,0.16)] backdrop-blur-lg">
          <p className="mb-4 text-rose-900">{error || '데이터를 불러올 수 없습니다'}</p>
          <button
            onClick={() => router.push('/select-mutant')}
            className="rounded-[14px] border border-black/10 bg-white/10 px-6 py-2 font-bold text-slate-900 shadow-[0_12px_30px_rgba(15,23,42,0.06)] transition hover:bg-white/12"
          >
            Step 1로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-transparent px-4 py-8 sm:px-6 lg:px-8">
      <div className="relative mx-auto max-w-7xl">
        <div className="mb-8 rounded-[24px] border border-white/18 bg-white/5 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          <div className="mb-4 inline-flex rounded-[14px] border border-black/10 bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.32em] text-slate-800">
            Splice Playground
          </div>
          <h1 className="text-4xl font-black tracking-tight text-slate-950 sm:text-5xl">2. Manipulate DNA</h1>
        </div>

        <div className="relative rounded-[28px] border border-white/18 bg-white/5 p-5 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          <div className="absolute right-4 top-4 w-40 rounded-[18px] border border-white/16 bg-white/5 p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
            <div className="flex flex-col items-center">
              <svg width="60" height="100" viewBox="0 0 60 100" className="mb-2">
                <ellipse cx="30" cy="25" rx="15" ry="20" fill="rgba(255,255,255,0.72)" stroke="rgba(255,255,255,0.9)" strokeWidth="2"/>
                <ellipse cx="30" cy="75" rx="15" ry="20" fill="rgba(255,255,255,0.72)" stroke="rgba(255,255,255,0.9)" strokeWidth="2"/>
                <rect x="25" y="25" width="10" height="50" fill="rgba(255,255,255,0.72)" stroke="rgba(255,255,255,0.9)" strokeWidth="2"/>
                <circle cx="30" cy="50" r="5" fill="#38BDF8" stroke="white" strokeWidth="1"/>
              </svg>
              <p className="text-xs text-center font-semibold text-slate-950">{diseaseDetail.gene.chromosome}</p>
              <p className="text-xs text-center text-slate-700">{diseaseDetail.gene.gene_symbol}</p>
            </div>
          </div>

          <div className="mb-8 pr-48">
            <div className="mb-4 flex items-center gap-4">
              <p className="w-36 whitespace-nowrap text-sm font-semibold text-slate-900">{diseaseDetail.gene.gene_symbol} (정상)</p>
              <div className="flex items-center gap-1">
                {diagramRegions.map((region) => (
                  <div key={`normal-${region.region_id}`} className="flex items-center">
                    {region.region_type === 'exon' ? (
                      <div className="min-w-28 rounded-xl border border-white/16 bg-white/5 px-8 py-3 text-center shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm">
                        <span className="text-sm font-semibold text-slate-950">Exon{region.region_number}</span>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center">
                        <div className="h-1 w-32 rounded-full bg-white/85"></div>
                        <span className="mt-1 text-xs text-slate-700">Intron{region.region_number}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8 flex items-center gap-4">
              <p className="w-36 whitespace-nowrap text-sm font-semibold text-rose-800">{diseaseDetail.gene.gene_symbol} (편집 가능)</p>
              <div className="flex items-center gap-1">
                {diagramRegions.map((region) => (
                  <div key={`mutant-${region.region_id}`} className="flex items-center">
                    {region.region_type === 'exon' ? (
                      <button
                        onClick={() => handleRegionClick(region)}
                        className={`min-w-28 rounded-xl border px-8 py-3 text-center shadow-[0_10px_30px_rgba(15,23,42,0.10)] backdrop-blur-sm transition-all
                          ${selectedRegion?.region_id === region.region_id
                            ? 'border-cyan-300/60 bg-cyan-100/12 ring-2 ring-cyan-300/40'
                            : hasSNV(region.region_id)
                              ? 'border-rose-300/60 bg-rose-100/12'
                              : 'border-white/16 bg-white/5 hover:bg-white/8'}
                          ${hasEdits(region.region_id) ? 'border-amber-300/80' : ''}
                        `}
                      >
                        <span className={`text-sm font-semibold ${hasSNV(region.region_id) ? 'text-rose-800' : hasEdits(region.region_id) ? 'text-amber-800' : 'text-slate-950'}`}>
                          Exon{region.region_number}
                        </span>
                        {hasSNV(region.region_id) && <div className="text-xs text-rose-700">SNV</div>}
                        {hasEdits(region.region_id) && <div className="text-xs text-amber-700">edited</div>}
                      </button>
                    ) : (
                      <button
                        onClick={() => handleRegionClick(region)}
                        className={`flex flex-col items-center transition-all ${selectedRegion?.region_id === region.region_id ? 'scale-110' : ''}`}
                      >
                        <div className={`w-32 rounded-full ${selectedRegion?.region_id === region.region_id ? 'h-2 bg-cyan-200' : hasSNV(region.region_id) ? 'h-1 bg-rose-400' : hasEdits(region.region_id) ? 'h-1 bg-amber-400' : 'h-1 bg-slate-600'}`}></div>
                        <span className={`mt-1 text-xs ${hasSNV(region.region_id) ? 'font-semibold text-rose-700' : hasEdits(region.region_id) ? 'text-amber-700' : 'text-slate-700'} ${selectedRegion?.region_id === region.region_id ? 'font-semibold text-cyan-700' : ''}`}>
                          Intron{region.region_number}
                          {hasSNV(region.region_id) && ' (SNV)'}
                          {hasEdits(region.region_id) && ' (edited)'}
                        </span>
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {selectedRegion ? (
            <div className="rounded-[20px] border border-cyan-300/25 bg-white/5 p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-lg">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                <h3 className="font-bold text-slate-950">
                  {selectedRegion.region_type === 'exon' ? 'Exon' : 'Intron'} {selectedRegion.region_number} 서열 편집
                </h3>
                <div className="flex flex-wrap gap-2 text-xs text-slate-700">
                  <span className="rounded-full border border-white/16 bg-white/5 px-3 py-1">길이: {currentSequence.length} bp</span>
                  <span className="rounded-full border border-white/16 bg-white/5 px-3 py-1">Reference diff: {differenceSummary.toReference}</span>
                  <span className="rounded-full border border-white/16 bg-white/5 px-3 py-1">Seed diff: {differenceSummary.toSeed}</span>
                </div>
              </div>

              {isRegionLoading ? (
                <div className="flex h-32 items-center justify-center">
                  <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
                </div>
              ) : (
                <>
                  <div className="mb-3 flex flex-wrap gap-2">
                    <button
                      onClick={restoreDiseaseSnv}
                      className="rounded-full border border-rose-300/55 bg-rose-100/10 px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100/15"
                    >
                      Restore disease SNV
                    </button>
                    <button
                      onClick={restoreReference}
                      className="rounded-full border border-emerald-300/55 bg-emerald-100/10 px-4 py-2 text-sm font-semibold text-emerald-900 transition hover:bg-emerald-100/15"
                    >
                      Restore reference
                    </button>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-2">
                    <div>
                      <p className="mb-1 text-sm font-semibold text-slate-800">정상 서열 (Reference)</p>
                      <div className="max-h-40 overflow-auto rounded-xl border border-white/16 bg-white/5 p-4 font-mono text-sm leading-6 text-slate-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] break-all whitespace-pre-wrap">
                        {currentOriginalSequence
                          ? renderDiffSpans(currentOriginalSequence, currentSequence, {
                              changedClassName: 'rounded bg-amber-300/75 px-[1px] font-bold text-slate-950',
                            })
                          : '로딩 중...'}
                      </div>
                    </div>

                    <div>
                      <p className="mb-1 text-sm font-semibold text-cyan-800">편집 서열 (고정 길이 overwrite 모드)</p>
                      <div className="relative overflow-hidden rounded-xl border border-white/16 bg-white/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
                        <div
                          ref={editorBackdropRef}
                          aria-hidden="true"
                          className="pointer-events-none max-h-56 overflow-auto p-4 font-mono text-sm leading-6 text-slate-950 break-all whitespace-pre-wrap"
                        >
                          {renderDiffSpans(currentSequence, currentOriginalSequence, {
                            changedClassName: 'rounded bg-amber-300/75 px-[1px] font-bold text-slate-950',
                          })}
                        </div>
                        <textarea
                          ref={textareaRef}
                          value={currentSequence}
                          spellCheck={false}
                          autoCapitalize="off"
                          autoCorrect="off"
                          autoComplete="off"
                          onKeyDown={handleEditorKeyDown}
                          onBeforeInput={handleBeforeInput}
                          onPaste={handlePaste}
                          onChange={handleTextareaFallbackChange}
                          onScroll={handleEditorScroll}
                          className="absolute inset-0 min-h-full w-full resize-none bg-transparent p-4 font-mono text-sm leading-6 text-transparent caret-slate-950 outline-none selection:bg-cyan-200/40"
                        />
                      </div>
                      <p className="mt-2 text-xs text-slate-700">
                        Backspace/Delete는 길이를 줄이지 않고 해당 위치를 <span className="font-bold">N</span>으로 바꿉니다. 입력/붙여넣기는 항상 기존 길이를 유지한 채 덮어쓰기됩니다.
                      </p>
                    </div>
                  </div>
                  {differenceSummary.toReference > 0 && (
                    <p className="mt-3 text-sm text-rose-800">⚠️ 정상 서열(Reference)과 비교해 {differenceSummary.toReference}개 위치가 다릅니다.</p>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="rounded-[20px] border border-dashed border-white/16 bg-white/5 p-8 text-center text-slate-800 backdrop-blur-sm">
              <p>위의 Exon 또는 Intron을 클릭하여 서열을 편집하세요</p>
            </div>
          )}

          <div className="mt-8 flex justify-end">
            <button
              onClick={handleNextStep}
              className="rounded-full border border-cyan-300/60 bg-[linear-gradient(135deg,rgba(14,165,233,0.95),rgba(37,99,235,0.92))] px-12 py-4 text-2xl font-bold italic text-white shadow-[0_18px_45px_rgba(2,132,199,0.35)] transition-all hover:brightness-105"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
