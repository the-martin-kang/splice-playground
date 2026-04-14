# STEP4 Frontend Handoff Spec (Mol* Integration)

## 목적
이 문서는 프론트엔드가 STEP4 응답을 읽어 정상(normal) 단백질 구조를 Mol*로 표시하고,
향후 GPU worker가 붙었을 때 user structure prediction까지 자연스럽게 확장할 수 있도록
백엔드 응답 계약(contract)과 UI 동작 규칙을 정리한 명세서다.

현재 배포 상태는 **CPU-only baseline mode** 이다.
즉:
- 정상 구조(normal track)는 즉시 표시 가능
- user structure prediction(ColabFold job)은 아직 비활성화
- 프론트는 baseline structure만 표시하고, 예측 버튼은 disabled 처리해야 함

---

## 1. 엔드포인트

### STEP4 메인 응답
`GET /api/states/{state_id}/step4?include_sequences=true`

예시:
`GET https://api.splice-playground-api.com/api/states/<STATE_ID>/step4?include_sequences=true`

---

## 2. 프론트가 반드시 읽어야 하는 필드

### 최상위
- `ready_for_frontend: boolean`
- `capabilities.normal_structure_ready: boolean`
- `capabilities.structure_prediction_enabled: boolean`
- `capabilities.create_job_endpoint_enabled: boolean`
- `capabilities.prediction_mode: string`
- `capabilities.reason: string | null`
- `notes: string[]`

### normal track
- `normal_track.baseline_protein`
- `normal_track.default_structure`
- `normal_track.molstar_default`
- `normal_track.structures`

### user track
- `user_track.predicted_transcript`
- `user_track.translation_sanity`
- `user_track.comparison_to_normal`
- `user_track.protein_seq`
- `user_track.cds_seq`
- `user_track.cdna_seq`
- `user_track.structure_prediction_enabled`
- `user_track.structure_prediction_message`
- `user_track.can_reuse_normal_structure`
- `user_track.recommended_structure_strategy`
- `user_track.latest_structure_job`
- `user_track.structure_jobs`
- `user_track.warnings`

---

## 3. normal structure 표시 규칙

프론트는 normal structure를 표시할 때 **항상 `normal_track.molstar_default`를 1순위 source of truth로 사용**한다.

### 사용 필드
- `normal_track.molstar_default.url`
- `normal_track.molstar_default.format`
- `normal_track.molstar_default.title`
- `normal_track.molstar_default.source_id`
- `normal_track.molstar_default.source_chain_id`

### 의미
- `url`: Supabase signed URL
- `format`: Mol*에 넘길 파일 포맷. 현재는 `mmcif`
- `title`: 카드/헤더 표시용
- `source_id`: 예: `8rb1`
- `source_chain_id`: 예: `A`

### 현재 기본 규칙
- `ready_for_frontend === true`
- `capabilities.normal_structure_ready === true`
- `normal_track.molstar_default.url` 존재

이 세 조건이 만족되면 Mol* viewer를 렌더한다.

---

## 4. user structure prediction 버튼 규칙

현재 CPU-only 서버에서는 아래처럼 처리한다.

### 버튼 활성화 조건
```ts
const canPredictUserStructure =
  step4.capabilities.structure_prediction_enabled &&
  step4.capabilities.create_job_endpoint_enabled;
```

### 현재 배포에서 기대값
- `capabilities.structure_prediction_enabled = false`
- `capabilities.create_job_endpoint_enabled = false`
- `user_track.structure_prediction_enabled = false`

### 현재 UI 동작
- 예측 버튼은 disabled
- helper text는 `user_track.structure_prediction_message ?? capabilities.reason` 표시
- baseline structure만 보여 줌

---

## 5. 추천 UI 구성

### STEP4 화면 2-track

#### A. Normal track (읽기 전용)
표시 항목:
- protein name / gene symbol
- transcript id
- UniProt accession
- protein length
- validation status
- default structure title
- Mol* viewer (normal structure)

권장 데이터 소스:
- `gene_symbol`
- `normal_track.baseline_protein.transcript_id`
- `normal_track.baseline_protein.uniprot_accession`
- `normal_track.baseline_protein.protein_length`
- `normal_track.baseline_protein.validation_status`
- `normal_track.default_structure.title`
- `normal_track.molstar_default`

#### B. User track
표시 항목:
- primary event type
- included / excluded exons
- translation sanity
- same as normal 여부
- 추천 구조 전략
- user protein length
- warning badge

권장 데이터 소스:
- `user_track.predicted_transcript.primary_event_type`
- `user_track.predicted_transcript.primary_subtype`
- `user_track.predicted_transcript.included_exon_numbers`
- `user_track.predicted_transcript.excluded_exon_numbers`
- `user_track.translation_sanity.translation_ok`
- `user_track.translation_sanity.frameshift_likely`
- `user_track.translation_sanity.premature_stop_likely`
- `user_track.comparison_to_normal.same_as_normal`
- `user_track.recommended_structure_strategy`
- `user_track.warnings`

---

## 6. 현재 상태에서 프론트가 해석해야 하는 핵심 규칙

### 케이스 1. `same_as_normal = true`
이 경우:
- user protein이 normal protein과 동일
- 새 구조 예측을 굳이 돌릴 필요 없음
- 프론트는 normal Mol* viewer를 그대로 사용
- user 카드에는 `recommended_structure_strategy = reuse_baseline` 배지 표시

### 케이스 2. `same_as_normal = false` 이지만 prediction disabled
이 경우:
- user protein은 바뀌었지만 아직 GPU worker가 없음
- normal structure는 계속 보여줌
- user 영역에는 “구조 예측 준비 중” 상태 표시
- 버튼 disabled

### 케이스 3. 나중에 GPU worker가 붙었을 때
이 경우:
- `capabilities.structure_prediction_enabled = true`
- 예측 버튼 enabled
- `POST /api/states/{state_id}/step4/jobs` 호출
- 이후 `latest_structure_job` / `structure_jobs` polling

---

## 7. TypeScript 타입(권장 최소형)

```ts
export type MolstarStructureRef = {
  structure_asset_id: string;
  provider: string;
  source_db: string;
  source_id: string;
  source_chain_id: string | null;
  title: string;
  url: string;
  format: 'mmcif' | 'pdb' | string;
};

export type Step4Response = {
  disease_id: string;
  state_id: string;
  gene_id: string;
  gene_symbol: string;
  normal_track: {
    baseline_protein: {
      protein_reference_id: string;
      transcript_id: string;
      uniprot_accession: string | null;
      protein_length: number;
      validation_status: string;
    };
    default_structure_asset_id: string | null;
    default_structure: {
      structure_asset_id: string;
      title: string;
      provider: string;
      source_db: string;
      source_id: string;
      source_chain_id: string | null;
      structure_kind: string;
      viewer_format: string;
      validation_status: string;
      mapped_coverage: number | null;
      resolution_angstrom: number | null;
      mean_plddt: number | null;
      signed_url: string;
    } | null;
    molstar_default: MolstarStructureRef | null;
    structures: Array<{
      structure_asset_id: string;
      title: string;
      provider: string;
      source_db: string;
      source_id: string;
      source_chain_id: string | null;
      structure_kind: string;
      viewer_format: string;
      validation_status: string;
      mapped_coverage: number | null;
      resolution_angstrom: number | null;
      mean_plddt: number | null;
      signed_url: string;
      is_default: boolean;
    }>;
  };
  user_track: {
    predicted_transcript: {
      primary_event_type: string | null;
      primary_subtype: string | null;
      included_exon_numbers: number[];
      excluded_exon_numbers: number[];
      blocks: Array<{
        block_id: string;
        block_kind: string;
        label: string;
        canonical_exon_number?: number;
        gene_start_idx: number;
        gene_end_idx: number;
        length: number;
        cdna_start_1?: number;
        cdna_end_1?: number;
      }>;
      warnings: string[];
    };
    translation_sanity: {
      translation_ok: boolean;
      start_codon_preserved: boolean;
      stop_codon_found: boolean;
      multiple_of_three: boolean;
      frameshift_likely: boolean;
      premature_stop_likely: boolean;
      protein_length: number;
    };
    comparison_to_normal: {
      same_as_normal: boolean;
      normal_protein_length: number;
      user_protein_length: number;
      first_mismatch_aa_1: number | null;
      normalized_edit_similarity: number;
    };
    protein_seq?: string;
    cds_seq?: string;
    cdna_seq?: string;
    structure_prediction_enabled: boolean;
    structure_prediction_message: string | null;
    can_reuse_normal_structure: boolean;
    recommended_structure_strategy: string | null;
    latest_structure_job: unknown | null;
    structure_jobs: unknown[];
    warnings: string[];
  };
  capabilities: {
    normal_structure_ready: boolean;
    user_track_available: boolean;
    structure_prediction_enabled: boolean;
    create_job_endpoint_enabled: boolean;
    prediction_mode: string;
    reason: string | null;
  };
  ready_for_frontend: boolean;
  notes: string[];
};
```

---

## 8. 프론트에서 실제로 사용하는 최소 데이터 매핑

### 카드 헤더
```ts
const header = {
  gene: step4.gene_symbol,
  transcriptId: step4.normal_track.baseline_protein.transcript_id,
  uniprot: step4.normal_track.baseline_protein.uniprot_accession,
  proteinLength: step4.normal_track.baseline_protein.protein_length,
  validation: step4.normal_track.baseline_protein.validation_status,
};
```

### Mol* 로더 입력
```ts
const molstarInput = step4.normal_track.molstar_default
  ? {
      url: step4.normal_track.molstar_default.url,
      format: step4.normal_track.molstar_default.format,
      title: step4.normal_track.molstar_default.title,
    }
  : null;
```

### user summary
```ts
const userSummary = {
  eventType: step4.user_track.predicted_transcript.primary_event_type,
  eventSubtype: step4.user_track.predicted_transcript.primary_subtype,
  translationOk: step4.user_track.translation_sanity.translation_ok,
  sameAsNormal: step4.user_track.comparison_to_normal.same_as_normal,
  strategy: step4.user_track.recommended_structure_strategy,
  warnings: step4.user_track.warnings,
};
```

---

## 9. Mol* 연결 방식

### 권장 방식
프론트는 Mol*를 **arbitrary URL + format** 형태로 로드해야 한다.
왜냐하면 백엔드가 signed Supabase URL을 내려주고 있고, 현재 source는 PDB id가 아니라 **signed asset URL** 이기 때문이다.

즉 프론트는 `pdb=...` 식이 아니라:
- `url = normal_track.molstar_default.url`
- `format = normal_track.molstar_default.format`

을 사용해야 한다.

### 현재 format
- `mmcif`

---

## 10. React 예시 (Mol* 직접 임베드)

```tsx
import { useEffect, useRef } from 'react';
import { createPluginUI } from 'molstar/lib/mol-plugin-ui';
import { renderReact18 } from 'molstar/lib/mol-plugin-ui/react18';
import 'molstar/lib/mol-plugin-ui/skin/light.scss';

type Props = {
  url: string;
  format: 'mmcif' | 'pdb' | string;
};

export function MolstarStructureViewer({ url, format }: Props) {
  const parentRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let disposed = false;
    let plugin: any;

    async function init() {
      if (!parentRef.current) return;

      plugin = await createPluginUI({
        target: parentRef.current,
        render: renderReact18,
      });

      const data = await plugin.builders.data.download(
        { url },
        { state: { isGhost: true } }
      );

      const trajectory = await plugin.builders.structure.parseTrajectory(
        data,
        format
      );

      await plugin.builders.structure.hierarchy.applyPreset(
        trajectory,
        'default'
      );
    }

    init();

    return () => {
      disposed = true;
      if (plugin && !disposed) return;
      plugin?.dispose?.();
    };
  }, [url, format]);

  return <div ref={parentRef} style={{ width: '100%', height: 560, position: 'relative' }} />;
}
```

### 추천 props 연결
```tsx
<MolstarStructureViewer
  url={step4.normal_track.molstar_default!.url}
  format={step4.normal_track.molstar_default!.format}
/>
```

---

## 11. 더 단순한 대안

Mol*는 URL parameter 방식으로도 arbitrary URL 구조를 로드할 수 있다.
하지만 프로젝트 내부에서 카드/텍스트/비교 UI와 tight하게 결합할 예정이면,
iframe으로 공식 viewer를 감싸는 방식보다 **직접 임베드 방식**을 추천한다.

단, 임시 데모라면 아래 URL 패턴으로도 된다.

```text
https://molstar.org/viewer/?structure-url=<ENCODED_URL>&structure-url-format=mmcif
```

이건 빠른 PoC용 대안이다.

---

## 12. 현재 프론트 상태 머신

### 상태 1: loading
- STEP4 fetch 전

### 상태 2: baseline-ready
조건:
- `ready_for_frontend === true`
- `capabilities.normal_structure_ready === true`
- `normal_track.molstar_default != null`

UI:
- baseline protein summary 표시
- normal structure Mol* 표시

### 상태 3: user-equals-normal
조건:
- `user_track.comparison_to_normal.same_as_normal === true`

UI:
- `reuse_baseline` badge 표시
- 별도 user structure viewer는 아직 생략 가능

### 상태 4: prediction-disabled
조건:
- `capabilities.structure_prediction_enabled === false`

UI:
- predict button disabled
- `user_track.structure_prediction_message` 표시

### 상태 5: future prediction-enabled
조건:
- `capabilities.structure_prediction_enabled === true`

UI:
- predict button enabled
- job 생성 / polling
- user structure card 표시

---

## 13. 프론트에서 지금은 보여주지 않아도 되는 것

처음 버전에서는 아래는 숨겨도 된다.
- `normal_track.structures` 전체 리스트
- AlphaFold fallback 구조 목록
- `protein_seq`, `cds_seq`, `cdna_seq` 원문 전체
- `provenance`, `validation_report` 상세 JSON

이건 개발자 디버그 drawer나 advanced panel로만 넣는 것을 권장한다.

---

## 14. 운영 주의사항 (중요)

백엔드 운영 메모:
- `CORS_ORIGINS=https://spliceplayground-frontend.vercel.app,...` 를 **쉘에서 일회성으로 export한 것만으로는 systemd 서비스에 반영되지 않는다.**
- 실제 서비스 반영을 위해서는 `/home/ubuntu/splice-playground/backend/.env.backend` 파일 안의 `CORS_ORIGINS` 값을 실제 Vercel 도메인으로 수정한 뒤,
  `sudo systemctl restart splice-backend-api` 를 해야 한다.

즉 프론트가 붙기 전 백엔드 쪽에서 반드시 해야 할 일:
1. `.env.backend` 열기
2. `CORS_ORIGINS` 에 실제 Vercel 도메인 넣기
3. backend 서비스 재시작

---

## 15. 프론트 담당자에게 전달할 최종 한 줄

현재 STEP4는 **CPU-only baseline mode** 이다.
따라서 프론트는:
- `GET /api/states/{state_id}/step4?include_sequences=true` 호출
- `normal_track.molstar_default.url` + `format` 을 Mol*에 넘겨 정상 구조 표시
- `user_track` 으로 이벤트/translation summary 표시
- `structure_prediction_enabled === false` 일 때는 예측 버튼을 비활성화

이 계약만 지키면, 나중에 GPU worker가 붙어도 프론트 계약을 크게 바꾸지 않고 user structure prediction을 붙일 수 있다.
