'use client';

import { Suspense } from 'react';
import DNAManipulator from '../components/DNAManipulator';

function Step2Content() {
  return <DNAManipulator />;
}

export default function Step2Page() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-black"></div>
          <p className="mt-4 text-black font-semibold">로딩 중...</p>
        </div>
      </div>
    }>
      <Step2Content />
    </Suspense>
  );
}