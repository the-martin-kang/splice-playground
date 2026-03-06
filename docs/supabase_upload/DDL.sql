-- ============================================================
-- splice-playground (MVP) - Public Schema DDL (Rebuild)
-- Step1~4 product flow friendly
--   Step3: splicing 결과
--   Step4: protein/structure 차이
-- ============================================================

begin;

-- UUID 생성용 (Supabase에서는 보통 사용 가능)
create extension if not exists "pgcrypto";

-- updated_at 자동 갱신 트리거 함수
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ------------------------------------------------------------
-- Drop existing tables (safe, order matters)
-- ------------------------------------------------------------
drop table if exists public.structure_job cascade;
drop table if exists public.user_state_result cascade;
drop table if exists public.baseline_result cascade;

drop table if exists public.user_state cascade;
drop table if exists public.editing_target_window cascade;
drop table if exists public.splice_altering_snv cascade;

drop table if exists public.region cascade;

-- legacy tables you decided to remove
drop table if exists public.disease_gene cascade;
drop table if exists public.disease_representative_snv cascade;

drop table if exists public.disease cascade;
drop table if exists public.gene cascade;

-- ------------------------------------------------------------
-- gene
-- ------------------------------------------------------------
create table public.gene (
  gene_id text primary key,                 -- e.g. "SMN1"
  gene_symbol text not null,                -- display (often same as gene_id)
  chromosome text,                          -- e.g. "chr5" (metadata)
  strand char(1) not null check (strand in ('+','-')),

  length integer not null check (length > 0),
  exon_count integer not null check (exon_count > 0),

  canonical_transcript_id text,
  canonical_source text,
  source_version text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint uq_gene_symbol unique (gene_symbol)
);

create trigger trg_gene_set_updated_at
before update on public.gene
for each row execute function public.set_updated_at();

-- ------------------------------------------------------------
-- disease  (※ 너가 쓰는 "disease_id"는 사실상 mutant case id로 이해)
--  - disease_id 예: "SMN1_gene0_27005_C>T"
--  - 같은 disease_name 이더라도 disease_id는 다를 수 있음
--  - 한 disease row는 MVP에서 "대표 gene 1개"를 갖는다고 가정
-- ------------------------------------------------------------
create table public.disease (
  disease_id text primary key,
  disease_name text not null,
  description text,
  image_path text,

  gene_id text not null references public.gene(gene_id) on delete restrict,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- composite FK를 쓰기 위해 "형식상" unique로 선언 (disease_id가 PK라 논리상 redundant지만 필요)
  constraint uq_disease_id_gene unique (disease_id, gene_id)
);

create index idx_disease_gene_id on public.disease(gene_id);

create trigger trg_disease_set_updated_at
before update on public.disease
for each row execute function public.set_updated_at();

-- ------------------------------------------------------------
-- region (exon/intron segments)
--  - gene-local coordinate (0-based), gene_end_idx는 inclusive로 가정
--  - length = gene_end_idx - gene_start_idx + 1
-- ------------------------------------------------------------
create table public.region (
  region_id text primary key,               -- e.g. "SMN1_exon_7" 같은 식으로 자유롭게

  gene_id text not null references public.gene(gene_id) on delete cascade,

  region_type text not null check (region_type in ('exon','intron')),
  region_number integer not null check (region_number > 0),

  gene_start_idx integer not null check (gene_start_idx >= 0),
  gene_end_idx integer not null check (gene_end_idx >= gene_start_idx),

  length integer not null check (length = gene_end_idx - gene_start_idx + 1),
  sequence text not null,

  -- optional (원하면 exon 내 CDS offset)
  cds_start_offset integer,
  cds_end_offset integer,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint uq_region_gene_type_number unique (gene_id, region_type, region_number),
  constraint ck_region_seq_length check (char_length(sequence) = length)
);

create index idx_region_gene_id on public.region(gene_id);
create index idx_region_gene_range on public.region(gene_id, gene_start_idx, gene_end_idx);

create trigger trg_region_set_updated_at
before update on public.region
for each row execute function public.set_updated_at();

-- ------------------------------------------------------------
-- splice_altering_snv
--  - disease_representative_snv 제거하고 여기로 통일
--  - disease당 복수 SNV 저장 가능 (PK를 uuid로)
--  - Step1/2에서 "대표 SNV"를 안정적으로 고르기 위해 is_representative 사용
-- ------------------------------------------------------------
create table public.splice_altering_snv (
  snv_id uuid primary key default gen_random_uuid(),

  disease_id text not null,
  gene_id text not null,

  pos_gene0 integer not null check (pos_gene0 >= 0),

  ref char(1) not null check (ref in ('A','C','G','T','N')),
  alt char(1) not null check (alt in ('A','C','G','T','N')),
  constraint ck_snv_ref_alt_diff check (ref <> alt),

  is_representative boolean not null default false,

  -- hg38는 "메타데이터로만" 유지(원하면 채우고, 아니면 null이어도 됨)
  chromosome text,
  pos_hg38_1 integer,

  note text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- disease의 gene_id와 반드시 일치하도록 composite FK로 고정
  constraint fk_snv_disease_gene
    foreign key (disease_id, gene_id)
    references public.disease(disease_id, gene_id)
    on delete cascade
    on update cascade,

  -- 같은 SNV 중복 저장 방지
  constraint uq_snv_natural unique (disease_id, gene_id, pos_gene0, ref, alt)
);

-- disease당 대표 SNV는 "최대 1개"만 (없을 수는 있음: DB가 강제 못하지만, 운영 규칙으로 넣자)
create unique index uq_one_representative_snv_per_disease
on public.splice_altering_snv(disease_id)
where is_representative;

create index idx_snv_disease on public.splice_altering_snv(disease_id);
create index idx_snv_gene_pos on public.splice_altering_snv(gene_id, pos_gene0);

create trigger trg_snv_set_updated_at
before update on public.splice_altering_snv
for each row execute function public.set_updated_at();

-- ------------------------------------------------------------
-- editing_target_window (Step2 핵심: 조절 타겟 구간 + chosen_by)
-- ------------------------------------------------------------
create table public.editing_target_window (
  window_id uuid primary key default gen_random_uuid(),

  disease_id text not null,
  gene_id text not null,

  start_gene0 integer not null check (start_gene0 >= 0),
  end_gene0 integer not null check (end_gene0 >= start_gene0),

  label text,
  chosen_by text not null,                  -- 예: 'manual', 'heuristic', 'model'
  note text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint fk_window_disease_gene
    foreign key (disease_id, gene_id)
    references public.disease(disease_id, gene_id)
    on delete cascade
    on update cascade
);

create index idx_window_disease on public.editing_target_window(disease_id);
create index idx_window_gene_range on public.editing_target_window(gene_id, start_gene0, end_gene0);

create trigger trg_window_set_updated_at
before update on public.editing_target_window
for each row execute function public.set_updated_at();

-- ------------------------------------------------------------
-- user_state (Step2 편집 상태)
--  - applied_edit는 너가 합의한 JSON 포맷:
--      {"type":"user","edits":[{"pos":109442,"from":"G","to":"A"}, ...]}
--  - 이 patch는 "mutated starting point(= 대표 SNV가 이미 들어간 상태)" 기준이라고 가정
-- ------------------------------------------------------------
create table public.user_state (
  state_id uuid primary key default gen_random_uuid(),

  disease_id text not null,
  gene_id text not null,

  parent_state_id uuid references public.user_state(state_id) on delete set null,

  applied_edit jsonb not null default '{"type":"user","edits":[]}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint fk_state_disease_gene
    foreign key (disease_id, gene_id)
    references public.disease(disease_id, gene_id)
    on delete cascade
    on update cascade,

  -- 최소 형태 검증(너무 빡빡하게 안 잡고 MVP에 필요한 수준만)
  constraint ck_applied_edit_shape check (
    jsonb_typeof(applied_edit) = 'object'
    and applied_edit ? 'type'
    and applied_edit ? 'edits'
    and jsonb_typeof(applied_edit->'edits') = 'array'
  )
);

create index idx_state_disease on public.user_state(disease_id);
create index idx_state_created_at on public.user_state(created_at);

create trigger trg_user_state_set_updated_at
before update on public.user_state
for each row execute function public.set_updated_at();

-- ------------------------------------------------------------
-- baseline_result (gene별 baseline 결과 캐시)
--  - model_version을 PK에 포함 (네 합의 반영)
-- ------------------------------------------------------------
create table public.baseline_result (
  gene_id text not null references public.gene(gene_id) on delete cascade,

  step text not null check (step in ('step3','step4')),
  model_version text not null,

  result_payload jsonb not null,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  primary key (gene_id, step, model_version)
);

create index idx_baseline_result_step on public.baseline_result(step);

create trigger trg_baseline_result_set_updated_at
before update on public.baseline_result
for each row execute function public.set_updated_at();

-- ------------------------------------------------------------
-- user_state_result (state별 결과)
--  - model_version을 PK에 포함 (네 합의 반영)
--  - result_payload: 절대 결과
--  - delta_payload: baseline과의 diff
-- ------------------------------------------------------------
create table public.user_state_result (
  state_id uuid not null references public.user_state(state_id) on delete cascade,

  step text not null check (step in ('step3','step4')),
  model_version text not null,

  result_payload jsonb not null,
  delta_payload jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  primary key (state_id, step, model_version)
);

create index idx_user_state_result_step on public.user_state_result(step);

create trigger trg_user_state_result_set_updated_at
before update on public.user_state_result
for each row execute function public.set_updated_at();

-- ------------------------------------------------------------
-- structure_job (Step4 async: AlphaFold3 등)
-- ------------------------------------------------------------
create table public.structure_job (
  job_id uuid primary key default gen_random_uuid(),

  state_id uuid not null references public.user_state(state_id) on delete cascade,

  provider text not null default 'alphafold3',
  status text not null check (status in ('queued','running','succeeded','failed','canceled')),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  external_job_id text,
  result_payload jsonb,
  error_message text,

  -- external_job_id는 provider별로 unique하게 관리(없으면 null 허용)
  constraint uq_structure_job_external unique (provider, external_job_id)
);

create index idx_structure_job_state on public.structure_job(state_id);
create index idx_structure_job_status on public.structure_job(status);

create trigger trg_structure_job_set_updated_at
before update on public.structure_job
for each row execute function public.set_updated_at();

commit;
