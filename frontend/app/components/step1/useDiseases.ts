'use client';

import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../../lib/api';
import type { Disease, DiseaseDetail } from './types';

export function useDiseases() {
  const [diseases, setDiseases] = useState<Disease[]>([]);
  const [selectedDiseaseId, setSelectedDiseaseId] = useState<string | null>(null);
  const [diseaseDetail, setDiseaseDetail] = useState<DiseaseDetail | null>(null);
  const [isListLoading, setIsListLoading] = useState(true);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 1. 질병 목록 조회 - GET /diseases
  useEffect(() => {
    const fetchDiseases = async () => {
      setIsListLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/api/diseases?limit=100&offset=0`);

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        setDiseases(data.items || []);
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : '질병 목록을 불러올 수 없습니다';
        setError(errorMessage);
        console.error('Error fetching diseases:', err);
      } finally {
        setIsListLoading(false);
      }
    };

    fetchDiseases();
  }, []);

  // 2. 질병 상세 조회 - GET /diseases/{disease_id}
  const handleSelectDisease = async (diseaseId: string) => {
    setSelectedDiseaseId(diseaseId);
    setDiseaseDetail(null);
    setIsDetailLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/diseases/${encodeURIComponent(diseaseId)}?include_sequence=true`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setDiseaseDetail(data);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : '질병 상세 정보를 불러올 수 없습니다';
      setError(errorMessage);
      console.error('Error fetching disease details:', err);
    } finally {
      setIsDetailLoading(false);
    }
  };

  const handleCloseModal = () => {
    setSelectedDiseaseId(null);
    setDiseaseDetail(null);
    setError(null);
  };

  return {
    diseases,
    selectedDiseaseId,
    diseaseDetail,
    isListLoading,
    isDetailLoading,
    error,
    handleSelectDisease,
    handleCloseModal,
  };
}
