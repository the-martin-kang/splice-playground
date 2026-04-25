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

  useLayoutEffect(() => {
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

  const applyCaretWhenSequenceDoesNotRerender = (caret: number | null | undefined) => {
    if (caret == null) return;
    if (typeof window === 'undefined') return;
    window.requestAnimationFrame(() => {
      if (pendingCaretRef.current !== caret || !textareaRef.current) return;
      textareaRef.current.setSelectionRange(caret, caret);
      pendingCaretRef.current = null;
    });
  };

  const commitSequence = (regionId: string, nextSequence: string, caret?: number | null) => {
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
      'PageUp', 'PageDown', 'Insert', 'Escape', 'Enter', 'Tab',
    ]);
    const navigationKeys = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End']);

    if ((event.ctrlKey || event.metaKey) && ['a', 'c', 'v'].includes(lowerKey)) {
      return;
    }

    if ((event.ctrlKey || event.metaKey) && lowerKey === 'x') {
      event.preventDefault();
      if (start !== end) {
        commitSequence(regionId, replaceRangeWithNs(currentSequence, start, end), start);
      }
      return;
    }

    if (navigationKeys.has(event.key)) {
      return;
    }

    if (blockedKeys.has(event.key)) {
      event.preventDefault();
      return;
    }

    if (event.ctrlKey || event.metaKey || event.altKey) {
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

  // LOGIC: browser input/paste fallback paths for the fixed-length DNA editor.
  const handleBeforeInput = (event: React.FormEvent<HTMLTextAreaElement>) => {
    if (!selectedRegion) return;
    const nativeEvent = event.nativeEvent as InputEvent;
    if (!nativeEvent || nativeEvent.isComposing) return;

    if (nativeEvent.inputType === 'insertLineBreak') {
      event.preventDefault();
      return;
    }

    if (nativeEvent.inputType.startsWith('delete')) {
      event.preventDefault();
      const target = event.currentTarget;
      const start = target.selectionStart ?? 0;
      const end = target.selectionEnd ?? start;

      if (start !== end) {
        commitSequence(selectedRegion.region_id, replaceRangeWithNs(currentSequence, start, end), start);
        return;
      }

      if (nativeEvent.inputType.includes('Backward')) {
        if (start <= 0) return;
        const pos = start - 1;
        commitSequence(
          selectedRegion.region_id,
          currentSequence.slice(0, pos) + 'N' + currentSequence.slice(pos + 1),
          pos
        );
        return;
      }

      if (start >= currentSequence.length) return;
      commitSequence(
        selectedRegion.region_id,
        currentSequence.slice(0, start) + 'N' + currentSequence.slice(start + 1),
        start
      );
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
