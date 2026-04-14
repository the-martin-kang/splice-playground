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
    <div className="relative min-h-screen overflow-hidden bg-transparent px-4 py-8 sm:px-6 lg:px-8">
      <div className="relative mx-auto max-w-6xl">
        {/* Header */}
        <div className="mb-10 rounded-[24px] border border-white/18 bg-white/5 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          <div className="mb-4 inline-flex rounded-[14px] border border-black/10 bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.32em] text-slate-800 shadow-[0_10px_30px_rgba(15,23,42,0.04)]">
            Splice Playground
          </div>
          <h1 className="mb-2 text-4xl font-black tracking-tight text-slate-950 sm:text-5xl">
            1. Select Mutant
          </h1>
          <p className="max-w-2xl text-sm leading-6 text-slate-800 sm:text-base">
            질병 카드를 선택해 변이와 유전자 정보를 확인한 뒤 다음 단계로 진행합니다.
          </p>
        </div>

        {/* Error Message */}
        {error && !selectedDiseaseId && (
          <div className="mb-6 rounded-xl border border-rose-300/30 bg-rose-100/12 p-4 shadow-[0_18px_45px_rgba(225,29,72,0.08)] backdrop-blur-sm">
            <p className="text-sm font-medium text-rose-900">{error}</p>
          </div>
        )}

        {/* Main Container */}
        <div className="rounded-[28px] border border-white/18 bg-white/5 p-5 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          {/* Disease Grid */}
          {isListLoading ? (
            <div className="flex h-96 items-center justify-center rounded-[20px] border border-white/16 bg-white/5 backdrop-blur-sm">
              <div className="text-center">
                <div className="inline-block h-12 w-12 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
                <p className="mt-4 font-semibold text-slate-950">질병 목록 로딩 중...</p>
              </div>
            </div>
          ) : diseases.length === 0 ? (
            <div className="flex h-96 items-center justify-center rounded-[20px] border border-white/16 bg-white/5 backdrop-blur-sm">
              <p className="text-lg font-medium text-slate-950">질병 목록을 불러올 수 없습니다</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {diseases.map((disease) => (
                <button
                  key={disease.disease_id}
                  onClick={() => handleSelectDisease(disease.disease_id)}
                  className={`group relative flex min-h-72 flex-col justify-between overflow-hidden rounded-[20px] border p-5 text-left transition-all duration-300 ${
                    selectedDiseaseId === disease.disease_id
                      ? 'border-white/22 bg-white/8 shadow-[0_24px_70px_rgba(15,23,42,0.14)] ring-1 ring-cyan-300/40 backdrop-blur-lg'
                      : 'border-white/16 bg-white/5 shadow-[0_18px_55px_rgba(15,23,42,0.08)] backdrop-blur-sm hover:-translate-y-1 hover:border-white/22 hover:bg-white/8 hover:shadow-[0_30px_80px_rgba(15,23,42,0.12)]'
                  }`}
                >
                  <div className="pointer-events-none absolute inset-x-5 top-0 h-24 rounded-b-[32px] bg-gradient-to-b from-white/20 to-transparent" />

                  {/* Image Area - 백엔드 image_url 사용 */}
                  <div className="relative mb-5 h-44 w-full overflow-hidden rounded-[16px] border border-white/16 bg-white/5 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
                    <Image
                      src={disease.image_url}
                      alt={disease.disease_name}
                      width={200}
                      height={160}
                      className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
                      unoptimized
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-slate-950/30 via-transparent to-white/5" />
                  </div>

                  {/* Title */}
                  <div className="relative">
                    <div className="mb-3 inline-flex rounded-[12px] border border-black/10 bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-800">
                      {disease.gene_id}
                    </div>
                    <p className="text-lg font-bold leading-snug text-slate-950">
                      {disease.disease_name}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Detail Modal */}
        {selectedDiseaseId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-transparent p-4">
            <div className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-[24px] border border-white/18 bg-white/7 p-6 shadow-[0_30px_120px_rgba(15,23,42,0.14)] backdrop-blur-lg sm:p-8">
              {isDetailLoading ? (
                <div className="flex items-center justify-center h-40">
                  <div className="text-center">
                    <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
                    <p className="mt-2 font-semibold text-slate-950">로딩 중...</p>
                  </div>
                </div>
              ) : error ? (
                <div className="text-center">
                  <p className="mb-4 text-rose-900">{error}</p>
                  <button
                    onClick={handleCloseModal}
                    className="rounded-[14px] border border-black/10 bg-white/10 px-6 py-2 font-bold text-slate-900 shadow-[0_12px_30px_rgba(15,23,42,0.06)] transition hover:bg-white/12"
                  >
                    닫기
                  </button>
                </div>
              ) : diseaseDetail ? (
                <>
                  <h2 className="mb-6 text-3xl font-black tracking-tight text-slate-950">
                    {diseaseDetail.disease.disease_name}
                  </h2>

                  {/* Disease Info */}
                  <div className="mb-6">
                    <h3 className="mb-3 text-lg font-bold text-slate-950">질병 정보</h3>
                    <div className="space-y-2 rounded-[18px] border border-white/16 bg-white/5 p-5 text-sm text-slate-800 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
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
                    <h3 className="mb-3 text-lg font-bold text-slate-950">유전자 정보</h3>
                    <div className="space-y-2 rounded-[18px] border border-white/16 bg-white/5 p-5 text-sm text-slate-800 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
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
                      <h3 className="mb-3 text-lg font-bold text-slate-950">Splice Altering SNV</h3>
                      <div className="space-y-2 rounded-[18px] border border-white/16 bg-white/5 p-5 text-sm text-slate-800 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
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
                      className="flex-1 rounded-[14px] border border-black/10 bg-white/10 py-3 font-bold text-slate-900 shadow-[0_14px_35px_rgba(15,23,42,0.06)] transition hover:bg-white/12"
                    >
                      닫기
                    </button>
                    <button
                      onClick={handleNextStep}
                      className="flex-1 rounded-full border border-cyan-300/60 bg-[linear-gradient(135deg,rgba(14,165,233,0.95),rgba(37,99,235,0.92))] py-3 font-bold text-white shadow-[0_18px_45px_rgba(2,132,199,0.35)] transition hover:brightness-105"
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
