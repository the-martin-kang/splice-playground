'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

// 타입 정의
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

// API Base URL
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export default function DNAManipulator() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const diseaseId = searchParams.get('disease_id');

  // 상태 관리
  const [diseaseDetail, setDiseaseDetail] = useState<DiseaseDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 선택된 region
  const [selectedRegion, setSelectedRegion] = useState<Region | null>(null);
  const [isRegionLoading, setIsRegionLoading] = useState(false);

  // 편집된 시퀀스 (원본과 비교용)
  const [editedSequences, setEditedSequences] = useState<{ [regionId: string]: string }>({});
  const [originalSequences, setOriginalSequences] = useState<{ [regionId: string]: string }>({});
  const [currentSequence, setCurrentSequence] = useState<string>('');

  // 다이어그램에 표시할 5개 region (focus 기준 ±2)
  const [diagramRegions, setDiagramRegions] = useState<Region[]>([]);

  // 질병 상세 정보 로드
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

        // 다이어그램 구성: focus 기준 ±2 (총 5개)
        const allRegions = [...data.target.context_regions];
        // rel 기준 정렬 (-2, -1, 0, 1, 2)
        allRegions.sort((a, b) => (a.rel || 0) - (b.rel || 0));
        
        // focus_region의 rel은 0
        const focusWithRel = { ...data.target.focus_region, rel: 0 };
        
        // context_regions에서 focus 제외하고 합치기
        const regionsWithoutFocus = allRegions.filter(r => r.region_id !== focusWithRel.region_id);
        const finalRegions = [...regionsWithoutFocus, focusWithRel].sort((a, b) => (a.rel || 0) - (b.rel || 0));
        
        setDiagramRegions(finalRegions);

      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : '데이터를 불러올 수 없습니다';
        setError(errorMessage);
        console.error('Error fetching disease detail:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchDiseaseDetail();
  }, [diseaseId]);

  // Region 클릭 시 시퀀스 로드
  const handleRegionClick = async (region: Region) => {
    if (!diseaseId) return;

    // 이미 편집된 시퀀스가 있으면 그걸 사용
    if (editedSequences[region.region_id]) {
      setSelectedRegion(region);
      setCurrentSequence(editedSequences[region.region_id]);
      return;
    }

    // 시퀀스가 이미 있으면 그대로 사용
    if (region.sequence) {
      setSelectedRegion(region);
      setCurrentSequence(region.sequence);
      setEditedSequences(prev => ({ ...prev, [region.region_id]: region.sequence! }));
      setOriginalSequences(prev => ({ ...prev, [region.region_id]: region.sequence! }));
      return;
    }

    // API로 시퀀스 로드
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
      const sequence = data.region.sequence || '';
      setCurrentSequence(sequence);
      setEditedSequences(prev => ({ ...prev, [region.region_id]: sequence }));
      setOriginalSequences(prev => ({ ...prev, [region.region_id]: sequence }));

    } catch (err) {
      console.error('Error fetching region:', err);
      setCurrentSequence('시퀀스를 불러올 수 없습니다');
    } finally {
      setIsRegionLoading(false);
    }
  };

  // 시퀀스 편집 핸들러
  const handleSequenceChange = (newSequence: string) => {
    // 한글 → 영문 변환 (ㅁ→A, ㅊ→C, ㅎ→G, ㅅ→T, ㅜ→N)
    const koreanToEnglish: { [key: string]: string } = {
      'ㅁ': 'A', 'ㅊ': 'C', 'ㅎ': 'G', 'ㅅ': 'T', 'ㅜ': 'N',
      'a': 'A', 'c': 'C', 'g': 'G', 't': 'T', 'n': 'N'
    };
    
    let converted = '';
    for (const char of newSequence) {
      const upper = char.toUpperCase();
      if (koreanToEnglish[char]) {
        converted += koreanToEnglish[char];
      } else if (koreanToEnglish[upper]) {
        converted += koreanToEnglish[upper];
      } else if ('ACGTN'.includes(upper)) {
        converted += upper;
      }
      // 그 외 문자는 무시
    }
    
    // 빈 문자열이 되는 것 방지
    if (converted.length === 0 && currentSequence.length > 0) {
      return;
    }
    
    setCurrentSequence(converted);
    
    if (selectedRegion) {
      setEditedSequences(prev => ({
        ...prev,
        [selectedRegion.region_id]: converted
      }));
    }
  };

  // 변이 위치 확인 (현재 region 내에 SNV가 있는지)
  const getMutationIndex = (): number | null => {
    if (!selectedRegion || !diseaseDetail?.splice_altering_snv) return null;
    
    const snvPos = diseaseDetail.splice_altering_snv.pos_gene0;
    const { gene_start_idx, gene_end_idx } = selectedRegion;
    
    if (snvPos >= gene_start_idx && snvPos <= gene_end_idx) {
      return snvPos - gene_start_idx;
    }
    return null;
  };

  // 원본과 비교하여 변경된 위치 찾기
  const getChangedPositions = (): number[] => {
    if (!selectedRegion) return [];
    
    const originalSequence = originalSequences[selectedRegion.region_id] || '';
    
    const changes: number[] = [];
    for (let i = 0; i < currentSequence.length; i++) {
      if (currentSequence[i] !== originalSequence[i]) {
        changes.push(i);
      }
    }
    return changes;
  };

  // Step 3로 이동
  const handleNextStep = () => {
    // 편집된 시퀀스 정보를 localStorage에 저장 (또는 Context API 사용 가능)
    const step2Data = {
      diseaseId,
      diseaseDetail,
      editedSequences
    };
    localStorage.setItem('step2Data', JSON.stringify(step2Data));
    
    router.push(`/step3?disease_id=${encodeURIComponent(diseaseId || '')}`);
  };

  // 시퀀스에 수정 여부가 있는지 확인
  const hasEdits = (regionId: string): boolean => {
    // 원본 시퀀스가 없으면 (아직 로드 안됨) 수정 안된 것으로 처리
    if (!originalSequences[regionId]) return false;
    
    // 편집된 시퀀스가 없으면 수정 안됨
    if (!editedSequences[regionId]) return false;
    
    // 원본과 편집된 시퀀스 비교
    return editedSequences[regionId] !== originalSequences[regionId];
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-black"></div>
          <p className="mt-4 text-black font-semibold">로딩 중...</p>
        </div>
      </div>
    );
  }

  if (error || !diseaseDetail) {
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

  const mutationIndex = getMutationIndex();
  const changedPositions = getChangedPositions();

  return (
    <div className="min-h-screen bg-white p-8">
      <div className="max-w-7xl mx-auto">
        {/* (1) 제목 */}
        <div className="mb-8">
          <h1 className="text-5xl font-bold text-black">2. Manipulate DNA</h1>
        </div>

        {/* Main Container */}
        <div className="border-4 border-black rounded-3xl p-8 bg-white relative">
          
          {/* (4) 염색체 박스 - 우측 상단 */}
          <div className="absolute top-4 right-4 border-2 border-black rounded-xl p-4 bg-white w-40">
            <div className="flex flex-col items-center">
              {/* 염색체 이미지 (간단한 SVG) */}
              <svg width="60" height="100" viewBox="0 0 60 100" className="mb-2">
                <ellipse cx="30" cy="25" rx="15" ry="20" fill="#e5e5e5" stroke="black" strokeWidth="2"/>
                <ellipse cx="30" cy="75" rx="15" ry="20" fill="#e5e5e5" stroke="black" strokeWidth="2"/>
                <rect x="25" y="25" width="10" height="50" fill="#e5e5e5" stroke="black" strokeWidth="2"/>
                {/* 유전자 위치 표시 */}
                <circle cx="30" cy="50" r="5" fill="#3B82F6" stroke="black" strokeWidth="1"/>
              </svg>
              <p className="text-xs text-center font-semibold text-black">
                {diseaseDetail.gene.chromosome}
              </p>
              <p className="text-xs text-center text-gray-600">
                {diseaseDetail.gene.gene_symbol}
              </p>
            </div>
          </div>

          {/* (2) Exon/Intron 다이어그램 */}
          <div className="mb-8 pr-48">
            {/* 첫번째 줄: 정상 유전자 */}
            <div className="flex items-center gap-4 mb-4">
              <p className="text-sm font-semibold text-black whitespace-nowrap w-36">{diseaseDetail.gene.gene_symbol} (정상)</p>
              <div className="flex items-center gap-1">
                {diagramRegions.map((region, idx) => (
                  <div key={`normal-${region.region_id}`} className="flex items-center">
                    {region.region_type === 'exon' ? (
                      // Exon: 네모 박스
                      <div className="border-2 border-black rounded px-8 py-3 bg-white min-w-28 text-center">
                        <span className="text-sm font-semibold text-black">Exon{region.region_number}</span>
                      </div>
                    ) : (
                      // Intron: 굵은 선
                      <div className="flex flex-col items-center">
                        <div className="w-32 h-1 bg-black"></div>
                        <span className="text-xs mt-1 text-black">Intron{region.region_number}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* 두번째 줄: 변이 유전자 (클릭 가능) */}
            <div className="flex items-center gap-4 mt-8">
              <p className="text-sm font-semibold text-red-600 whitespace-nowrap w-36">{diseaseDetail.gene.gene_symbol} (편집 가능)</p>
              <div className="flex items-center gap-1">
                {diagramRegions.map((region, idx) => (
                  <div key={`mutant-${region.region_id}`} className="flex items-center">
                    {region.region_type === 'exon' ? (
                      // Exon: 클릭 가능한 네모 박스
                      <button
                        onClick={() => handleRegionClick(region)}
                        className={`border-2 rounded px-8 py-3 min-w-28 text-center transition-all
                          ${selectedRegion?.region_id === region.region_id 
                            ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-300' 
                            : 'border-black bg-white hover:bg-gray-50'}
                          ${hasEdits(region.region_id) ? 'border-red-500' : ''}
                        `}
                      >
                        <span className={`text-sm font-semibold ${hasEdits(region.region_id) ? 'text-red-600' : 'text-black'}`}>
                          Exon{region.region_number}
                        </span>
                        {hasEdits(region.region_id) && (
                          <div className="text-xs text-red-500">mutant</div>
                        )}
                      </button>
                    ) : (
                      // Intron: 클릭 가능한 굵은 선
                      <button
                        onClick={() => handleRegionClick(region)}
                        className={`flex flex-col items-center transition-all
                          ${selectedRegion?.region_id === region.region_id ? 'scale-110' : ''}
                        `}
                      >
                        <div className={`w-32 h-1 ${hasEdits(region.region_id) ? 'bg-red-500' : 'bg-black'} 
                          ${selectedRegion?.region_id === region.region_id ? 'h-2 bg-blue-500' : ''}
                        `}></div>
                        <span className={`text-xs mt-1 
                          ${hasEdits(region.region_id) ? 'text-red-500' : 'text-black'}
                          ${selectedRegion?.region_id === region.region_id ? 'text-blue-500 font-semibold' : ''}
                        `}>
                          Intron{region.region_number}
                          {hasEdits(region.region_id) && ' (mutant)'}
                        </span>
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* (3) 시퀀스 편집기 */}
          {selectedRegion && (
            <div className="border-2 border-blue-500 rounded-xl p-4 bg-blue-50">
              <div className="flex justify-between items-center mb-2">
                <h3 className="font-bold text-black">
                  {selectedRegion.region_type === 'exon' ? 'Exon' : 'Intron'} {selectedRegion.region_number} 서열 편집
                </h3>
                <span className="text-sm text-black">
                  길이: {currentSequence.length} bp
                </span>
              </div>

              {isRegionLoading ? (
                <div className="flex items-center justify-center h-32">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                </div>
              ) : (
                <>
                  {/* 원본 서열 (고정) */}
                  <div className="mb-4">
                    <p className="text-sm font-semibold text-gray-600 mb-1">원본 서열</p>
                    <div className="bg-gray-100 border border-gray-300 rounded p-4 font-mono text-sm overflow-x-auto max-h-32 overflow-y-auto text-black">
                      {originalSequences[selectedRegion.region_id] || '로딩 중...'}
                    </div>
                  </div>

                  {/* 수정된 시퀀스 표시 (색상 강조) */}
                  <div className="mb-2">
                    <p className="text-sm font-semibold text-black mb-1">편집된 서열</p>
                    <div className="bg-white border border-gray-300 rounded p-4 font-mono text-sm overflow-x-auto max-h-32 overflow-y-auto text-black">
                      {currentSequence.split('').map((char, idx) => {
                        const isMutation = mutationIndex === idx;
                        const isChanged = changedPositions.includes(idx);
                        
                        return (
                          <span
                            key={idx}
                            className={`
                              ${isMutation ? 'bg-red-500 text-white font-bold' : ''}
                              ${isChanged && !isMutation ? 'bg-yellow-300 text-black' : ''}
                            `}
                          >
                            {char}
                          </span>
                        );
                      })}
                    </div>
                  </div>

                  {/* 편집 영역 */}
                  <textarea
                    value={currentSequence}
                    onChange={(e) => handleSequenceChange(e.target.value)}
                    className="w-full h-32 p-3 border-2 border-gray-300 rounded-lg font-mono text-sm resize-none focus:border-blue-500 focus:outline-none text-black bg-white"
                    placeholder="DNA 서열을 편집하세요 (A, C, G, T, N만 허용)"
                  />

                  {changedPositions.length > 0 && (
                    <p className="text-red-600 text-sm mt-2">
                      ⚠️ {changedPositions.length}개 위치가 변경되었습니다
                    </p>
                  )}
                </>
              )}
            </div>
          )}

          {!selectedRegion && (
            <div className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center text-gray-500">
              <p>위의 Exon 또는 Intron을 클릭하여 서열을 편집하세요</p>
            </div>
          )}

          {/* (5) Next 버튼 */}
          <div className="flex justify-end mt-8">
            <button
              onClick={handleNextStep}
              className="border-4 border-blue-500 bg-white text-blue-500 rounded-2xl px-12 py-4 text-2xl font-bold italic hover:bg-blue-50 transition-all"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
