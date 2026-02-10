'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';

// 질병 목록 타입
interface Disease {
  disease_id: string;
  disease_name: string;
  description: string | null;
  image_path: string;
}

// 질병 상세 타입
interface DiseaseDetail {
  disease: {
    disease_id: string;
    disease_name: string;
    description: string | null;
    image_path: string;
  };
  gene: {
    gene_id: string;
    gene_symbol: string;
    chromosome: string;
    strand: string;
    length: number;
    exon_count: number;
    canonical_source: string;
    canonical_transcript_id: string;
    source_version: string;
  };
  seed_snv: {
    pos_gene0: number;
    ref: string;
    alt: string;
    note: string | null;
  } | null;
}

// FastAPI URL (환경 변수에서 읽음)
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

// 이미지 하드코딩 (백엔드 준비 전까지 임시)
const DISEASE_IMAGES: { [key: string]: string } = {
  'CFTR_gene0_109442_A>G': '/images/CFTR.jpeg',
  'DNM1_gene0_22648_G>A': '/images/DNM1.png',
  'MSH2_gene0_4856_T>G': '/images/MSH2.png',
  'PMM2_gene0_34406_C>T': '/images/PMM2.png',
  'SMN1_gene0_27005_C>T': '/images/SMN_SMA.png',
  'TSC2_gene0_9474_C>T': '/images/TSC2.png',
};

export default function DiseaseSelector() {
  const [diseases, setDiseases] = useState<Disease[]>([]);
  const [selectedDiseaseId, setSelectedDiseaseId] = useState<string | null>(null);
  const [diseaseDetail, setDiseaseDetail] = useState<DiseaseDetail | null>(null);
  const [isListLoading, setIsListLoading] = useState(true);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 1. 질병 목록 조회 - GET /api/v1/diseases/
  useEffect(() => {
    const fetchDiseases = async () => {
      setIsListLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/diseases/`);

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

  // 2. 질병 상세 조회 - GET /api/v1/diseases/{disease_id}
  const handleSelectDisease = async (diseaseId: string) => {
    setSelectedDiseaseId(diseaseId);
    setDiseaseDetail(null);
    setIsDetailLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/diseases/${encodeURIComponent(diseaseId)}`
      );

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

  const handleNextStep = () => {
    if (selectedDiseaseId && diseaseDetail) {
      // Step 2로 데이터 전달
      console.log('다음 단계로 진행:', selectedDiseaseId, diseaseDetail);
      // 나중에: router.push('/step2') 또는 Context API로 상태 전달
    }
  };

  // 이미지 URL 생성 (하드코딩 우선, 없으면 백엔드 경로)
  const getImageUrl = (diseaseId: string, imagePath: string) => {
    return DISEASE_IMAGES[diseaseId] || `${API_BASE_URL}${imagePath}`;
  };

  return (
    <div className="min-h-screen bg-white p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-12">
          <h1 className="text-5xl font-bold text-black mb-2">1. Select Mutant</h1>
        </div>

        {/* Error Message */}
        {error && !selectedDiseaseId && (
          <div className="mb-6 bg-red-100 border border-red-400 rounded-lg p-4">
            <p className="text-red-800">{error}</p>
          </div>
        )}

        {/* Main Container */}
        <div className="border-4 border-black rounded-3xl p-8 bg-white">
          {/* Disease Grid */}
          {isListLoading ? (
            <div className="flex items-center justify-center h-96">
              <div className="text-center">
                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-black"></div>
                <p className="mt-4 text-black font-semibold">질병 목록 로딩 중...</p>
              </div>
            </div>
          ) : diseases.length === 0 ? (
            <div className="flex items-center justify-center h-96">
              <p className="text-black text-lg">질병 목록을 불러올 수 없습니다</p>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-6 mb-8">
              {diseases.map((disease) => (
                <button
                  key={disease.disease_id}
                  onClick={() => handleSelectDisease(disease.disease_id)}
                  className={`border-4 rounded-2xl p-6 transition-all duration-200 flex flex-col items-center justify-center min-h-64 ${
                    selectedDiseaseId === disease.disease_id
                      ? 'border-black bg-gray-50'
                      : 'border-black hover:bg-gray-50'
                  }`}
                >
                  {/* Image Area */}
                  <div className="w-full h-40 bg-gray-100 rounded-lg flex items-center justify-center mb-4 overflow-hidden">
                    <Image
                      src={getImageUrl(disease.disease_id, disease.image_path)}
                      alt={disease.disease_name}
                      width={200}
                      height={160}
                      className="w-full h-full object-cover"
                      unoptimized
                    />
                  </div>

                  {/* Title */}
                  <p className="text-center font-semibold text-black text-sm">
                    {disease.disease_name}
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Detail Modal */}
        {selectedDiseaseId && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl border-4 border-black max-w-2xl w-full p-8 max-h-[80vh] overflow-y-auto">
              {isDetailLoading ? (
                <div className="flex items-center justify-center h-40">
                  <div className="text-center">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-black"></div>
                    <p className="mt-2 text-black font-semibold">로딩 중...</p>
                  </div>
                </div>
              ) : error ? (
                <div className="text-center">
                  <p className="text-red-600 mb-4">{error}</p>
                  <button
                    onClick={handleCloseModal}
                    className="border-2 border-black rounded-lg px-6 py-2 font-bold text-black hover:bg-gray-100 transition"
                  >
                    닫기
                  </button>
                </div>
              ) : diseaseDetail ? (
                <>
                  <h2 className="text-3xl font-bold text-black mb-6">
                    {diseaseDetail.disease.disease_name}
                  </h2>

                  {/* Disease Info */}
                  <div className="mb-6">
                    <h3 className="text-lg font-bold text-black mb-3">질병 정보</h3>
                    <div className="space-y-2 text-sm text-black">
                      <p>
                        <span className="font-semibold">ID:</span>{' '}
                        {diseaseDetail.disease.disease_id}
                      </p>
                      {diseaseDetail.disease.description && (
                        <p>
                          <span className="font-semibold">설명:</span>{' '}
                          {diseaseDetail.disease.description}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Gene Info */}
                  <div className="mb-6">
                    <h3 className="text-lg font-bold text-black mb-3">유전자 정보</h3>
                    <div className="space-y-2 text-sm text-black">
                      <p>
                        <span className="font-semibold">기호:</span>{' '}
                        {diseaseDetail.gene.gene_symbol}
                      </p>
                      <p>
                        <span className="font-semibold">염색체:</span>{' '}
                        {diseaseDetail.gene.chromosome}
                      </p>
                      <p>
                        <span className="font-semibold">Strand:</span>{' '}
                        {diseaseDetail.gene.strand}
                      </p>
                      <p>
                        <span className="font-semibold">길이:</span>{' '}
                        {diseaseDetail.gene.length.toLocaleString()} bp
                      </p>
                      <p>
                        <span className="font-semibold">Exon 수:</span>{' '}
                        {diseaseDetail.gene.exon_count}
                      </p>
                      <p>
                        <span className="font-semibold">Canonical Source:</span>{' '}
                        {diseaseDetail.gene.canonical_source}
                      </p>
                      <p>
                        <span className="font-semibold">Transcript ID:</span>{' '}
                        {diseaseDetail.gene.canonical_transcript_id}
                      </p>
                      <p>
                        <span className="font-semibold">Source Version:</span>{' '}
                        {diseaseDetail.gene.source_version}
                      </p>
                    </div>
                  </div>

                  {/* SNV Info */}
                  {diseaseDetail.seed_snv && (
                    <div className="mb-6">
                      <h3 className="text-lg font-bold text-black mb-3">Seed SNV</h3>
                      <div className="space-y-2 text-sm text-black">
                        <p>
                          <span className="font-semibold">위치 (Gene0):</span>{' '}
                          {diseaseDetail.seed_snv.pos_gene0}
                        </p>
                        <p>
                          <span className="font-semibold">Reference:</span>{' '}
                          {diseaseDetail.seed_snv.ref}
                        </p>
                        <p>
                          <span className="font-semibold">Alternate:</span>{' '}
                          {diseaseDetail.seed_snv.alt}
                        </p>
                        {diseaseDetail.seed_snv.note && (
                          <p>
                            <span className="font-semibold">노트:</span>{' '}
                            {diseaseDetail.seed_snv.note}
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Buttons */}
                  <div className="flex gap-4">
                    <button
                      onClick={handleCloseModal}
                      className="flex-1 border-2 border-black rounded-lg py-2 font-bold text-black hover:bg-gray-100 transition"
                    >
                      닫기
                    </button>
                    <button
                      onClick={handleNextStep}
                      className="flex-1 border-2 border-black bg-black text-white rounded-lg py-2 font-bold hover:bg-gray-900 transition"
                    >
                      다음 단계
                    </button>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}