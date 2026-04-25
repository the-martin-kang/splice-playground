'use client';

import { useCallback, useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { extractApiMessage, formatError } from './step4Formatters';
import { isTerminalJob, mergeMolstarTarget } from './step4Transforms';
import type { CreateJobResponse, MolstarTarget, Step4StateResponse, Step4StructureJob } from './types';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.splice-playground-api.com';

export function useStructureJob(
  stateId: string | null,
  step4Data: Step4StateResponse | null,
  setStableUserTarget: Dispatch<SetStateAction<MolstarTarget | null>>,
  refreshStep4?: (showLoading?: boolean) => Promise<void>
) {
  const [job, setJob] = useState<Step4StructureJob | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [jobMessage, setJobMessage] = useState<string | null>(null);
  const [isSubmittingJob, setIsSubmittingJob] = useState(false);
  const [hasAutoSubmittedJob, setHasAutoSubmittedJob] = useState(false);

  useEffect(() => {
    if (!step4Data) return;
    setJob((prev) => step4Data.user_track.latest_structure_job || prev);
  }, [step4Data]);

  // LOGIC: create a user structure prediction job through the backend.
  const createStructureJob = useCallback(async () => {
    if (!stateId) return;
    setIsSubmittingJob(true);
    setJobError(null);
    setJobMessage(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/states/${encodeURIComponent(stateId)}/step4/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: 'colabfold', force: false, reuse_if_identical: true }),
      });

      const payload = (await response.json().catch(() => null)) as CreateJobResponse | null;
      if (!response.ok) {
        throw new Error(extractApiMessage(payload) || `HTTP error! status: ${response.status}`);
      }

      if (payload?.message) setJobMessage(payload.message);
      const nextJob = payload?.job || payload?.user_track?.latest_structure_job || null;
      if (nextJob) {
        setJob(nextJob);
        setStableUserTarget((prev) => mergeMolstarTarget(prev, nextJob.molstar_default || null));
      }
      if (payload?.user_track || nextJob?.molstar_default?.url) {
        await refreshStep4?.(false);
      }
    } catch (submitError) {
      setJobError(formatError(submitError));
    } finally {
      setIsSubmittingJob(false);
    }
  }, [stateId, setStableUserTarget, refreshStep4]);

  // LOGIC: automatically create a prediction job when backend strategy requires it.
  useEffect(() => {
    if (!step4Data) return;
    if (job || step4Data.user_track.latest_structure_job) return;
    if (hasAutoSubmittedJob) return;
    if (!step4Data.capabilities.create_job_endpoint_enabled) return;
    if (step4Data.user_track.recommended_structure_strategy !== 'predict_user_structure') return;

    setHasAutoSubmittedJob(true);
    void createStructureJob();
  }, [step4Data, job, hasAutoSubmittedJob, createStructureJob]);

  // LOGIC: poll an in-progress structure prediction job until it becomes terminal.
  useEffect(() => {
    if (!job?.job_id || isTerminalJob(job)) return;

    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/step4-jobs/${encodeURIComponent(job.job_id)}?include_payload=false`
        );
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(extractApiMessage(payload) || `HTTP error! status: ${response.status}`);
        }
        const refreshedJob = payload as Step4StructureJob;
        setJob((prev) => ({ ...(prev || {}), ...refreshedJob } as Step4StructureJob));
        if (refreshedJob.molstar_default?.url) {
          setStableUserTarget((prev) => mergeMolstarTarget(prev, refreshedJob.molstar_default || null));
        }
        if (isTerminalJob(refreshedJob)) {
          await refreshStep4?.(false);
        }
      } catch (pollError) {
        setJobError(formatError(pollError));
      }
    }, 8000);

    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status, job?.error_message, job?.molstar_default?.url, setStableUserTarget, refreshStep4]);

  return {
    job,
    jobError,
    jobMessage,
    isSubmittingJob,
    createStructureJob,
  };
}
