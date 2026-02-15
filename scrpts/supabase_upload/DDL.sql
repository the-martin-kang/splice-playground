create extension if not exists "pgcrypto";

create table if not exists public.disease (
  disease_id   text primary key,
  disease_name text not null,
  description  text,
  image_path   text
);

create table if not exists public.gene (
  gene_id                 text primary key,
  gene_symbol             text not null,
  chromosome              text,
  strand                  char(1) not null check (strand in ('+', '-')),
  length                  integer not null check (length >= 0),
  exon_count              integer not null check (exon_count >= 0),
  canonical_transcript_id text,
  canonical_source        text check (canonical_source in ('MANE_Select', 'Ensembl_canonical', 'longest_CDS') or canonical_source is null),
  source_version          text
);

create table if not exists public.disease_gene (
  disease_id text not null references public.disease(disease_id) on delete cascade,
  gene_id    text not null references public.gene(gene_id) on delete cascade,
  primary key (disease_id, gene_id)
);

create table if not exists public.disease_representative_snv (
  disease_id  text primary key references public.disease(disease_id) on delete cascade,
  gene_id     text not null references public.gene(gene_id) on delete restrict,
  pos_gene0   integer not null check (pos_gene0 >= 0),
  ref         char(1) not null,
  alt         char(1) not null,
  note        text,
  check (ref <> alt)
);

create table if not exists public.region (
  region_id        text primary key,
  gene_id          text not null references public.gene(gene_id) on delete cascade,
  region_type      text not null check (region_type in ('exon', 'intron')),
  region_number    integer not null check (region_number > 0),
  gene_start_idx   integer not null check (gene_start_idx >= 0),
  gene_end_idx     integer not null check (gene_end_idx >= gene_start_idx),
  length           integer not null check (length >= 0),
  sequence         text not null,
  cds_start_offset integer,
  cds_end_offset   integer,
  unique (gene_id, region_type, region_number),
  check (
    (cds_start_offset is null and cds_end_offset is null)
    or
    (cds_start_offset is not null and cds_end_offset is not null and cds_start_offset >= 0 and cds_end_offset >= cds_start_offset)
  )
);

create index if not exists idx_region_gene on public.region(gene_id);
create index if not exists idx_region_gene_type_num on public.region.region(gene_id, region_type, region_number);
create index if not exists idx_region_gene_idx on public.region(gene_id, gene_start_idx, gene_end_idx);

create table if not exists public.baseline_result (
  gene_id        text not null references public.gene(gene_id) on delete cascade,
  step           text not null check (step in ('sequence', 'splicing', 'protein')),
  model_version  text not null,
  result_payload jsonb not null,
  primary key (gene_id, step)
);

create table if not exists public.snv_result (
  disease_id     text not null references public.disease(disease_id) on delete cascade,
  step           text not null check (step in ('sequence', 'splicing', 'protein')),
  model_version  text not null,
  result_payload jsonb not null,
  delta_payload  jsonb,
  primary key (disease_id, step)
);

create table if not exists public.user_state (
  state_id        uuid primary key default gen_random_uuid(),
  disease_id      text not null references public.disease(disease_id) on delete cascade,
  parent_state_id uuid references public.user_state(state_id) on delete set null,
  applied_edit    jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now()
);

create index if not exists idx_user_state_disease on public.user_state(disease_id);
create index if not exists idx_user_state_parent on public.user_state(parent_state_id);

create table if not exists public.user_state_result (
  state_id       uuid not null references public.user_state(state_id) on delete cascade,
  step           text not null check (step in ('sequence', 'splicing', 'protein')),
  model_version  text not null,
  result_payload jsonb not null,
  delta_payload  jsonb,
  primary key (state_id, step)
);

create index if not exists idx_user_state_result_step on public.user_state_result(step);