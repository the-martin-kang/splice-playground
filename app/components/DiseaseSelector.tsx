'use client';

import { useState } from 'react';
import Image from 'next/image';

interface DiseaseDetail {
  disease: {
    disease_id: string;
    disease_name: string;
    description: string | null;
  };
  gene: {
    gene_id: string;
    gene_symbol: string;
    chromosome: string;
    strand: string;
    length: number;
    exon_count: number;
  };
  seed_snv: {
    pos_gene0: number;
    ref: string;
    alt: string;
    note: string | null;
  };
}

// 질병 목록 (하드코딩 — API 없이 화면에 바로 표시)
const DISEASE_LIST = [
  {
    disease_id: 'CFTR_seed',
    disease_name: 'Cystic Fibrosis (CFTR)',
    image_url: '/images/CFTR.jpeg',
  },
  {
    disease_id: 'DNM1_seed',
    disease_name: 'Epileptic Encephalopathy (DNM1)',
    image_url: '/images/DNM1.png',
  },
  {
    disease_id: 'MSH2_seed',
    disease_name: 'Lynch Syndrome (MSH2)',
    image_url: '/images/MSH2.png',
  },
  {
    disease_id: 'PMM2_seed',
    disease_name: 'CDG Syndrome (PMM2)',
    image_url: '/images/PMM2.png',
  },
  {
    disease_id: 'SMN_seed',
    disease_name: 'Spinal Muscular Atrophy (SMN)',
    image_url: '/images/SMN_SMA.png',
  },
  {
    disease_id: 'TSC2_seed',
    disease_name: 'Tuberous Sclerosis (TSC2)',
    image_url: '/images/TSC2.png',
  },
];

// ✅ FastAPI Base URL (환경 변수에서 읽음)
// .env.local: NEXT_PUBLIC_API_BASE_URL=https://mmnamcwi3y.ap-northeast-1.awsapprunner.com
const RAW_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
// 끝에 / 붙어도 안전하게
const API_BASE_URL = RAW_BASE_URL.replace(/\/$/, '');

export default function DiseaseSelector() {
  const [selectedDiseaseId, setSelectedDiseaseId] = useState<string | null>(null);
  const [diseaseDetail, setDiseaseDetail] = useState<DiseaseDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 클릭 시에만 API 호출 — 질병 상세 조회
  const handleSelectDisease = async (diseaseId: string) => {
    setSelectedDiseaseId(diseaseId);
    setDiseaseDetail(null);
    setIsDetailLoading(true);
    setError(null);

    try {
      // ✅ v1 포함된 실제 백엔드 스펙으로 호출
      const response = await fetch(
        `${API_BASE_URL}/api/v1/diseases/${diseaseId}`
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
      console.log('다음 단계로 진행:', selectedDiseaseId, diseaseDetail);
      // 나중에: router.push('/step2') 또는 Context API로 상태 전달
    }
  };

  return (
    <div className="min-h-screen bg-white p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-12">
          <h1 className="text-5xl font-bold text-black mb-2">1. Select Mutant</h1>
        </div>

        {/* Main Container */}
        <div className="border-4 border-black rounded-3xl p-8 bg-white">
          {/* Disease Grid — 하드코딩된 목록을 바로 렌더링 */}
          <div className="grid grid-cols-3 gap-6 mb-8">
            {DISEASE_LIST.map((disease, idx) => (
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
                <div className="relative w-full h-40 bg-gray-100 rounded-lg flex items-center justify-center mb-4 overflow-hidden">
                  <Image
                    src={disease.image_url}
                    alt={disease.disease_name}
                    fill
                    className="object-cover"
                    sizes="(max-width: 768px) 100vw, 33vw"
                    // 첫 화면에 크게 보이는 이미지는 LCP일 수 있어서 첫 카드만 priority
                    priority={idx === 0}
                  />
                </div>

                {/* Title */}
                <p className="text-center font-semibold text-black text-sm">
                  {disease.disease_name}
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* Detail Modal — 클릭 후 API 응답 표시 */}
        {selectedDiseaseId && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl border-4 border-black max-w-2xl w-full p-8 max-h-96 overflow-y-auto">
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
                    </div>
                  </div>

                  {/* SNV Info */}
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

                  {/* Buttons */}
                  <div className="flex gap-4">
                    <button
                      onClick={handleCloseModal}
                      className="flex-1 border-3 border-black rounded-lg py-2 font-bold text-black hover:bg-gray-100 transition"
                    >
                      닫기
                    </button>
                    <button
                      onClick={handleNextStep}
                      className="flex-1 border-3 border-black bg-black text-white rounded-lg py-2 font-bold hover:bg-gray-900 transition"
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
