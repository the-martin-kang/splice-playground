'use client';

import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { API_BASE_URL } from '../../lib/api';
import {
  BASE_MAP,
  applySnvToSequence,
  normalizeBases,
  overwriteSequence,
  replaceRangeWithNs,
} from './dnaEditing';
import type { DifferenceSummary, DiseaseDetail, Region, RegionData } from './types';

export function useRegionSequenceEditor(
  diseaseId: string | null,
  diseaseDetail: DiseaseDetail | null,
  diagramRegions: Region[]
) {
  const [selectedRegion, setSelectedRegion] = useState<Region | null>(null);
  const [isRegionLoading, setIsRegionLoading] = useState(false);

  const [editedSequences, setEditedSequences] = useState<{ [regionId: string]: string }>({});
  const [originalSequences, setOriginalSequences] = useState<{ [regionId: string]: string }>({});
  const [snvSequences, setSnvSequences] = useState<{ [regionId: string]: string }>({});
  const [currentSequence, setCurrentSequence] = useState('');

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const editorBackdropRef = useRef<HTMLDivElement | null>(null);
  const pendingCaretRef = useRef<number | null>(null);
  const currentSequenceRef = useRef(currentSequence);
  const beforeInputSuppressUntilRef = useRef(0);
  const nativeChangeGuardRef = useRef<{ nextSequence: string; caret: number; expiresAt: number } | null>(null);

  useLayoutEffect(() => {
    currentSequenceRef.current = currentSequence;
    if (pendingCaretRef.current == null || !textareaRef.current) return;
    textareaRef.current.setSelectionRange(pendingCaretRef.current, pendingCaretRef.current);
    pendingCaretRef.current = null;
  }, [currentSequence]);

  const autoApplyDiseaseSnv = (diseaseDetail?.disease.seed_mode || 'apply_alt') !== 'reference_is_current';

  const initialRegionSequence = (originalSeq: string, snvSeq: string) =>
    autoApplyDiseaseSnv ? snvSeq : originalSeq;

  const baseSequenceForRegion = (regionId: string) => {
    const originalSeq = originalSequences[regionId] || '';
    const snvSeq = snvSequences[regionId] || originalSeq;
    return autoApplyDiseaseSnv ? snvSeq : originalSeq;
  };

  const eventNow = () => (
    typeof performance !== 'undefined' && typeof performance.now === 'function'
      ? performance.now()
      : Date.now()
  );

  const applyCaretWhenSequenceDoesNotRerender = (caret: number | null | undefined) => {
    if (caret == null) return;
    if (typeof window === 'undefined') return;
    window.requestAnimationFrame(() => {
      if (pendingCaretRef.current !== caret || !textareaRef.current) return;
      textareaRef.current.setSelectionRange(caret, caret);
      pendingCaretRef.current = null;
    });
  };

  const armNativeEditGuard = (nextSequence: string, caret: number) => {
    const expiresAt = eventNow() + 450;
    beforeInputSuppressUntilRef.current = expiresAt;
    nativeChangeGuardRef.current = { nextSequence, caret, expiresAt };
  };

  const shouldSuppressBeforeInput = () => {
    const now = eventNow();
    if (beforeInputSuppressUntilRef.current <= now) {
      beforeInputSuppressUntilRef.current = 0;
      return false;
    }
    beforeInputSuppressUntilRef.current = 0;
    return true;
  };

  const consumeNativeChangeGuard = () => {
    const guard = nativeChangeGuardRef.current;
    if (!guard) return null;
    if (guard.expiresAt <= eventNow()) {
      nativeChangeGuardRef.current = null;
      return null;
    }
    nativeChangeGuardRef.current = null;
    return guard;
  };

  const reconcileNativeTextareaChange = (previous: string, nativeValue: string) => {
    if (nativeValue === previous) {
      return { next: previous, caret: Math.min(textareaRef.current?.selectionStart ?? 0, previous.length) };
    }

    let prefix = 0;
    const maxPrefix = Math.min(previous.length, nativeValue.length);
    while (prefix < maxPrefix && previous[prefix] === nativeValue[prefix]) {
      prefix += 1;
    }

    let suffix = 0;
    while (
      suffix < previous.length - prefix &&
      suffix < nativeValue.length - prefix &&
      previous[previous.length - 1 - suffix] === nativeValue[nativeValue.length - 1 - suffix]
    ) {
      suffix += 1;
    }

    const removedStart = prefix;
    const removedEnd = previous.length - suffix;
    const insertedRaw = nativeValue.slice(prefix, nativeValue.length - suffix);

    if (insertedRaw.length > 0) {
      return overwriteSequence(previous, removedStart, removedEnd, insertedRaw);
    }

    if (removedEnd > removedStart) {
      return {
        next: replaceRangeWithNs(previous, removedStart, removedEnd),
        caret: removedStart,
      };
    }

    return { next: previous, caret: Math.min(textareaRef.current?.selectionStart ?? 0, previous.length) };
  };

  const commitSequence = (regionId: string, nextSequence: string, caret?: number | null) => {
    currentSequenceRef.current = nextSequence;
    pendingCaretRef.current = caret ?? null;
    setCurrentSequence(prev => {
      if (prev === nextSequence) {
        applyCaretWhenSequenceDoesNotRerender(caret);
      }
      return nextSequence;
    });
    setEditedSequences(prev => ({ ...prev, [regionId]: nextSequence }));
  };

  // LOGIC: select a region, fetch its sequence if needed, and seed the editable sequence.
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
      const snvSeq = applySnvToSequence(originalSeq, region, diseaseDetail);
      const initialSeq = initialRegionSequence(originalSeq, snvSeq);

      setOriginalSequences(prev => ({ ...prev, [region.region_id]: originalSeq }));
      setSnvSequences(prev => ({ ...prev, [region.region_id]: snvSeq }));
      setEditedSequences(prev => ({ ...prev, [region.region_id]: initialSeq }));
      setCurrentSequence(initialSeq);
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
      const snvSeq = applySnvToSequence(originalSeq, region, diseaseDetail);
      const initialSeq = initialRegionSequence(originalSeq, snvSeq);

      setOriginalSequences(prev => ({ ...prev, [region.region_id]: originalSeq }));
      setSnvSequences(prev => ({ ...prev, [region.region_id]: snvSeq }));
      setEditedSequences(prev => ({ ...prev, [region.region_id]: initialSeq }));
      setCurrentSequence(initialSeq);
    } catch (err) {
      console.error('Error fetching region:', err);
      setCurrentSequence('시퀀스를 불러올 수 없습니다');
    } finally {
      setIsRegionLoading(false);
    }
  };

  // LOGIC: editor controls for restoring disease SNV/reference sequence.
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

  // LOGIC: keyboard editing rules. Length is never changed; edits overwrite bases or set N.
  // The textarea is controlled, but production browsers can still emit beforeinput/change
  // around keydown. Guarding those native fallback events prevents duplicate bases and
  // prevents invalid keys from advancing the caret.
  const handleEditorKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!selectedRegion) return;
    if (event.nativeEvent.isComposing) return;

    const regionId = selectedRegion.region_id;
    const sequence = currentSequenceRef.current;
    const target = event.currentTarget;
    const start = target.selectionStart ?? 0;
    const end = target.selectionEnd ?? start;
    const lowerKey = event.key.toLowerCase();
    const blockedKeys = new Set([
      'Shift', 'CapsLock', 'Alt', 'AltGraph', 'Control', 'Meta',
      'PageUp', 'PageDown', 'Insert', 'Escape', 'Enter', 'Tab',
    ]);
    const navigationKeys = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End']);

    if ((event.ctrlKey || event.metaKey) && ['a', 'c', 'v'].includes(lowerKey)) {
      return;
    }

    if ((event.ctrlKey || event.metaKey) && lowerKey === 'x') {
      event.preventDefault();
      const next = start !== end ? replaceRangeWithNs(sequence, start, end) : sequence;
      armNativeEditGuard(next, start);
      commitSequence(regionId, next, start);
      return;
    }

    if (navigationKeys.has(event.key)) {
      return;
    }

    if (blockedKeys.has(event.key)) {
      event.preventDefault();
      armNativeEditGuard(sequence, start);
      commitSequence(regionId, sequence, start);
      return;
    }

    if (event.ctrlKey || event.metaKey || event.altKey) {
      event.preventDefault();
      armNativeEditGuard(sequence, start);
      commitSequence(regionId, sequence, start);
      return;
    }

    if (event.key === 'Backspace') {
      event.preventDefault();
      if (start !== end) {
        const next = replaceRangeWithNs(sequence, start, end);
        armNativeEditGuard(next, start);
        commitSequence(regionId, next, start);
        return;
      }
      if (start <= 0) {
        armNativeEditGuard(sequence, start);
        commitSequence(regionId, sequence, start);
        return;
      }
      const pos = start - 1;
      const next = sequence.slice(0, pos) + 'N' + sequence.slice(pos + 1);
      armNativeEditGuard(next, pos);
      commitSequence(regionId, next, pos);
      return;
    }

    if (event.key === 'Delete') {
      event.preventDefault();
      if (start !== end) {
        const next = replaceRangeWithNs(sequence, start, end);
        armNativeEditGuard(next, start);
        commitSequence(regionId, next, start);
        return;
      }
      if (start >= sequence.length) {
        armNativeEditGuard(sequence, start);
        commitSequence(regionId, sequence, start);
        return;
      }
      const next = sequence.slice(0, start) + 'N' + sequence.slice(start + 1);
      armNativeEditGuard(next, start);
      commitSequence(regionId, next, start);
      return;
    }

    if (event.key.length !== 1) {
      event.preventDefault();
      armNativeEditGuard(sequence, start);
      commitSequence(regionId, sequence, start);
      return;
    }

    const normalized = BASE_MAP[event.key];
    if (!normalized) {
      event.preventDefault();
      armNativeEditGuard(sequence, start);
      commitSequence(regionId, sequence, start);
      return;
    }

    event.preventDefault();
    const { next, caret } = overwriteSequence(sequence, start, end, normalized);
    armNativeEditGuard(next, caret);
    commitSequence(regionId, next, caret);
  };

  // LOGIC: browser input/paste fallback paths for the fixed-length DNA editor.
  const handleBeforeInput = (event: React.FormEvent<HTMLTextAreaElement>) => {
    if (!selectedRegion) return;
    const nativeEvent = event.nativeEvent as InputEvent;
    if (!nativeEvent || nativeEvent.isComposing) return;

    if (shouldSuppressBeforeInput()) {
      event.preventDefault();
      return;
    }

    const inputType = typeof nativeEvent.inputType === 'string' ? nativeEvent.inputType : '';

    if (inputType === 'insertLineBreak') {
      event.preventDefault();
      return;
    }

    const regionId = selectedRegion.region_id;
    const sequence = currentSequenceRef.current;
    const target = event.currentTarget;
    const start = target.selectionStart ?? 0;
    const end = target.selectionEnd ?? start;

    if (inputType.startsWith('delete')) {
      event.preventDefault();

      if (start !== end) {
        commitSequence(regionId, replaceRangeWithNs(sequence, start, end), start);
        return;
      }

      if (inputType.includes('Backward')) {
        if (start <= 0) {
          commitSequence(regionId, sequence, start);
          return;
        }
        const pos = start - 1;
        commitSequence(regionId, sequence.slice(0, pos) + 'N' + sequence.slice(pos + 1), pos);
        return;
      }

      if (start >= sequence.length) {
        commitSequence(regionId, sequence, start);
        return;
      }
      commitSequence(regionId, sequence.slice(0, start) + 'N' + sequence.slice(start + 1), start);
      return;
    }

    if (!inputType.startsWith('insert')) return;

    const inserted = normalizeBases(nativeEvent.data || '');
    if (!inserted) {
      event.preventDefault();
      commitSequence(regionId, sequence, start);
      return;
    }

    event.preventDefault();
    const { next, caret } = overwriteSequence(sequence, start, end, inserted);
    commitSequence(regionId, next, caret);
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!selectedRegion) return;
    event.preventDefault();

    const regionId = selectedRegion.region_id;
    const sequence = currentSequenceRef.current;
    const target = event.currentTarget;
    const start = target.selectionStart ?? 0;
    const end = target.selectionEnd ?? start;
    const pasted = normalizeBases(event.clipboardData.getData('text'));

    if (!pasted) {
      armNativeEditGuard(sequence, start);
      commitSequence(regionId, sequence, start);
      return;
    }

    const { next, caret } = overwriteSequence(sequence, start, end, pasted);
    armNativeEditGuard(next, caret);
    commitSequence(regionId, next, caret);
  };

  const handleTextareaFallbackChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    if (!selectedRegion) return;

    const guarded = consumeNativeChangeGuard();
    if (guarded) {
      commitSequence(selectedRegion.region_id, guarded.nextSequence, guarded.caret);
      return;
    }

    const sequence = currentSequenceRef.current;
    const { next, caret } = reconcileNativeTextareaChange(sequence, event.target.value);
    commitSequence(selectedRegion.region_id, next, caret);
  };


  const handleEditorScroll = (event: React.UIEvent<HTMLTextAreaElement>) => {
    if (!editorBackdropRef.current) return;
    editorBackdropRef.current.scrollTop = event.currentTarget.scrollTop;
    editorBackdropRef.current.scrollLeft = event.currentTarget.scrollLeft;
  };

  const hasEdits = (regionId: string): boolean => {
    if (!editedSequences[regionId]) return false;
    return editedSequences[regionId] !== baseSequenceForRegion(regionId);
  };

  const hasSNV = (regionId: string): boolean => {
    if (!diseaseDetail?.splice_altering_snv) return false;
    const region = diagramRegions.find(r => r.region_id === regionId);
    if (!region) return false;
    const snvPos = diseaseDetail.splice_altering_snv.pos_gene0;
    return snvPos >= region.gene_start_idx && snvPos <= region.gene_end_idx;
  };

  const currentOriginalSequence = selectedRegion ? originalSequences[selectedRegion.region_id] || '' : '';
  const currentBaseSequence = selectedRegion ? baseSequenceForRegion(selectedRegion.region_id) : '';
  // LOGIC: compute live diff counts shown in the editor summary chips.
  const differenceSummary: DifferenceSummary = useMemo(() => {
    if (!selectedRegion || !currentOriginalSequence || !currentSequence) return { toReference: 0, toSeed: 0 };
    let toReference = 0;
    let toSeed = 0;
    for (let i = 0; i < currentSequence.length; i += 1) {
      if (currentSequence[i] !== currentOriginalSequence[i]) toReference += 1;
      if (currentSequence[i] !== currentBaseSequence[i]) toSeed += 1;
    }
    return { toReference, toSeed };
  }, [selectedRegion, currentOriginalSequence, currentBaseSequence, currentSequence]);

  return {
    selectedRegion,
    isRegionLoading,
    editedSequences,
    originalSequences,
    snvSequences,
    currentSequence,
    currentOriginalSequence,
    differenceSummary,
    textareaRef,
    editorBackdropRef,
    handleRegionClick,
    restoreDiseaseSnv,
    restoreReference,
    handleEditorKeyDown,
    handleBeforeInput,
    handlePaste,
    handleTextareaFallbackChange,
    handleEditorScroll,
    hasEdits,
    hasSNV,
  };
}
