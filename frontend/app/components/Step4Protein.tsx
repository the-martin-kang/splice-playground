'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import MolstarViewer, { MolstarComputedComparison, MolstarStructureInput } from './MolstarViewer';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.splice-playground-api.com';

type StructureStrategy = 'reuse_baseline' | 'predict_user_structure';

interface MolstarTarget {
  structure_asset_id?: string | null;
  provider?: string | null;
  source_db?: string | null;
  source_id?: string | null;
  source_chain_id?: string | null;
  title?: string | null;
  url?: string | null;
  format?: string | null;
}

interface StructureAsset {
  structure_asset_id: string;
  provider: string;
  source_db: string;
  source_id: string;
  source_chain_id?: string | null;
  structure_kind: string;
  title?: string | null;
  method?: string | null;
  resolution_angstrom?: number | null;
  mapped_coverage?: number | null;
  mean_plddt?: number | null;
  file_format: string;
  viewer_format?: string | null;
  is_default?: boolean;
  validation_status: string;
  signed_url?: string | null;
  signed_url_expires_in?: number | null;
}

interface Step4StructureComparison {
  method?: string | null;
  tm_score_1?: number | null;
  tm_score_2?: number | null;
  rmsd?: number | null;
  aligned_length?: number | null;
}

interface Step4StructureJob {
  job_id: string;
  state_id: string;
  provider: string;
  status: string;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  reused_baseline_structure?: boolean;
  molstar_default?: MolstarTarget | null;
  structure_comparison?: Step4StructureComparison | null;
}

interface TranscriptBlock {
  block_id: string;
  block_kind: 'canonical_exon' | 'pseudo_exon' | 'boundary_shift';
  label: string;
  length: number;
  canonical_exon_number?: number | null;
  notes: string[];
}

interface TranslationSanity {
  translation_ok: boolean;
  protein_length?: number;
  cds_length_nt?: number;
  frameshift_likely?: boolean | null;
  premature_stop_likely?: boolean | null;
  stop_codon_found?: boolean;
  multiple_of_three?: boolean;
  notes: string[];
}

interface SequenceComparison {
  same_as_normal: boolean;
  normal_protein_length: number;
  user_protein_length: number;
  length_delta_aa: number;
  first_mismatch_aa_1?: number | null;
  normalized_edit_similarity: number;
  notes: string[];
}

interface BaselineProtein {
  transcript_id: string;
  transcript_kind: string;
  refseq_protein_id?: string | null;
  uniprot_accession?: string | null;
  protein_length: number;
  validation_status: string;
}

interface Step4StateResponse {
  disease_id: string;
  state_id: string;
  gene_id: string;
  gene_symbol?: string | null;
  normal_track: {
    baseline_protein: BaselineProtein;
    structures: StructureAsset[];
    default_structure_asset_id?: string | null;
    default_structure?: StructureAsset | null;
    molstar_default?: MolstarTarget | null;
  };
  user_track: {
    state_id: string;
    representative_snv_applied: boolean;
    predicted_transcript: {
      primary_event_type: string;
      primary_subtype?: string | null;
      blocks: TranscriptBlock[];
      included_exon_numbers: number[];
      excluded_exon_numbers: number[];
      inserted_block_count: number;
      warnings: string[];
    };
    translation_sanity: TranslationSanity;
    comparison_to_normal: SequenceComparison;
    structure_prediction_enabled: boolean;
    structure_prediction_message?: string | null;
    can_reuse_normal_structure: boolean;
    recommended_structure_strategy: StructureStrategy;
    latest_structure_job?: Step4StructureJob | null;
    structure_jobs: Step4StructureJob[];
    warnings: string[];
  };
  capabilities: {
    normal_structure_ready: boolean;
    user_track_available: boolean;
    structure_prediction_enabled: boolean;
    create_job_endpoint_enabled: boolean;
    prediction_mode: 'disabled' | 'job_queue';
    reason?: string | null;
  };
  ready_for_frontend: boolean;
  notes: string[];
}

interface CreateJobResponse {
  created: boolean;
  reused_baseline_structure?: boolean;
  message: string;
  job?: Step4StructureJob | null;
  user_track?: Step4StateResponse['user_track'] | null;
}

function formatError(error: unknown) {
  if (error instanceof Error) return error.message;
  return '요청 중 오류가 발생했습니다.';
}

function formatDateTime(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ko-KR');
}

function formatPercent(value?: number | null) {
  if (value == null || Number.isNaN(value)) return '-';
  return `${Math.round(value * 100)}%`;
}

function formatNumber(value?: number | null, digits = 2) {
  if (value == null || Number.isNaN(value)) return '-';
  return value.toFixed(digits);
}

function statusClassName(status: string) {
  const normalized = status.toLowerCase();
  if (['completed', 'succeeded', 'success'].includes(normalized)) {
    return 'border-emerald-300/40 bg-emerald-100/15 text-emerald-50';
  }
  if (['failed', 'error', 'cancelled'].includes(normalized)) {
    return 'border-rose-300/35 bg-rose-100/10 text-rose-900';
  }
  return 'border-amber-300/35 bg-amber-100/10 text-amber-900';
}

function isTerminalJob(job: Step4StructureJob) {
  const normalized = job.status.toLowerCase();
  return (
    !!job.error_message ||
    !!job.molstar_default?.url ||
    ['completed', 'succeeded', 'success', 'failed', 'error', 'cancelled'].includes(normalized)
  );
}

function extractApiMessage(payload: unknown) {
  if (typeof payload === 'string') return payload;
  if (
    payload &&
    typeof payload === 'object' &&
    'detail' in payload &&
    typeof (payload as { detail?: unknown }).detail === 'string'
  ) {
    return (payload as { detail: string }).detail;
  }
  if (
    payload &&
    typeof payload === 'object' &&
    'message' in payload &&
    typeof (payload as { message?: unknown }).message === 'string'
  ) {
    return (payload as { message: string }).message;
  }
  return null;
}

function mergeMolstarTarget(previous: MolstarTarget | null, next: MolstarTarget | null) {
  if (!next?.url) return previous;
  if (
    previous &&
    previous.structure_asset_id &&
    next.structure_asset_id &&
    previous.structure_asset_id === next.structure_asset_id
  ) {
    return previous;
  }
  return next;
}

function buildJobProgress(
  job: Step4StructureJob | null,
  step4Data: Step4StateResponse | null,
  userStructureReady: boolean
) {
  if (!step4Data) return null;
  if (!step4Data.capabilities.structure_prediction_enabled) {
    return {
      tone: 'slate' as const,
      title: '구조 예측이 현재 비활성화되어 있습니다.',
      body:
        step4Data.user_track.structure_prediction_message ||
        step4Data.capabilities.reason ||
        '현재는 정상 구조만 표시합니다.',
    };
  }

  if (!job) {
    if (step4Data.user_track.recommended_structure_strategy === 'reuse_baseline') {
      return {
        tone: 'emerald' as const,
        title: '정상 구조를 그대로 재사용합니다.',
        body: '현재 생성된 단백질이 정상 단백질과 동일해 추가 ColabFold 예측이 필요하지 않습니다.',
      };
    }
    return {
      tone: 'amber' as const,
      title: 'ColabFold 예측 대기 중',
      body: '구조 예측 job이 아직 생성되지 않았습니다. 보통 1~2분 정도 걸리며, 단백질이 길면 더 오래 걸릴 수 있습니다.',
    };
  }

  const status = job.status.toLowerCase();
  const startedAt = job.created_at ? new Date(job.created_at).getTime() : null;
  const elapsedSeconds = startedAt ? Math.max(0, Math.round((Date.now() - startedAt) / 1000)) : null;
  const elapsedText = elapsedSeconds != null ? `경과 ${elapsedSeconds}s` : null;

  if (userStructureReady || ['succeeded', 'completed', 'success'].includes(status)) {
    return {
      tone: 'emerald' as const,
      title: 'ColabFold 예측이 완료되었습니다.',
      body: '정상 구조와 생성 구조를 서로 다른 색으로 overlay해 비교할 수 있습니다.',
      meta: elapsedText,
    };
  }

  if (['failed', 'error', 'cancelled'].includes(status)) {
    return {
      tone: 'rose' as const,
      title: 'ColabFold 예측이 실패했습니다.',
      body: job.error_message || 'worker 로그를 확인해 주세요.',
      meta: elapsedText,
    };
  }

  if (status === 'running') {
    return {
      tone: 'amber' as const,
      title: 'ColabFold가 단백질 구조를 예측 중입니다…',
      body: '현재 Mol* 창은 정상 구조를 유지합니다. 예측이 끝나면 새 구조를 자동으로 overlay 비교 모드로 보여줍니다. 보통 1~2분 정도 걸리며, 큰 단백질은 더 오래 걸릴 수 있습니다.',
      meta: elapsedText,
      spinning: true,
    };
  }

  return {
    tone: 'amber' as const,
    title: '예측 job이 큐에 들어가 있습니다.',
    body: 'worker가 구조 예측을 시작하면 상태가 running으로 바뀝니다. 보통 1~2분 정도 걸릴 수 있습니다.',
    meta: elapsedText,
    spinning: true,
  };
}

function progressCardClasses(tone: 'slate' | 'amber' | 'emerald' | 'rose') {
  switch (tone) {
    case 'emerald':
      return 'border-emerald-300/30 bg-emerald-100/10 text-emerald-950';
    case 'rose':
      return 'border-rose-300/30 bg-rose-100/10 text-rose-950';
    case 'amber':
      return 'border-amber-300/30 bg-amber-100/10 text-amber-950';
    default:
      return 'border-black/10 bg-white/10 text-slate-900';
  }
}

export default function Step4Protein() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const diseaseId = searchParams.get('disease_id');
  const stateId = searchParams.get('state_id');

  const [step4Data, setStep4Data] = useState<Step4StateResponse | null>(null);
  const [job, setJob] = useState<Step4StructureJob | null>(null);
  const [diseaseName, setDiseaseName] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [jobMessage, setJobMessage] = useState<string | null>(null);
  const [isSubmittingJob, setIsSubmittingJob] = useState(false);
  const [hasAutoSubmittedJob, setHasAutoSubmittedJob] = useState(false);
  const [activeStructureView, setActiveStructureView] = useState<'normal' | 'user' | 'overlay'>('normal');
  const [frontendStructureComparison, setFrontendStructureComparison] = useState<Step4StructureComparison | null>(null);
  const [stableNormalTarget, setStableNormalTarget] = useState<MolstarTarget | null>(null);
  const [stableUserTarget, setStableUserTarget] = useState<MolstarTarget | null>(null);
  const hasInitializedViewRef = useRef(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem('step3Data');
      if (!saved) return;
      const parsed = JSON.parse(saved) as { diseaseDetail?: { disease?: { disease_name?: string } } };
      setDiseaseName(parsed.diseaseDetail?.disease?.disease_name || null);
    } catch {
      setDiseaseName(null);
    }
  }, []);

  const handleComputedComparison = useCallback((nextComparison: MolstarComputedComparison | null) => {
    if (!nextComparison) {
      setFrontendStructureComparison(null);
      return;
    }
    setFrontendStructureComparison({
      method: nextComparison.method,
      tm_score_1: nextComparison.tm_score_1 ?? null,
      tm_score_2: nextComparison.tm_score_2 ?? null,
      rmsd: nextComparison.rmsd ?? null,
      aligned_length: nextComparison.aligned_length ?? null,
    });
  }, []);

  const fetchStep4 = async (showLoading = true) => {
    if (!stateId) return;
    if (showLoading) setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/states/${encodeURIComponent(stateId)}/step4?include_sequences=false`
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(extractApiMessage(payload) || `HTTP error! status: ${response.status}`);
      }

      const data = payload as Step4StateResponse;
      setStep4Data(data);
      setJob((prev) => data.user_track.latest_structure_job || prev);
      setStableNormalTarget((prev) => mergeMolstarTarget(prev, data.normal_track.molstar_default || null));
      setStableUserTarget((prev) =>
        mergeMolstarTarget(prev, data.user_track.latest_structure_job?.molstar_default || null)
      );

      if (!hasInitializedViewRef.current) {
        setActiveStructureView('normal');
        hasInitializedViewRef.current = true;
      }
    } catch (fetchError) {
      setError(formatError(fetchError));
    } finally {
      if (showLoading) setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!diseaseId || !stateId) {
      setError('step4에 필요한 disease_id 또는 state_id가 없습니다.');
      setIsLoading(false);
      return;
    }
    void fetchStep4(true);
  }, [diseaseId, stateId]);

  const createStructureJob = async () => {
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
      if (payload?.user_track && step4Data) {
        setStep4Data({ ...step4Data, user_track: payload.user_track });
      }
      if (payload?.job) {
        setJob(payload.job);
        setStableUserTarget((prev) => mergeMolstarTarget(prev, payload.job?.molstar_default || null));
      }
    } catch (submitError) {
      setJobError(formatError(submitError));
    } finally {
      setIsSubmittingJob(false);
    }
  };

  useEffect(() => {
    if (!step4Data) return;
    if (job) return;
    if (hasAutoSubmittedJob) return;
    if (!step4Data.capabilities.create_job_endpoint_enabled) return;
    if (step4Data.user_track.recommended_structure_strategy !== 'predict_user_structure') return;

    setHasAutoSubmittedJob(true);
    void createStructureJob();
  }, [step4Data, job, hasAutoSubmittedJob]);

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
      } catch (pollError) {
        setJobError(formatError(pollError));
      }
    }, 8000);

    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status, job?.error_message, job?.molstar_default?.url]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-transparent px-4">
        <div className="w-full max-w-md rounded-[24px] border border-white/18 bg-white/5 p-10 text-center shadow-[0_30px_120px_rgba(15,23,42,0.16)] backdrop-blur-lg">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-2 border-white/25 border-b-white"></div>
          <p className="mt-4 font-semibold text-slate-950">Step 4 데이터를 불러오는 중...</p>
        </div>
      </div>
    );
  }

  if (error || !step4Data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-transparent px-4">
        <div className="w-full max-w-md rounded-[24px] border border-white/18 bg-white/5 p-10 text-center shadow-[0_30px_120px_rgba(15,23,42,0.16)] backdrop-blur-lg">
          <p className="mb-4 text-rose-900">{error || 'Step 4 데이터를 불러올 수 없습니다.'}</p>
          <button
            onClick={() => router.push('/select-mutant')}
            className="rounded-[14px] border border-black/10 bg-white/10 px-6 py-2 font-bold text-slate-900 shadow-[0_12px_30px_rgba(15,23,42,0.06)] transition hover:bg-white/12"
          >
            Step 1로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  const comparison = step4Data.user_track.comparison_to_normal;
  const translation = step4Data.user_track.translation_sanity;
  const normalStructureTarget = stableNormalTarget;
  const userStructureTarget = stableUserTarget;

  const normalViewerTarget: MolstarStructureInput | null = normalStructureTarget?.url
    ? {
        url: normalStructureTarget.url,
        format: normalStructureTarget.format || 'mmcif',
        label: normalStructureTarget.title || 'Normal Structure',
        chainId: normalStructureTarget.source_chain_id || null,
        color: 0x22c55e,
      }
    : null;

  const overlaySecondary = userStructureTarget?.url
    ? userStructureTarget
    : comparison.same_as_normal && normalStructureTarget?.url
      ? { ...normalStructureTarget, title: 'User Structure (baseline reuse)' }
      : null;

  const userViewerTarget: MolstarStructureInput | null = overlaySecondary?.url
    ? {
        url: overlaySecondary.url,
        format: overlaySecondary.format || 'mmcif',
        label: overlaySecondary.title || 'User Structure',
        chainId: overlaySecondary.source_chain_id || null,
        color: 0xef4444,
      }
    : null;

  const structureComparison =
    job?.structure_comparison ||
    frontendStructureComparison ||
    (comparison.same_as_normal
      ? {
          method: 'identical-reuse',
          tm_score_1: 1,
          tm_score_2: 1,
          rmsd: 0,
          aligned_length: comparison.user_protein_length,
        }
      : null);

  const structureSimilarityScore = structureComparison
    ? Math.max(structureComparison.tm_score_1 ?? 0, structureComparison.tm_score_2 ?? 0)
    : null;

  const singleDisplayedTarget =
    activeStructureView === 'user' && userViewerTarget ? userViewerTarget : normalViewerTarget;

  const progress = buildJobProgress(job, step4Data, Boolean(userViewerTarget?.url));

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-transparent px-4 py-8 pb-16 sm:px-6 lg:px-8">
      <div className="relative mx-auto max-w-7xl space-y-8">
        <section className="rounded-[24px] border border-white/18 bg-white/5 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-8">
          <div className="mb-4 inline-flex rounded-[14px] border border-black/10 bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.32em] text-slate-800">
            Splice Playground
          </div>
          <h1 className="text-4xl font-black tracking-tight text-slate-950 sm:text-5xl">4. Protein Structure</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-800 sm:text-base">
            {diseaseName || step4Data.disease_id}의 정상 단백질 구조와 사용자 편집 상태에서 예측된 단백질 결과를 비교합니다.
          </p>
          <div className="mt-6 flex flex-wrap gap-3 text-xs text-slate-800">
            <span className="rounded-[12px] border border-black/10 bg-white/10 px-3 py-1">Gene: {step4Data.gene_symbol || step4Data.gene_id}</span>
            <span className="rounded-[12px] border border-black/10 bg-white/10 px-3 py-1">State: {step4Data.state_id}</span>
            <span className="rounded-[12px] border border-black/10 bg-white/10 px-3 py-1">Strategy: {step4Data.user_track.recommended_structure_strategy}</span>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-[18px] border border-white/16 bg-white/5 p-5 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-600">Normal Protein</p>
            <p className="mt-3 text-3xl font-black text-slate-950">{comparison.normal_protein_length}<span className="ml-2 text-sm font-semibold text-slate-600">aa</span></p>
          </div>
          <div className="rounded-[18px] border border-white/16 bg-white/5 p-5 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-600">User Protein</p>
            <p className="mt-3 text-3xl font-black text-slate-950">{comparison.user_protein_length}<span className="ml-2 text-sm font-semibold text-slate-600">aa</span></p>
          </div>
          <div className="rounded-[18px] border border-white/16 bg-white/5 p-5 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-600">Length Delta</p>
            <p className="mt-3 text-3xl font-black text-slate-950">{comparison.length_delta_aa > 0 ? '+' : ''}{comparison.length_delta_aa}<span className="ml-2 text-sm font-semibold text-slate-600">aa</span></p>
          </div>
          <div className="rounded-[18px] border border-white/16 bg-white/5 p-5 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-600">Structure Similarity</p>
            <p className="mt-3 text-3xl font-black text-slate-950">{formatPercent(structureSimilarityScore)}</p>
            <p className="mt-2 text-xs text-slate-600">TM-score max 기준 · AA 유사도 {formatPercent(comparison.normalized_edit_similarity)}</p>
          </div>
        </section>

        <section className="grid gap-8 xl:grid-cols-[1.5fr_0.9fr]">
          <div className="rounded-[24px] border border-white/18 bg-white/5 p-5 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-lg sm:p-6">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl font-black text-slate-950">Mol* Structure Viewer</h2>
                <p className="mt-1 text-sm text-slate-800">정상 구조는 초록, 생성 구조는 빨강으로 표시하며, overlay 모드에서는 브라우저에서 TM-align으로 직접 겹쳐 비교합니다.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setActiveStructureView('normal')}
                  className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${activeStructureView === 'normal' ? 'border-cyan-300/60 bg-cyan-100/12 text-cyan-900' : 'border-black/10 bg-white/10 text-slate-800 hover:bg-white/12'}`}
                >
                  Normal Structure
                </button>
                <button
                  onClick={() => setActiveStructureView('user')}
                  disabled={!userViewerTarget}
                  className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${activeStructureView === 'user' && userViewerTarget ? 'border-cyan-300/60 bg-cyan-100/12 text-cyan-900' : 'border-black/10 bg-white/10 text-slate-800 hover:bg-white/12 disabled:cursor-not-allowed disabled:opacity-40'}`}
                >
                  User Structure
                </button>
                <button
                  onClick={() => setActiveStructureView('overlay')}
                  disabled={!normalViewerTarget || !userViewerTarget}
                  className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${activeStructureView === 'overlay' && normalViewerTarget && userViewerTarget ? 'border-fuchsia-300/60 bg-fuchsia-100/12 text-fuchsia-900' : 'border-black/10 bg-white/10 text-slate-800 hover:bg-white/12 disabled:cursor-not-allowed disabled:opacity-40'}`}
                >
                  Overlay Compare
                </button>
              </div>
            </div>

            {activeStructureView === 'overlay' && normalViewerTarget && userViewerTarget ? (
              <MolstarViewer mode="overlay" primary={normalViewerTarget} secondary={userViewerTarget} onComputedComparison={handleComputedComparison} />
            ) : (
              <MolstarViewer mode="single" primary={singleDisplayedTarget} onComputedComparison={handleComputedComparison} />
            )}

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div className="rounded-[18px] border border-white/16 bg-white/5 p-4 text-sm text-slate-800">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-600">Displayed Asset</p>
                <p className="mt-2 font-semibold text-slate-950">
                  {activeStructureView === 'overlay'
                    ? 'Normal + User overlay'
                    : singleDisplayedTarget?.label || '구조 자산 없음'}
                </p>
                <p className="mt-2 text-slate-700">
                  {activeStructureView === 'overlay'
                    ? 'TM-align based superposition'
                    : `${activeStructureView === 'user' ? userStructureTarget?.provider || '-' : normalStructureTarget?.provider || '-'} / ${activeStructureView === 'user' ? userStructureTarget?.source_db || '-' : normalStructureTarget?.source_db || '-'}`}
                </p>
                <p className="mt-1 text-slate-700">
                  {activeStructureView === 'overlay'
                    ? `${normalStructureTarget?.source_id || '-'} vs ${overlaySecondary?.source_id || '-'}`
                    : (activeStructureView === 'user' ? userStructureTarget?.source_id : normalStructureTarget?.source_id) || '-'}
                  {activeStructureView !== 'overlay' && (activeStructureView === 'user' ? userStructureTarget?.source_chain_id : normalStructureTarget?.source_chain_id)
                    ? ` · Chain ${activeStructureView === 'user' ? userStructureTarget?.source_chain_id : normalStructureTarget?.source_chain_id}`
                    : ''}
                </p>
              </div>
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
            </div>
          </div>

          <div className="space-y-6">
            <section className="rounded-[24px] border border-white/18 bg-white/5 p-5 shadow-[0_24px_70px_rgba(15,23,42,0.10)] backdrop-blur-lg xl:max-h-[calc(100vh-6rem)] xl:overflow-y-auto">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-black text-slate-950">Translation Summary</h2>
                  <p className="mt-2 text-sm text-slate-800">STEP4 API의 `translation_sanity`, job status, 구조 비교 결과를 함께 요약합니다.</p>
                </div>
                <button
                  onClick={() => fetchStep4(false)}
                  className="rounded-[14px] border border-black/10 bg-white/10 px-4 py-2 text-sm font-semibold text-slate-800 transition hover:bg-white/12"
                >
                  Refresh
                </button>
              </div>

              {progress ? (
                <div className={`mt-5 rounded-2xl border px-4 py-4 ${progressCardClasses(progress.tone)}`}>
                  <div className="flex items-start gap-3">
                    {progress.spinning ? <div className="mt-0.5 h-5 w-5 animate-spin rounded-full border-2 border-current/25 border-b-current" /> : null}
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold">{progress.title}</p>
                      <p className="mt-2 text-sm leading-6">{progress.body}</p>
                      {progress.meta ? <p className="mt-2 text-xs opacity-80">{progress.meta}</p> : null}
                    </div>
                  </div>
                </div>
              ) : null}

              <div className="mt-5 space-y-3 text-sm text-slate-800">
                <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>Translation OK</span><span className="font-semibold">{translation.translation_ok ? 'Yes' : 'No'}</span></div>
                <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>Frameshift Likely</span><span className="font-semibold">{translation.frameshift_likely ? 'Yes' : 'No'}</span></div>
                <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>Premature Stop</span><span className="font-semibold">{translation.premature_stop_likely ? 'Yes' : 'No'}</span></div>
                <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>First AA Mismatch</span><span className="font-semibold">{comparison.first_mismatch_aa_1 ?? '-'}</span></div>
                <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>CDS Length</span><span className="font-semibold">{translation.cds_length_nt ?? '-'} nt</span></div>
                <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>AA Similarity</span><span className="font-semibold">{formatPercent(comparison.normalized_edit_similarity)}</span></div>
                <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>3D Similarity (TM-score max)</span><span className="font-semibold">{formatPercent(structureSimilarityScore)}</span></div>
              </div>

              {(jobMessage || jobError) && (
                <div className="mt-5 space-y-3">
                  {jobMessage ? <div className="rounded-2xl border border-emerald-300/25 bg-emerald-100/10 px-4 py-3 text-sm text-emerald-900">{jobMessage}</div> : null}
                  {jobError ? <div className="rounded-2xl border border-rose-300/25 bg-rose-100/10 px-4 py-3 text-sm text-rose-900">{jobError}</div> : null}
                </div>
              )}

              {step4Data.user_track.recommended_structure_strategy === 'predict_user_structure' && !userViewerTarget ? (
                <div className="mt-5">
                  <button
                    onClick={createStructureJob}
                    disabled={isSubmittingJob}
                    className="w-full rounded-full border border-cyan-300/60 bg-[linear-gradient(135deg,rgba(14,165,233,0.95),rgba(37,99,235,0.92))] px-6 py-3 text-sm font-bold text-white shadow-[0_18px_45px_rgba(2,132,199,0.35)] transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isSubmittingJob ? 'Predicting Structure...' : 'Run User Structure Prediction'}
                  </button>
                </div>
              ) : null}
            </section>

            <section className="rounded-[24px] border border-white/18 bg-white/5 p-5 shadow-[0_24px_70px_rgba(15,23,42,0.10)] backdrop-blur-lg">
              <h2 className="text-xl font-black text-slate-950">Transcript Blocks</h2>
              <div className="mt-4 flex max-h-[280px] flex-wrap gap-2 overflow-y-auto pr-1">
                {step4Data.user_track.predicted_transcript.blocks.map((block) => (
                  <div
                    key={block.block_id}
                    className={`rounded-full border px-3 py-2 text-xs font-semibold ${block.block_kind === 'pseudo_exon' ? 'border-amber-300/35 bg-amber-100/10 text-amber-900' : 'border-white/14 bg-white/5 text-slate-800'}`}
                  >
                    {block.label} · {block.length} nt
                  </div>
                ))}
              </div>
            </section>

            {structureComparison ? (
              <section className="rounded-[24px] border border-white/18 bg-white/5 p-5 shadow-[0_24px_70px_rgba(15,23,42,0.10)] backdrop-blur-lg">
                <h2 className="text-xl font-black text-slate-950">Structure Comparison (3D)</h2>
                {structureComparison?.method ? <div className="mb-3 rounded-xl border border-white/12 bg-white/5 px-4 py-3 text-xs text-slate-700">Method: {structureComparison.method}</div> : null}
                <div className="mt-4 space-y-3 text-sm text-slate-800">
                  <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>TM-score 1</span><span className="font-semibold">{formatNumber(structureComparison.tm_score_1, 3)}</span></div>
                  <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>TM-score 2</span><span className="font-semibold">{formatNumber(structureComparison.tm_score_2, 3)}</span></div>
                  <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>RMSD</span><span className="font-semibold">{formatNumber(structureComparison.rmsd, 3)}</span></div>
                  <div className="flex items-center justify-between rounded-xl border border-white/12 bg-white/5 px-4 py-3"><span>Aligned Length</span><span className="font-semibold">{structureComparison.aligned_length ?? '-'}</span></div>
                </div>
              </section>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}
