'use client';

import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../../lib/api';
import { getBaseSequenceForRegion, getPrimaryEvent, uniqueNumbers } from './splicingTransform';
import type { Edit, SplicingResponse, Step2Data } from './types';

export function useSplicingPrediction(diseaseId: string | null) {
  const [step2Data, setStep2Data] = useState<Step2Data | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // State & Splicing 결과
  const [stateId, setStateId] = useState<string | null>(null);
  const [splicingResult, setSplicingResult] = useState<SplicingResponse | null>(null);

  // 정상 mRNA exon 목록 (전체 exon)
  const [normalExons, setNormalExons] = useState<number[]>([]);
  
  // 비정상 mRNA - affected exons
  const [affectedExons, setAffectedExons] = useState<number[]>([]);
  
  // 이벤트 요약
  const [eventSummary, setEventSummary] = useState<string>('');

  // LOGIC: load Step 2 output, convert sequence differences into edits, create state, then predict splicing.
  useEffect(() => {
    const loadDataAndPredict = async () => {
      try {
        // Step2에서 저장한 데이터 로드
        const savedData = localStorage.getItem('step2Data');
        if (!savedData) {
          setError('Step2 데이터가 없습니다. Step2로 돌아가세요.');
          setIsLoading(false);
          return;
        }

        const data: Step2Data = JSON.parse(savedData);
        setStep2Data(data);

        // Exon 개수 가져오기
        const exonCount = data.diseaseDetail.gene.exon_count;
        const allExons = Array.from({ length: exonCount }, (_, i) => i + 1);
        setNormalExons(allExons);

        // Step2에서 편집한 내용을 edits 배열로 변환
        // current seed sequence(apply_alt면 representative SNV 적용, reference_is_current면 reference)와 사용자 편집 서열 비교
        const edits: Edit[] = [];
        
        if (data.snvSequences && data.editedSequences) {
          // 각 region별로 비교
          for (const regionId of Object.keys(data.editedSequences)) {
            const baseSeq = getBaseSequenceForRegion(data, regionId);
            const edited = data.editedSequences[regionId] || '';
            
            // region의 gene_start_idx 찾기
            const allRegions = [
              data.diseaseDetail.target.focus_region,
              ...data.diseaseDetail.target.context_regions
            ];
            const region = allRegions.find(r => r.region_id === regionId);
            
            if (!region) continue;
            
            const regionStart = region.gene_start_idx;
            
            // 각 위치별로 비교 (current seed sequence와 편집 서열)
            for (let i = 0; i < Math.max(baseSeq.length, edited.length); i++) {
              const fromChar = baseSeq[i] || '';
              const toChar = edited[i] || '';
              
              // SNV 적용 서열과 다르면 모두 edit으로 추가 (including N for deletions)
              if (fromChar !== toChar && fromChar !== '') {
                edits.push({
                  pos: regionStart + i,
                  from: fromChar,
                  to: toChar
                });
              }
            }
          }
        }

        // 1. Create State API 호출
        const createStateResponse = await fetch(
          `${API_BASE_URL}/api/diseases/${encodeURIComponent(data.diseaseId)}/states`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              applied_edit: {
                type: 'user',
                edits: edits.length > 0 ? edits : []
              }
            })
          }
        );

        if (!createStateResponse.ok) {
          const errorText = await createStateResponse.text();
          console.error('State 생성 에러:', errorText);
          throw new Error(`State 생성 실패: ${createStateResponse.status} - ${errorText}`);
        }

        const stateData = await createStateResponse.json();
        const newStateId = stateData.state_id;
        setStateId(newStateId);

        // 2. Predict Splicing API 호출
        const splicingResponse = await fetch(
          `${API_BASE_URL}/api/states/${encodeURIComponent(newStateId)}/splicing`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              region_radius: 3,
              flank: 5000,
              include_disease_snv: true,
              include_parent_chain: true,
              strict_ref_check: false,
              return_target_sequence: false
            })
          }
        );

        if (!splicingResponse.ok) {
          throw new Error(`Splicing 예측 실패: ${splicingResponse.status}`);
        }

        const splicingData: SplicingResponse = await splicingResponse.json();
        setSplicingResult(splicingData);

        const primaryEvent = getPrimaryEvent(splicingData);
        setAffectedExons(uniqueNumbers(primaryEvent?.affected_exon_numbers || []));

        // 이벤트 요약 설정
        if (splicingData.frontend_summary?.headline) {
          setEventSummary(splicingData.frontend_summary.headline);
        } else if (splicingData.interpreted_events?.length > 0) {
          const firstEvent = splicingData.interpreted_events[0];
          setEventSummary(firstEvent.summary || firstEvent.event_type);
        }

        setIsLoading(false);
      } catch (err) {
        console.error('Error:', err);
        setError(err instanceof Error ? err.message : '오류가 발생했습니다.');
        setIsLoading(false);
      }
    };

    loadDataAndPredict();
  }, [diseaseId]);

  return {
    step2Data,
    isLoading,
    error,
    stateId,
    splicingResult,
    normalExons,
    affectedExons,
    eventSummary,
  };
}
