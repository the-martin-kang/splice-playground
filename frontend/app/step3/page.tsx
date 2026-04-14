'use client';

import { Suspense } from 'react';
import MatureMRNA from '../components/MatureMRNA';

function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-transparent px-4">
      <div className="w-full max-w-md rounded-[24px] border border-white/18 bg-white/5 p-10 text-center shadow-[0_30px_120px_rgba(15,23,42,0.16)] backdrop-blur-lg">
        <div className="inline-block h-12 w-12 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
        <p className="mt-4 font-semibold text-slate-950">로딩 중...</p>
      </div>
    </div>
  );
}

export default function Step3Page() {
  return (
    <Suspense fallback={<Loading />}>
      <MatureMRNA />
    </Suspense>
  );
}
