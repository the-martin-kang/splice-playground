import { formatDateTime, statusClassName } from './step4Formatters';
import type { Step4StructureJob } from './types';

interface PredictionJobCardProps {
  job: Step4StructureJob | null;
}

export default function PredictionJobCard({ job }: PredictionJobCardProps) {
  return (
    <div className="rounded-[18px] border border-white/16 bg-white/5 p-4 text-sm text-slate-800">
      <p className="text-xs uppercase tracking-[0.24em] text-slate-600">Prediction Job</p>
      {job ? (
        <>
          <div className={`mt-2 inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${statusClassName(job.status)}`}>{job.status}</div>
          <p className="mt-3 text-slate-700">Provider: {job.provider}</p>
          <p className="mt-1 text-slate-700">Updated: {formatDateTime(job.updated_at)}</p>
          {job.reused_baseline_structure ? <p className="mt-3 text-emerald-800">정상 구조를 재사용하도록 판단된 job입니다.</p> : null}
        </>
      ) : (
        <p className="mt-2 text-slate-700">아직 사용자 구조 job이 없습니다. 예측 가능하면 자동으로 생성합니다.</p>
      )}
    </div>
  );
}
