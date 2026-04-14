'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

// 타입 정의
interface Edit {
  pos: number;
  from: string;
  to: string;
}

interface Region {
  region_id: string;
  region_type: 'exon' | 'intron';
  region_number: number;
  gene_start_idx: number;
  gene_end_idx: number;
  length: number;
  rel?: number;
}

interface InterpretedEvent {
  event_type: string;
  subtype?: string;
  confidence: string;
  summary: string;
  affected_exon_numbers?: number[];
  affected_intron_numbers?: number[];
}

interface FrontendSummary {
  primary_event_type: string;
  primary_subtype?: string;
  confidence: string;
  headline: string;
  interpretation_basis: string;
}

interface SplicingResponse {
  state_id: string;
  disease_id: string;
  gene_id: string;
  focus_region: Region;
  target_regions: Region[];
  interpreted_events: InterpretedEvent[];
  frontend_summary: FrontendSummary;
  warnings: string[];
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

interface Step2Data {
  diseaseId: string;
  diseaseDetail: DiseaseDetail;
  editedSequences: { [regionId: string]: string };
  originalSequences: { [regionId: string]: string };
  snvSequences: { [regionId: string]: string };
}

export default function MatureMRNA() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const diseaseId = searchParams.get('disease_id');

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
        // SNV가 이미 적용된 서열(snvSequences)과 사용자 편집 서열(editedSequences) 비교
        const edits: Edit[] = [];
        
        if (data.snvSequences && data.editedSequences) {
          // 각 region별로 비교
          for (const regionId of Object.keys(data.editedSequences)) {
            const snvSeq = data.snvSequences[regionId] || '';
            const edited = data.editedSequences[regionId] || '';
            
            // region의 gene_start_idx 찾기
            const allRegions = [
              data.diseaseDetail.target.focus_region,
              ...data.diseaseDetail.target.context_regions
            ];
            const region = allRegions.find(r => r.region_id === regionId);
            
            if (!region) continue;
            
            const regionStart = region.gene_start_idx;
            
            // 각 위치별로 비교 (SNV 적용 서열과 편집 서열)
            for (let i = 0; i < Math.max(snvSeq.length, edited.length); i++) {
              const fromChar = snvSeq[i] || '';
              const toChar = edited[i] || '';
              
              // SNV 서열과 다르고, N이 아닌 경우만 edit으로 추가
              if (fromChar !== toChar && toChar !== 'N' && fromChar !== '') {
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

        // Affected exons 추출
        const affected: number[] = [];
        if (splicingData.interpreted_events) {
          splicingData.interpreted_events.forEach(event => {
            if (event.affected_exon_numbers) {
              affected.push(...event.affected_exon_numbers);
            }
          });
        }
        setAffectedExons([...new Set(affected)]); // 중복 제거

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

  // Step 4로 이동
  const handleMakeProtein = () => {
    // Step3 데이터 저장
    const step3Data = {
      ...step2Data,
      stateId,
      splicingResult,
      normalExons,
      affectedExons,
      eventSummary
    };
    localStorage.setItem('step3Data', JSON.stringify(step3Data));
    
    router.push(`/step4?disease_id=${encodeURIComponent(diseaseId || '')}&state_id=${encodeURIComponent(stateId || '')}`);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-black"></div>
          <p className="mt-4 text-black font-semibold">Splicing 예측 중...</p>
        </div>
      </div>
    );
  }

  if (error || !step2Data) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-4">{error || '데이터를 불러올 수 없습니다'}</p>
          <button
            onClick={() => router.push('/')}
            className="border-2 border-black rounded-lg px-6 py-2 font-bold text-black hover:bg-gray-100 transition"
          >
            Step 1로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  const geneSymbol = step2Data.diseaseDetail.gene.gene_symbol;

  return (
    <div className="min-h-screen bg-white p-8">
      <div className="max-w-6xl mx-auto">
        {/* (1) 제목 */}
        <div className="mb-8">
          <h1 className="text-5xl font-bold text-black">3. Mature mRNA</h1>
        </div>

        {/* Main Container */}
        <div className="border-4 border-black rounded-3xl p-8 bg-white relative">
          
          {/* (2) 정상 mRNA */}
          <div className="mb-12">
            <p className="text-xl font-bold text-black mb-4">{geneSymbol} (정상)</p>
            <div className="flex items-center gap-1 flex-wrap">
              {normalExons.map((exonNum) => (
                <div 
                  key={`normal-${exonNum}`}
                  className="border-2 border-black rounded px-4 py-2 bg-white min-w-16 text-center"
                >
                  <span className="text-sm font-semibold text-black">Exon{exonNum}</span>
                </div>
              ))}
            </div>
          </div>

          {/* (3) 비정상 mRNA */}
          <div className="mb-12">
            <p className="text-xl font-bold text-red-600 italic mb-4">{geneSymbol} (비정상)</p>
            <div className="relative">
              <div className="flex items-center gap-1 flex-wrap">
                {normalExons.map((exonNum) => {
                  const isAffected = affectedExons.includes(exonNum);
                  
                  if (isAffected) {
                    // Affected exon - 빨간 점선 테두리
                    return (
                      <div key={`mutant-${exonNum}`} className="relative">
                        <div className="border-2 border-red-500 border-dashed rounded px-4 py-2 bg-red-50 min-w-16 text-center opacity-50">
                          <span className="text-sm font-semibold text-red-400 line-through">Exon{exonNum}</span>
                        </div>
                      </div>
                    );
                  }
                  
                  return (
                    <div 
                      key={`mutant-${exonNum}`}
                      className="border-2 border-black rounded px-4 py-2 bg-white min-w-16 text-center"
                    >
                      <span className="text-sm font-semibold text-black">Exon{exonNum}</span>
                    </div>
                  );
                })}
              </div>
            </div>
            
            {/* 이벤트 요약 */}
            {eventSummary && (
              <div className="mt-16 p-4 bg-yellow-50 border-2 border-yellow-400 rounded-lg">
                <p className="text-black font-semibold">{eventSummary}</p>
              </div>
            )}
          </div>

          {/* (4) Make Protein 버튼 */}
          <div className="flex justify-end mt-8">
            <button
              onClick={handleMakeProtein}
              className="border-4 border-blue-500 bg-white text-blue-500 rounded-2xl px-10 py-4 text-2xl font-bold hover:bg-blue-50 transition-all"
            >
              Make Protein
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}