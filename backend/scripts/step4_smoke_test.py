from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def _join(base: str, path: str) -> str:
    base = base.rstrip('/')
    if not path.startswith('/'):
        path = '/' + path
    return base + path


def _request_json(url: str, *, method: str = 'GET', payload: Optional[Dict[str, Any]] = None, timeout: int = 60) -> Any:
    data = None
    headers = {'accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['content-type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8')
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'{method} {url} failed: {e.code} {e.reason}: {body}') from e


def main() -> int:
    ap = argparse.ArgumentParser(description='Fetch STEP4 state, and optionally create/reuse a STEP4 job if enabled.')
    ap.add_argument('--backend-url', required=True, help='Example: https://api.example.com')
    ap.add_argument('--api-prefix', default='/api')
    ap.add_argument('--state-id', required=True)
    ap.add_argument('--timeout-seconds', type=int, default=3600)
    ap.add_argument('--poll-seconds', type=int, default=10)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--reuse-if-identical', action='store_true', default=True)
    ap.add_argument('--skip-job-create', action='store_true', help='Only verify baseline/STEP4 state payload; do not call the job-creation endpoint.')
    args = ap.parse_args()

    def api(path: str) -> str:
        return _join(args.backend_url, args.api_prefix.rstrip('/') + path)

    print('[STEP4 smoke] Fetching current STEP4 state ...')
    step4 = _request_json(api(f'/states/{args.state_id}/step4?include_sequences=true'))
    user_track = step4.get('user_track') or {}
    normal_track = step4.get('normal_track') or {}
    caps = step4.get('capabilities') or {}
    print(json.dumps({
        'state_id': args.state_id,
        'primary_event_type': (user_track.get('predicted_transcript') or {}).get('primary_event_type'),
        'translation_ok': (user_track.get('translation_sanity') or {}).get('translation_ok'),
        'same_as_normal': (user_track.get('comparison_to_normal') or {}).get('same_as_normal'),
        'recommended_structure_strategy': user_track.get('recommended_structure_strategy'),
        'default_structure_asset_id': normal_track.get('default_structure_asset_id'),
        'molstar_url_present': bool((normal_track.get('molstar_default') or {}).get('url')),
        'structure_prediction_enabled': caps.get('structure_prediction_enabled'),
    }, indent=2))

    if args.skip_job_create:
        return 0

    print('[STEP4 smoke] Creating or reusing STEP4 structure job ...')
    create = _request_json(
        api(f'/states/{args.state_id}/step4/jobs'),
        method='POST',
        payload={'provider': 'colabfold', 'force': args.force, 'reuse_if_identical': args.reuse_if_identical},
    )
    print(json.dumps(create, indent=2)[:4000])
    if not create.get('created'):
        print('[STEP4 smoke] Job creation disabled or no new job created. Treating this as success for CPU-only baseline verification.')
        return 0

    job = create.get('job') or {}
    job_id = job.get('job_id')
    if not job_id:
        print('[STEP4 smoke] No job_id returned.', file=sys.stderr)
        return 2

    deadline = time.time() + args.timeout_seconds
    while True:
        current = _request_json(api(f'/step4-jobs/{job_id}'))
        status = str(current.get('status') or 'unknown')
        print(json.dumps({'job_id': job_id, 'status': status}, indent=2))
        if status in {'succeeded', 'failed', 'canceled'}:
            print(json.dumps({
                'job_id': current.get('job_id'),
                'status': current.get('status'),
                'molstar_default': current.get('molstar_default'),
                'asset_count': len(current.get('assets') or []),
                'comparison_to_normal': current.get('comparison_to_normal'),
                'confidence': current.get('confidence'),
            }, indent=2)[:6000])
            return 0 if status == 'succeeded' else 3
        if time.time() >= deadline:
            print(f'[STEP4 smoke] Timed out waiting for job {job_id}', file=sys.stderr)
            return 4
        time.sleep(args.poll_seconds)


if __name__ == '__main__':
    raise SystemExit(main())
