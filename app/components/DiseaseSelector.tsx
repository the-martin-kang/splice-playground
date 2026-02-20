'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';

// 질병 목록 타입 (새 API 구조)
interface Disease {
  disease_id: string;
  disease_name: string;
  description: string | null;
  gene_id: string;
  image_path: string;
  image_url: string;
  image_expires_in: number;
}

// 질병 상세 타입 (새 API 구조)
interface DiseaseDetail {
  disease: {
    disease_id: string;
    disease_name: string;
    description: string | null;
    gene_id: string;
    image_path: string;
    image_url: string;
    image_expires_in: number;
  };
  gene: {
    gene_id: string;
    gene_symbol: string;
    chromosome: string;
    strand: string;
    length: number;
    exon_count: number;
    canonical_transcript_id: string;
    canonical_source: string;
    source_version: string;
  };
  splice_altering_snv: {
    snv_id: string;
    pos_gene0: number;
    ref: string;
    alt: string;
    coordinate: {
      coordinate_system: string;
      assembly: string;
      chromosome: string;
      pos_hg38_1: number;
      genomic_position: string;
    };
    note: string;
    is_representative: boolean;
  } | null;
  target: {
    window: {
      start_gene0: number;
      end_gene0: number;
      label: string;
      chosen_by: string;
      note: string;
    };
    focus_region: {
      region_id: string;
      region_type: string;
      region_number: number;
      gene_start_idx: number;
      gene_end_idx: number;
      length: number;
      sequence: string | null;
    };
    context_regions: Array<{
      region_id: string;
      region_type: string;
      region_number: number;
      gene_start_idx: number;
      gene_end_idx: number;
      length: number;
      sequence: string | null;
      rel: number;
    }>;
    constraints: {
      sequence_alphabet: string[];
      edit_length_must_be_preserved: boolean;
      edit_type: string;
    };
  };
  ui_hints: {
    highlight: {
      type: string;
      pos_gene0: number;
    };
    default_view: string;
  };
}

// FastAPI URL
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export default function DiseaseSelector() {
  const router = useRouter();
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

  const handleNextStep = () => {
    if (selectedDiseaseId && diseaseDetail) {
      // Step 2로 이동하면서 disease_id 전달
      router.push(`/step2?disease_id=${encodeURIComponent(selectedDiseaseId)}`);
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
                  {/* Image Area - 백엔드 image_url 사용 */}
                  <div className="w-full h-40 bg-gray-100 rounded-lg flex items-center justify-center mb-4 overflow-hidden">
                    <Image
                      src={disease.image_url}
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
                      <p>
                        <span className="font-semibold">Gene:</span>{' '}
                        {diseaseDetail.disease.gene_id}
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
                  {diseaseDetail.splice_altering_snv && (
                    <div className="mb-6">
                      <h3 className="text-lg font-bold text-black mb-3">Splice Altering SNV</h3>
                      <div className="space-y-2 text-sm text-black">
                        <p>
                          <span className="font-semibold">위치 (Gene0):</span>{' '}
                          {diseaseDetail.splice_altering_snv.pos_gene0}
                        </p>
                        <p>
                          <span className="font-semibold">Reference:</span>{' '}
                          {diseaseDetail.splice_altering_snv.ref}
                        </p>
                        <p>
                          <span className="font-semibold">Alternate:</span>{' '}
                          {diseaseDetail.splice_altering_snv.alt}
                        </p>
                        <p>
                          <span className="font-semibold">Genomic Position:</span>{' '}
                          {diseaseDetail.splice_altering_snv.coordinate.genomic_position}
                        </p>
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