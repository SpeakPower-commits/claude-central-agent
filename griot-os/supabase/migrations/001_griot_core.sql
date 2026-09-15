create extension if not exists pgcrypto;

create table if not exists public.griot_projects (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  name text not null,
  description text,
  created_at timestamptz not null default now()
);

create table if not exists public.griot_memories (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references public.griot_projects(id) on delete cascade,
  kind text not null,
  title text not null,
  content text not null,
  confidence text not null check (confidence in ('fact','inference','hypothesis','recommendation','unknown')),
  source text,
  created_at timestamptz not null default now()
);

create table if not exists public.griot_decisions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references public.griot_projects(id) on delete set null,
  request text not null,
  recommendation text,
  status text not null default 'analyzed',
  created_at timestamptz not null default now()
);

create table if not exists public.griot_actions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references public.griot_projects(id) on delete set null,
  action_type text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending',
  requires_approval boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.griot_kpis (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references public.griot_projects(id) on delete cascade,
  name text not null,
  value numeric,
  target numeric,
  measured_at timestamptz not null default now()
);

insert into public.griot_projects(slug,name,description) values
('speakpower','SpeakPower','Brand storytelling, communications and market development'),
('tonninyira','Tonninyira','Marketplace product, growth and software operations'),
('cuepointe','CuePointe','Community, tournament operations, brand and growth'),
('ubf','UBF','Conservation communications and process automation'),
('fob','FoB','Biodiversity/community ecosystem and operations'),
('other','Other Ventures','Cross-project business and strategy work')
on conflict (slug) do nothing;
