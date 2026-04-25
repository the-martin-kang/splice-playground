import Image from 'next/image';
import type { Disease } from './types';

interface DiseaseCardProps {
  disease: Disease;
  isSelected: boolean;
  onSelect: (diseaseId: string) => void;
}

export default function DiseaseCard({ disease, isSelected, onSelect }: DiseaseCardProps) {
  return (
    <button
      key={disease.disease_id}
      onClick={() => onSelect(disease.disease_id)}
      className={`group relative flex min-h-72 flex-col justify-between overflow-hidden rounded-[20px] border p-5 text-left transition-all duration-300 ${
        isSelected
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
  );
}
