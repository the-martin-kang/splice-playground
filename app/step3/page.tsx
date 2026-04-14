'use client';

import { Suspense } from 'react';
import MatureMRNA from '../components/MatureMRNA';

function Loading() {
  return (
    <div className="min-h-screen bg-white flex items-center justify-center">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-black"></div>
        <p className="mt-4 text-black font-semibold">로딩 중...</p>
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