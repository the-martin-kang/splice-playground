'use client';

import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../../lib/api';
import type { DiseaseDetail, Region } from './types';

export function useStep2Disease(diseaseId: string | null) {
  const [diseaseDetail, setDiseaseDetail] = useState<DiseaseDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [diagramRegions, setDiagramRegions] = useState<Region[]>([]);

  // LOGIC: load Step 2 disease detail and build the displayed exon/intron diagram order.
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

  return {
    diseaseDetail,
    isLoading,
    error,
    diagramRegions,
  };
}
