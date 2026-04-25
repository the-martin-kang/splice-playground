export default function Step1Header() {
  return (
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
  );
}
