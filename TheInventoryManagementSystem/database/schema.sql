-- ==================================================================
--  TheInventoryManagementSystem - Supabase schema
--  Run this once in the Supabase SQL Editor (SQL Editor -> New query).
-- ==================================================================

create extension if not exists "pgcrypto";

-- ------------------------------------------------------- admin users
create table if not exists public.users (
  id            uuid primary key default gen_random_uuid(),
  username      text unique not null,
  password_hash text not null,
  full_name     text default '',
  role          text default 'admin',
  created_at    timestamptz default now()
);

-- ------------------------------------------------------- equipment
create table if not exists public.equipment (
  id              uuid primary key default gen_random_uuid(),
  asset_tag       text,
  model           text not null,
  brand           text,
  category        text,
  serial_no       text,
  assigned_to     text,
  location        text,
  status          text default 'In Stock',
  condition       text default 'Good',
  purchase_date   date,
  warranty_expiry date,
  notes           text,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

-- ------------------------------------------------------- maintenance
create table if not exists public.maintenance (
  id             uuid primary key default gen_random_uuid(),
  equipment_id   uuid not null references public.equipment(id) on delete cascade,
  mtype          text,
  description    text,
  scheduled_date date,
  completed_date date,
  status         text default 'Scheduled',
  technician     text,
  cost           numeric default 0,
  created_at     timestamptz default now()
);

-- ------------------------------------------------------- borrowings
create table if not exists public.borrowings (
  id            uuid primary key default gen_random_uuid(),
  equipment_id  uuid not null references public.equipment(id) on delete cascade,
  borrower      text,
  department    text,
  purpose       text,
  borrowed_date date,
  due_date      date,
  returned_date date,
  status        text default 'Borrowed',
  notes         text,
  created_at    timestamptz default now()
);

-- ------------------------------------------------------- activity log
create table if not exists public.activity_log (
  id         uuid primary key default gen_random_uuid(),
  action     text,
  entity     text,
  detail     text,
  username   text,
  created_at timestamptz default now()
);

create index if not exists ix_equipment_status   on public.equipment (status);
create index if not exists ix_maintenance_equipment on public.maintenance (equipment_id);
create index if not exists ix_borrowings_equipment  on public.borrowings (equipment_id);
create index if not exists ix_activity_created   on public.activity_log (created_at desc);

-- ==================================================================
--  Row Level Security: enabled with NO policies, so the public anon
--  and authenticated keys can read and write NOTHING.  Only the
--  server-side service_role key used by the Python backend has access.
-- ==================================================================
alter table public.users       enable row level security;
alter table public.equipment   enable row level security;
alter table public.maintenance enable row level security;
alter table public.borrowings  enable row level security;
alter table public.activity_log enable row level security;
