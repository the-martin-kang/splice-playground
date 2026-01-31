'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';

interface Disease {
  disease_id: string;
  disease_name: string;
  image_url?: string;
}

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

// 이미지 매핑 (public/images 폴더의 이미지)
const DISEASE_IMAGES: { [key: string]: string } = {
  'CFTR_seed': '/images/CFTR.jpeg',
  'DNM1_seed': '/images/DNM1.png',
  'MSH2_seed': '/images/MSH2.png',
  'PMM2_seed': '/images/PMM2.png',
  'SMN_seed': '/images/SMN_SMA.png',
  'TSC2_seed': '/images/TSC2.png',
};

// FastAPI URL (환경 변수에서 읽음)
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function DiseaseSelector() {
  const [diseases, setDiseases] = useState<Disease[]>([]);
  const [selectedDisease, setSelectedDisease] = useState<Disease | null>(null);
  const [diseaseDetail, setDiseaseDetail] = useState<DiseaseDetail | null>(null);
  const [isListLoading, setIsListLoading] = useState(true);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 1-1) 질병 목록 조회 (FastAPI)
  useEffect(() => {
    const fetchDiseases = async () => {
      setIsListLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/api/diseases`);
        
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        setDiseases(data.items || []);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : '질병 목록을 불러올 수 없습니다';
        setError(errorMessage);
        console.error('Error fetching diseases:', err);
      } finally {
        setIsListLoading(false);
      }
    };

    fetchDiseases();
  }, []);

  // 1-2) 질병 상세 조회 (FastAPI)
  const handleSelectDisease = async (disease: Disease) => {
    setSelectedDisease(disease);
    setDiseaseDetail(null);
    setIsDetailLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/diseases/${disease.disease_id}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      setDiseaseDetail(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '질병 상세 정보를 불러올 수 없습니다';
      setError(errorMessage);
      console.error('Error fetching disease details:', err);
    } finally {
      setIsDetailLoading(false);
    }
  };

  const handleNextStep = () => {
    if (selectedDisease && diseaseDetail) {
      // Step 2로 데이터 전달
      console.log('다음 단계로 진행:', selectedDisease, diseaseDetail);
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

        {/* Error Message */}
        {error && (
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
                  onClick={() => handleSelectDisease(disease)}
                  className={`border-4 rounded-2xl p-6 transition-all duration-200 flex flex-col items-center justify-center min-h-64 ${
                    selectedDisease?.disease_id === disease.disease_id
                      ? 'border-black bg-gray-50'
                      : 'border-black hover:bg-gray-50'
                  }`}
                >
                  {/* Image Area */}
                  <div className="w-full h-40 bg-gray-100 rounded-lg flex items-center justify-center mb-4 overflow-hidden">
                    <Image
                      src={DISEASE_IMAGES[disease.disease_id] || '/images/default.jpg'}
                      alt={disease.disease_name}
                      width={200}
                      height={160}
                      className="w-full h-full object-cover"
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
        {selectedDisease && diseaseDetail && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl border-4 border-black max-w-2xl w-full p-8 max-h-96 overflow-y-auto">
              <h2 className="text-3xl font-bold text-black mb-6">
                {diseaseDetail.disease.disease_name}
              </h2>

              {isDetailLoading ? (
                <div className="flex items-center justify-center h-40">
                  <div className="text-center">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-black"></div>
                    <p className="mt-2 text-black font-semibold">로딩 중...</p>
                  </div>
                </div>
              ) : (
                <>
                  {/* Disease Info */}
                  <div className="mb-6">
                    <h3 className="text-lg font-bold text-black mb-3">질병 정보</h3>
                    <div className="space-y-2 text-sm text-black">
                      <p>
                        <span className="font-semibold">ID:</span> {diseaseDetail.disease.disease_id}
                      </p>
                      {diseaseDetail.disease.description && (
                        <p>
                          <span className="font-semibold">설명:</span> {diseaseDetail.disease.description}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Gene Info */}
                  <div className="mb-6">
                    <h3 className="text-lg font-bold text-black mb-3">유전자 정보</h3>
                    <div className="space-y-2 text-sm text-black">
                      <p>
                        <span className="font-semibold">기호:</span> {diseaseDetail.gene.gene_symbol}
                      </p>
                      <p>
                        <span className="font-semibold">염색체:</span> {diseaseDetail.gene.chromosome}
                      </p>
                      <p>
                        <span className="font-semibold">Strand:</span> {diseaseDetail.gene.strand}
                      </p>
                      <p>
                        <span className="font-semibold">길이:</span> {diseaseDetail.gene.length.toLocaleString()} bp
                      </p>
                      <p>
                        <span className="font-semibold">Exon 수:</span> {diseaseDetail.gene.exon_count}
                      </p>
                    </div>
                  </div>

                  {/* SNV Info */}
                  <div className="mb-6">
                    <h3 className="text-lg font-bold text-black mb-3">Seed SNV</h3>
                    <div className="space-y-2 text-sm text-black">
                      <p>
                        <span className="font-semibold">위치 (Gene0):</span> {diseaseDetail.seed_snv.pos_gene0}
                      </p>
                      <p>
                        <span className="font-semibold">Reference:</span> {diseaseDetail.seed_snv.ref}
                      </p>
                      <p>
                        <span className="font-semibold">Alternate:</span> {diseaseDetail.seed_snv.alt}
                      </p>
                      {diseaseDetail.seed_snv.note && (
                        <p>
                          <span className="font-semibold">노트:</span> {diseaseDetail.seed_snv.note}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Buttons */}
                  <div className="flex gap-4">
                    <button
                      onClick={() => setSelectedDisease(null)}
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
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}