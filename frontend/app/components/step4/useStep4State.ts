'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { extractApiMessage, formatError } from './step4Formatters';
import { mergeMolstarTarget } from './step4Transforms';
import type { ActiveStructureView, MolstarTarget, Step4StateResponse } from './types';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.splice-playground-api.com';

export function useStep4State(diseaseId: string | null, stateId: string | null) {
  const [step4Data, setStep4Data] = useState<Step4StateResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeStructureView, setActiveStructureView] = useState<ActiveStructureView>('normal');
  const [stableNormalTarget, setStableNormalTarget] = useState<MolstarTarget | null>(null);
  const [stableUserTarget, setStableUserTarget] = useState<MolstarTarget | null>(null);
  const hasInitializedViewRef = useRef(false);

  // LOGIC: fetch Step 4 state payload and stabilize Mol* structure targets across refreshes.
  const fetchStep4 = useCallback(async (showLoading = true) => {
    if (!stateId) return;
    if (showLoading) setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/states/${encodeURIComponent(stateId)}/step4?include_sequences=false`
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(extractApiMessage(payload) || `HTTP error! status: ${response.status}`);
      }

      const data = payload as Step4StateResponse;
      setStep4Data(data);
      setStableNormalTarget((prev) => mergeMolstarTarget(prev, data.normal_track.molstar_default || null));
      setStableUserTarget((prev) =>
        mergeMolstarTarget(prev, data.user_track.latest_structure_job?.molstar_default || null)
      );

      if (!hasInitializedViewRef.current) {
        setActiveStructureView('normal');
        hasInitializedViewRef.current = true;
      }
    } catch (fetchError) {
      setError(formatError(fetchError));
    } finally {
      if (showLoading) setIsLoading(false);
    }
  }, [stateId]);

  // LOGIC: initial Step 4 load once disease_id/state_id are available.
  useEffect(() => {
    if (!diseaseId || !stateId) {
      setError('step4에 필요한 disease_id 또는 state_id가 없습니다.');
      setIsLoading(false);
      return;
    }
    void fetchStep4(true);
  }, [diseaseId, stateId, fetchStep4]);

  return {
    step4Data,
    isLoading,
    error,
    activeStructureView,
    setActiveStructureView,
    stableNormalTarget,
    stableUserTarget,
    setStableUserTarget,
    fetchStep4,
  };
}
