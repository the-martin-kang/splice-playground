'use client';

import { useRouter } from 'next/navigation';
import DiseaseCard from './DiseaseCard';
import DiseaseDetailModal from './DiseaseDetailModal';
import Step1Header from './Step1Header';
import { useDiseases } from './useDiseases';

export default function Step1DiseaseSelector() {
  // LOGIC: route transition and API-backed selection state for Step 1.
  const router = useRouter();
  const {
    diseases,
    selectedDiseaseId,
    diseaseDetail,
    isListLoading,
    isDetailLoading,
    error,
    handleSelectDisease,
    handleCloseModal,
  } = useDiseases();

  const handleNextStep = () => {
    if (selectedDiseaseId && diseaseDetail) {
      // Step 2로 이동하면서 disease_id 전달
      router.push(`/step2?disease_id=${encodeURIComponent(selectedDiseaseId)}`);
    }
  };

  // UI: Step 1 screen, disease card grid, loading/error states, and detail modal.
  return (
    <div className="relative min-h-screen overflow-hidden bg-transparent px-4 py-8 sm:px-6 lg:px-8">
      <div className="relative mx-auto max-w-6xl">
        {/* Header */}
        <Step1Header />

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
                <DiseaseCard
                  key={disease.disease_id}
                  disease={disease}
                  isSelected={selectedDiseaseId === disease.disease_id}
                  onSelect={handleSelectDisease}
                />
              ))}
            </div>
          )}
        </div>

        {/* Detail Modal */}
        {selectedDiseaseId && (
          <DiseaseDetailModal
            diseaseDetail={diseaseDetail}
            isDetailLoading={isDetailLoading}
            error={error}
            onClose={handleCloseModal}
            onNext={handleNextStep}
          />
        )}
      </div>
    </div>
  );
}
