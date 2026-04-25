export function formatError(error: unknown) {
  if (error instanceof Error) return error.message;
  return '요청 중 오류가 발생했습니다.';
}

export function formatDateTime(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ko-KR');
}

export function formatPercent(value?: number | null) {
  if (value == null || Number.isNaN(value)) return '-';
  return `${Math.round(value * 100)}%`;
}

export function formatNumber(value?: number | null, digits = 2) {
  if (value == null || Number.isNaN(value)) return '-';
  return value.toFixed(digits);
}

export function statusClassName(status: string) {
  const normalized = status.toLowerCase();
  if (['completed', 'succeeded', 'success'].includes(normalized)) {
    return 'border-emerald-300/40 bg-emerald-100/15 text-emerald-50';
  }
  if (['failed', 'error', 'cancelled', 'canceled'].includes(normalized)) {
    return 'border-rose-300/35 bg-rose-100/10 text-rose-900';
  }
  return 'border-amber-300/35 bg-amber-100/10 text-amber-900';
}

export function extractApiMessage(payload: unknown) {
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
