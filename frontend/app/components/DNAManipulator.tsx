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
  const [originalSequences, setOriginalSequences] = useState<{ [regionId: string]: string }>({});  // 정상 서열 (ref)
  const [snvSequences, setSnvSequences] = useState<{ [regionId: string]: string }>({});  // SNV 적용 서열 (alt)
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

  // SNV가 해당 region에 있는지 확인하고, SNV 적용 서열 생성
  const applySnvToSequence = (sequence: string, region: Region): string => {
    if (!diseaseDetail?.splice_altering_snv) return sequence;
    
    const snvPos = diseaseDetail.splice_altering_snv.pos_gene0;
    const { gene_start_idx, gene_end_idx } = region;
    
    // SNV가 이 region 내에 있는지 확인
    if (snvPos >= gene_start_idx && snvPos <= gene_end_idx) {
      const localIndex = snvPos - gene_start_idx;
      const alt = diseaseDetail.splice_altering_snv.alt;
      
      // SNV 적용
      return sequence.substring(0, localIndex) + alt + sequence.substring(localIndex + 1);
    }
    
    return sequence;
  };

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
      const originalSeq = region.sequence;
      const snvSeq = applySnvToSequence(originalSeq, region);
      
      setOriginalSequences(prev => ({ ...prev, [region.region_id]: originalSeq }));
      setSnvSequences(prev => ({ ...prev, [region.region_id]: snvSeq }));
      setEditedSequences(prev => ({ ...prev, [region.region_id]: snvSeq }));
      setCurrentSequence(snvSeq);
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

  // 시퀀스 편집 핸들러 (길이 고정, 지운 자리에 N 삽입, N 대체 가능)
  const handleSequenceChange = (newSequence: string, cursorPosition?: number) => {
    if (!selectedRegion) return;
    
    const originalLength = originalSequences[selectedRegion.region_id]?.length || currentSequence.length;
    
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
    
    let finalSequence: string;
    const prevSequence = currentSequence;
    
    if (converted.length < originalLength) {
      // 삭제된 경우: 커서 위치 기준으로 삭제된 위치에 N 삽입
      const deleteCount = originalLength - converted.length;
      const deletePosition = cursorPosition !== undefined ? cursorPosition : converted.length;
      
      // 삭제 위치 앞부분 + N + 삭제 위치 뒷부분
      finalSequence = 
        converted.substring(0, deletePosition) + 
        'N'.repeat(deleteCount) + 
        converted.substring(deletePosition);
        
    } else if (converted.length > originalLength) {
      // 초과된 경우: 커서 위치 바로 뒤의 N을 대체
      const excessCount = converted.length - originalLength;
      const insertPos = cursorPosition !== undefined ? cursorPosition : converted.length;
      
      // 새로 입력된 부분 (커서 앞쪽)
      const beforeCursor = converted.substring(0, insertPos);
      // 이전 시퀀스에서 입력 시작 위치 이후 부분
      const startInPrev = insertPos - excessCount;
      const afterCursorInPrev = prevSequence.substring(startInPrev);
      
      // N을 제거하면서 뒤 문자 유지
      let afterPart = '';
      let nToRemove = excessCount;
      
      for (let i = 0; i < afterCursorInPrev.length; i++) {
        if (afterCursorInPrev[i] === 'N' && nToRemove > 0) {
          nToRemove--;
          // N은 건너뜀
        } else {
          afterPart += afterCursorInPrev[i];
        }
      }
      
      finalSequence = (beforeCursor + afterPart).substring(0, originalLength);
      
      // 길이가 부족하면 N으로 채움
      if (finalSequence.length < originalLength) {
        finalSequence += 'N'.repeat(originalLength - finalSequence.length);
      }
    } else {
      finalSequence = converted;
    }
    
    setCurrentSequence(finalSequence);
    
    setEditedSequences(prev => ({
      ...prev,
      [selectedRegion.region_id]: finalSequence
    }));
  };

  // SNV 서열과 비교하여 변경된 위치 찾기 (사용자 편집)
  const getChangedPositions = (): number[] => {
    if (!selectedRegion) return [];
    
    const snvSeq = snvSequences[selectedRegion.region_id] || '';
    
    const changes: number[] = [];
    for (let i = 0; i < currentSequence.length; i++) {
      if (currentSequence[i] !== snvSeq[i]) {
        changes.push(i);
      }
    }
    return changes;
  };
  
  // 원본과 SNV 서열 비교하여 SNV 위치 찾기
  const getSnvPosition = (): number | null => {
    if (!selectedRegion || !diseaseDetail?.splice_altering_snv) return null;
    
    const snvPos = diseaseDetail.splice_altering_snv.pos_gene0;
    const { gene_start_idx, gene_end_idx } = selectedRegion;
    
    if (snvPos >= gene_start_idx && snvPos <= gene_end_idx) {
      return snvPos - gene_start_idx;
    }
    return null;
  };

  // Step 3로 이동
  const handleNextStep = () => {
    // 편집된 시퀀스 정보를 localStorage에 저장 (또는 Context API 사용 가능)
    const step2Data = {
      diseaseId,
      diseaseDetail,
      editedSequences,
      originalSequences,
      snvSequences
    };
    localStorage.setItem('step2Data', JSON.stringify(step2Data));
    
    router.push(`/step3?disease_id=${encodeURIComponent(diseaseId || '')}`);
  };

  // 시퀀스에 수정 여부가 있는지 확인 (SNV 적용 서열과 비교)
  const hasEdits = (regionId: string): boolean => {
    // SNV 적용 서열이 없으면 (아직 로드 안됨) 수정 안된 것으로 처리
    if (!snvSequences[regionId]) return false;
    
    // 편집된 시퀀스가 없으면 수정 안됨
    if (!editedSequences[regionId]) return false;
    
    // SNV 적용 서열과 편집된 시퀀스 비교
    return editedSequences[regionId] !== snvSequences[regionId];
  };
  
  // SNV가 있는 region인지 확인
  const hasSNV = (regionId: string): boolean => {
    if (!diseaseDetail?.splice_altering_snv) return false;
    
    const region = diagramRegions.find(r => r.region_id === regionId);
    if (!region) return false;
    
    const snvPos = diseaseDetail.splice_altering_snv.pos_gene0;
    return snvPos >= region.gene_start_idx && snvPos <= region.gene_end_idx;
  };

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

  const snvPosition = getSnvPosition();
  const changedPositions = getChangedPositions();

  return (
    <div className="relative min-h-screen overflow-hidden bg-transparent px-4 py-8 sm:px-6 lg:px-8">
      <div className="relative mx-auto max-w-7xl">
        {/* (1) 제목 */}
        <div className="mb-8 rounded-[24px] border border-white/18 bg-white/5 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          <div className="mb-4 inline-flex rounded-[14px] border border-black/10 bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.32em] text-slate-800">
            Splice Playground
          </div>
          <h1 className="text-4xl font-black tracking-tight text-slate-950 sm:text-5xl">2. Manipulate DNA</h1>
        </div>

        {/* Main Container */}
        <div className="relative rounded-[28px] border border-white/18 bg-white/5 p-5 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          
          {/* (4) 염색체 박스 - 우측 상단 */}
          <div className="absolute right-4 top-4 w-40 rounded-[18px] border border-white/16 bg-white/5 p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
            <div className="flex flex-col items-center">
              {/* 염색체 이미지 (간단한 SVG) */}
              <svg width="60" height="100" viewBox="0 0 60 100" className="mb-2">
                <ellipse cx="30" cy="25" rx="15" ry="20" fill="rgba(255,255,255,0.72)" stroke="rgba(255,255,255,0.9)" strokeWidth="2"/>
                <ellipse cx="30" cy="75" rx="15" ry="20" fill="rgba(255,255,255,0.72)" stroke="rgba(255,255,255,0.9)" strokeWidth="2"/>
                <rect x="25" y="25" width="10" height="50" fill="rgba(255,255,255,0.72)" stroke="rgba(255,255,255,0.9)" strokeWidth="2"/>
                {/* 유전자 위치 표시 */}
                <circle cx="30" cy="50" r="5" fill="#38BDF8" stroke="white" strokeWidth="1"/>
              </svg>
              <p className="text-xs text-center font-semibold text-slate-950">
                {diseaseDetail.gene.chromosome}
              </p>
              <p className="text-xs text-center text-slate-700">
                {diseaseDetail.gene.gene_symbol}
              </p>
            </div>
          </div>

          {/* (2) Exon/Intron 다이어그램 */}
          <div className="mb-8 pr-48">
            {/* 첫번째 줄: 정상 유전자 */}
            <div className="flex items-center gap-4 mb-4">
              <p className="w-36 whitespace-nowrap text-sm font-semibold text-slate-900">{diseaseDetail.gene.gene_symbol} (정상)</p>
              <div className="flex items-center gap-1">
                {diagramRegions.map((region, idx) => (
                  <div key={`normal-${region.region_id}`} className="flex items-center">
                    {region.region_type === 'exon' ? (
                      // Exon: 네모 박스
                      <div className="min-w-28 rounded-xl border border-white/16 bg-white/5 px-8 py-3 text-center shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm">
                        <span className="text-sm font-semibold text-slate-950">Exon{region.region_number}</span>
                      </div>
                    ) : (
                      // Intron: 굵은 선
                      <div className="flex flex-col items-center">
                        <div className="h-1 w-32 rounded-full bg-white/85"></div>
                        <span className="mt-1 text-xs text-slate-700">Intron{region.region_number}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* 두번째 줄: 변이 유전자 (클릭 가능) */}
            <div className="flex items-center gap-4 mt-8">
              <p className="w-36 whitespace-nowrap text-sm font-semibold text-rose-800">{diseaseDetail.gene.gene_symbol} (편집 가능)</p>
              <div className="flex items-center gap-1">
                {diagramRegions.map((region, idx) => (
                  <div key={`mutant-${region.region_id}`} className="flex items-center">
                    {region.region_type === 'exon' ? (
                      // Exon: 클릭 가능한 네모 박스
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
                        {hasSNV(region.region_id) && (
                          <div className="text-xs text-rose-700">SNV</div>
                        )}
                        {hasEdits(region.region_id) && (
                          <div className="text-xs text-amber-700">edited</div>
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
                        <div className={`w-32 rounded-full 
                          ${selectedRegion?.region_id === region.region_id ? 'h-2 bg-cyan-200' : 
                            hasSNV(region.region_id) ? 'h-1 bg-rose-400' : 
                            hasEdits(region.region_id) ? 'h-1 bg-amber-400' : 'h-1 bg-slate-600'}
                        `}></div>
                        <span className={`text-xs mt-1 
                          ${hasSNV(region.region_id) ? 'font-semibold text-rose-700' : 
                            hasEdits(region.region_id) ? 'text-amber-700' : 'text-slate-700'}
                          ${selectedRegion?.region_id === region.region_id ? 'font-semibold text-cyan-700' : ''}
                        `}>
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

          {/* (3) 시퀀스 편집기 */}
          {selectedRegion && (
            <div className="rounded-[20px] border border-cyan-300/25 bg-white/5 p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-lg">
              <div className="flex justify-between items-center mb-2">
                <h3 className="font-bold text-slate-950">
                  {selectedRegion.region_type === 'exon' ? 'Exon' : 'Intron'} {selectedRegion.region_number} 서열 편집
                </h3>
                <span className="text-sm text-slate-700">
                  길이: {currentSequence.length} bp
                </span>
              </div>

              {isRegionLoading ? (
                <div className="flex items-center justify-center h-32">
                  <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
                </div>
              ) : (
                <>
                  {/* 원본 서열 (정상 - ref) */}
                  <div className="mb-4">
                    <p className="mb-1 text-sm font-semibold text-slate-800">정상 서열 (Reference)</p>
                    <div className="max-h-32 overflow-x-auto overflow-y-auto rounded-xl border border-white/16 bg-white/5 p-4 font-mono text-sm text-slate-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
                      {originalSequences[selectedRegion.region_id]?.split('').map((char, idx) => {
                        const editedChar = currentSequence[idx];
                        const isDifferent = char !== editedChar;
                        
                        return (
                          <span
                            key={idx}
                            className={isDifferent ? 'bg-yellow-300 font-bold' : ''}
                          >
                            {char}
                          </span>
                        );
                      }) || '로딩 중...'}
                    </div>
                  </div>

                  {/* 편집 영역 (색상 표시 + 편집 가능) */}
                  <div className="mb-2">
                    <p className="mb-1 text-sm font-semibold text-cyan-800">편집 서열 (클릭하여 수정)</p>
                    <div 
                      className="max-h-48 cursor-text overflow-x-auto overflow-y-auto rounded-xl border border-white/16 bg-white/70 p-4 font-mono text-sm text-slate-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] focus:border-cyan-300 focus:outline-none"
                      contentEditable
                      suppressContentEditableWarning
                      onInput={(e) => {
                        // 커서 위치 정확히 가져오기
                        const selection = window.getSelection();
                        let cursorPosition = 0;
                        
                        if (selection && selection.rangeCount > 0) {
                          const range = selection.getRangeAt(0);
                          const preCaretRange = range.cloneRange();
                          preCaretRange.selectNodeContents(e.currentTarget);
                          preCaretRange.setEnd(range.startContainer, range.startOffset);
                          cursorPosition = preCaretRange.toString().length;
                        }
                        
                        const text = e.currentTarget.textContent || '';
                        handleSequenceChange(text, cursorPosition);
                      }}
                      onBlur={(e) => {
                        const text = e.currentTarget.textContent || '';
                        handleSequenceChange(text);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                        }
                      }}
                      dangerouslySetInnerHTML={{
                        __html: currentSequence.split('').map((char, idx) => {
                          const originalChar = originalSequences[selectedRegion.region_id]?.[idx];
                          const isDifferent = char !== originalChar;
                          
                          if (isDifferent) {
                            return `<span class="bg-yellow-300 font-bold">${char}</span>`;
                          }
                          return char;
                        }).join('')
                      }}
                    />
                  </div>

                  {changedPositions.length > 0 && (
                    <p className="mt-2 text-sm text-rose-800">
                      ⚠️ {changedPositions.length}개 위치가 변경되었습니다
                    </p>
                  )}
                </>
              )}
            </div>
          )}

          {!selectedRegion && (
            <div className="rounded-[20px] border border-dashed border-white/16 bg-white/5 p-8 text-center text-slate-800 backdrop-blur-sm">
              <p>위의 Exon 또는 Intron을 클릭하여 서열을 편집하세요</p>
            </div>
          )}

          {/* (5) Next 버튼 */}
          <div className="flex justify-end mt-8">
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
