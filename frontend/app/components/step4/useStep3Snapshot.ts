'use client';

import { useEffect, useState } from 'react';
import type { Step3Snapshot, Step3SummaryState } from './types';

export function useStep3Snapshot(): Step3SummaryState {
  const [diseaseName, setDiseaseName] = useState<string | null>(null);
  const [step3AffectedExons, setStep3AffectedExons] = useState<number[]>([]);
  const [step3EventHeadline, setStep3EventHeadline] = useState<string | null>(null);
  const [step3AffectedSummary, setStep3AffectedSummary] = useState<string | null>(null);

  // LOGIC: read Step 3 snapshot from localStorage to enrich the Step 4 summary UI.
  useEffect(() => {
    try {
      const saved = localStorage.getItem('step3Data');
      if (!saved) return;
      const parsed = JSON.parse(saved) as Step3Snapshot & { diseaseDetail?: { disease?: { disease_name?: string } } };
      setDiseaseName(parsed.diseaseDetail?.disease?.disease_name || null);
      setStep3AffectedExons(parsed.affectedExons || []);
      setStep3EventHeadline(
        parsed.splicingResult?.frontend_summary?.headline || parsed.eventSummary || null
      );
      const summaries = (parsed.splicingResult?.interpreted_events || [])
        .map(event => event.summary)
        .filter((value): value is string => Boolean(value));
      setStep3AffectedSummary(summaries.length ? summaries.join(' ') : null);
    } catch {
      setDiseaseName(null);
      setStep3AffectedExons([]);
      setStep3EventHeadline(null);
      setStep3AffectedSummary(null);
    }
  }, []);

  return {
    diseaseName,
    step3AffectedExons,
    step3EventHeadline,
    step3AffectedSummary,
  };
}
