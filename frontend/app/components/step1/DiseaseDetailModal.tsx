import type { DiseaseDetail } from './types';

interface DiseaseDetailModalProps {
  diseaseDetail: DiseaseDetail | null;
  isDetailLoading: boolean;
  error: string | null;
  onClose: () => void;
  onNext: () => void;
}

export default function DiseaseDetailModal({
  diseaseDetail,
  isDetailLoading,
  error,
  onClose,
  onNext,
}: DiseaseDetailModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-transparent p-3 sm:p-4">
      <div className="flex max-h-[calc(100vh-2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-[24px] border border-white/18 bg-white/7 shadow-[0_30px_120px_rgba(15,23,42,0.14)] backdrop-blur-lg">
        {isDetailLoading ? (
          <div className="flex h-40 items-center justify-center p-5 sm:p-6">
            <div className="text-center">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
              <p className="mt-2 font-semibold text-slate-950">로딩 중...</p>
            </div>
          </div>
        ) : error ? (
          <div className="p-5 text-center sm:p-6">
            <p className="mb-4 text-rose-900">{error}</p>
            <button
              onClick={onClose}
              className="rounded-[14px] border border-black/10 bg-white/10 px-6 py-2 font-bold text-slate-900 shadow-[0_12px_30px_rgba(15,23,42,0.06)] transition hover:bg-white/12"
            >
              닫기
            </button>
          </div>
        ) : diseaseDetail ? (
          <>
            <div className="overflow-y-auto p-5 [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.45)_rgba(255,255,255,0.08)] sm:p-6 [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-track]:bg-white/10 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:border [&::-webkit-scrollbar-thumb]:border-white/30 [&::-webkit-scrollbar-thumb]:bg-white/45 [&::-webkit-scrollbar-thumb]:backdrop-blur-md [&::-webkit-scrollbar-thumb:hover]:bg-white/65">
              <h2 className="mb-4 text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">
                {diseaseDetail.disease.disease_name}
              </h2>

              {/* Disease Info */}
              <div className="mb-4">
                <h3 className="mb-2 text-base font-bold text-slate-950 sm:text-lg">질병 정보</h3>
                <div className="space-y-1.5 rounded-[18px] border border-white/16 bg-white/5 p-4 text-sm text-slate-800 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
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
              <div className="mb-4">
                <h3 className="mb-2 text-base font-bold text-slate-950 sm:text-lg">유전자 정보</h3>
                <div className="space-y-1.5 rounded-[18px] border border-white/16 bg-white/5 p-4 text-sm text-slate-800 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
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
                <div>
                  <h3 className="mb-2 text-base font-bold text-slate-950 sm:text-lg">Splice Altering SNV</h3>
                  <div className="space-y-1.5 rounded-[18px] border border-white/16 bg-white/5 p-4 text-sm text-slate-800 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
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
            </div>

            {/* Buttons */}
            <div className="flex shrink-0 gap-4 px-5 pb-5 pt-2 sm:px-6 sm:pb-6 sm:pt-3">
              <button
                onClick={onClose}
                className="flex-1 rounded-[14px] border border-black/10 bg-white/10 py-3 font-bold text-slate-900 shadow-[0_14px_35px_rgba(15,23,42,0.06)] transition hover:bg-white/12"
              >
                닫기
              </button>
              <button
                onClick={onNext}
                className="flex-1 rounded-full border border-cyan-300/60 bg-[linear-gradient(135deg,rgba(14,165,233,0.95),rgba(37,99,235,0.92))] py-3 font-bold text-white shadow-[0_18px_45px_rgba(2,132,199,0.35)] transition hover:brightness-105"
              >
                다음 단계
              </button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
