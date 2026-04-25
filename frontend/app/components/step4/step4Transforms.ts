import type { ActiveStructureView, JobProgress, MolstarTarget, SequenceComparison, Step4StateResponse, Step4StructureComparison, Step4StructureJob, ViewerTargets } from './types';

export function isTerminalJob(job: Step4StructureJob) {
  const normalized = job.status.toLowerCase();
  return (
    !!job.error_message ||
    !!job.molstar_default?.url ||
    ['completed', 'succeeded', 'success', 'failed', 'error', 'cancelled', 'canceled'].includes(normalized)
  );
}

function stableStructureKey(target: MolstarTarget | null) {
  if (!target?.url) return null;
  if (target.structure_asset_id) return `asset:${target.structure_asset_id}`;
  try {
    const parsed = new URL(target.url);
    return `url:${parsed.origin}${parsed.pathname}`;
  } catch {
    return `url:${target.url.split('?')[0]}`;
  }
}

export function mergeMolstarTarget(previous: MolstarTarget | null, next: MolstarTarget | null) {
  if (!next?.url) return previous;
  if (previous && stableStructureKey(previous) === stableStructureKey(next)) {
    return previous;
  }
  return next;
}

export function buildJobProgress(
  job: Step4StructureJob | null,
  step4Data: Step4StateResponse | null,
  userStructureReady: boolean
): JobProgress | null {
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

  if (['failed', 'error', 'cancelled', 'canceled'].includes(status)) {
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

export function progressCardClasses(tone: 'slate' | 'amber' | 'emerald' | 'rose') {
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

export function buildViewerTargets(
  normalStructureTarget: MolstarTarget | null,
  userStructureTarget: MolstarTarget | null,
  comparison: SequenceComparison,
  activeStructureView: ActiveStructureView
): ViewerTargets {
  const normalViewerTarget = normalStructureTarget?.url
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

  const userViewerTarget = overlaySecondary?.url
    ? {
        url: overlaySecondary.url,
        format: overlaySecondary.format || 'mmcif',
        label: overlaySecondary.title || 'User Structure',
        chainId: overlaySecondary.source_chain_id || null,
        color: 0xef4444,
      }
    : null;

  const singleDisplayedTarget =
    activeStructureView === 'user' && userViewerTarget ? userViewerTarget : normalViewerTarget;

  return {
    normalViewerTarget,
    overlaySecondary,
    userViewerTarget,
    singleDisplayedTarget,
  };
}

function hasNumericStructureScore(comparison: Step4StructureComparison | null | undefined) {
  return comparison?.tm_score_1 != null || comparison?.tm_score_2 != null;
}

export function buildStructureComparison(
  job: Step4StructureJob | null,
  frontendStructureComparison: Step4StructureComparison | null,
  comparison: SequenceComparison
): Step4StructureComparison | null {
  const backendComparison = job?.structure_comparison || null;

  if (hasNumericStructureScore(backendComparison)) return backendComparison;
  if (hasNumericStructureScore(frontendStructureComparison)) return frontendStructureComparison;
  if (backendComparison) return backendComparison;
  if (frontendStructureComparison) return frontendStructureComparison;

  return comparison.same_as_normal
    ? {
        method: 'identical-reuse',
        tm_score_1: 1,
        tm_score_2: 1,
        rmsd: 0,
        aligned_length: comparison.user_protein_length,
      }
    : null;
}

export function getStructureScoreDetails(structureComparison: Step4StructureComparison | null) {
  const hasStructureScore =
    structureComparison?.tm_score_1 != null || structureComparison?.tm_score_2 != null;

  const structureSimilarityScore = hasStructureScore
    ? Math.max(structureComparison?.tm_score_1 ?? 0, structureComparison?.tm_score_2 ?? 0)
    : null;
  const structureScoreLabel =
    structureComparison?.method === 'tm-align'
      ? 'TM-score'
      : structureComparison?.method === 'sequence-align'
        ? 'TM-like score'
        : '3D score';

  return {
    hasStructureScore,
    structureSimilarityScore,
    structureScoreLabel,
  };
}
