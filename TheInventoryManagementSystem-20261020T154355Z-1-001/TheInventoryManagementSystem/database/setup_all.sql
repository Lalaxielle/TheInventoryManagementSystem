-- ==================================================================
--  TheInventoryManagementSystem - COMPLETE Supabase setup
--  Paste this ENTIRE file into Supabase -> SQL Editor -> New query
--  and click RUN.  It creates every table (schema.sql) and then
--  loads the sample data + default admin login (seed.sql).
--
--  Default admin login after running:  admin / admin123
-- ==================================================================

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



-- ==================================================================
--  TheInventoryManagementSystem - optional sample data for Supabase
--  Run AFTER schema.sql.  Creates the default admin login and a set
--  of sample IT equipment so the dashboard is populated immediately.
--
--  Default admin login:  admin / admin123   (change it later with
--  py scripts/create_admin.py <user> <password> "<Full Name>")
-- ==================================================================

-- ------------------------------------------------------- admin login
insert into public.users (username, password_hash, full_name, role)
values (
  'admin',
  'pbkdf2_sha256$260000$696c74696d73303132333435$db4e609dcf6b1caa3a813cd71930da0831b049e27193d18028d0504a37941020',
  'System Administrator',
  'admin'
)
on conflict (username) do nothing;

-- ------------------------------------------------------- equipment
insert into public.equipment
  (id, asset_tag, model, brand, category, serial_no, assigned_to, location,
   status, condition, purchase_date, warranty_expiry, notes)
values
  ('11111111-1111-4111-8111-111111111101', 'IT-0001', 'ThinkPad T14 Gen 3', 'Lenovo', 'Laptop', 'PF3K8T21', 'Juan Dela Cruz', 'Rm 301 - Finance', 'Assigned', 'Good', '2024-03-15', '2027-03-15', 'Issued with docking station.'),
  ('11111111-1111-4111-8111-111111111102', 'IT-0002', 'Latitude 5440', 'Dell', 'Laptop', '7HQ2LM3', 'Maria Santos', 'Rm 205 - HR', 'Assigned', 'Good', '2023-11-20', '2025-11-20', 'Warranty expired - renew next budget cycle.'),
  ('11111111-1111-4111-8111-111111111103', 'IT-0003', 'MacBook Air M2', 'Apple', 'Laptop', 'C02X45M8Q6L4', 'Pedro Reyes', 'Rm 108 - Marketing', 'Assigned', 'Good', '2024-01-30', '2028-01-30', ''),
  ('11111111-1111-4111-8111-111111111104', 'IT-0004', 'UltraSharp U2422H', 'Dell', 'Monitor', 'CN0X7T9', '', 'Stock Room A', 'Under Maintenance', 'Fair', '2024-06-10', '2026-12-15', 'HDMI port fault - with service center.'),
  ('11111111-1111-4111-8111-111111111105', 'IT-0005', 'EW2780', 'BenQ', 'Monitor', 'ETX8K001', 'Reception Desk', 'Ground Floor - Lobby', 'Assigned', 'Fair', '2023-09-01', '2026-10-30', 'Flickers on cold start.'),
  ('11111111-1111-4111-8111-111111111106', 'IT-0006', 'LaserJet Pro M404dn', 'HP', 'Printer', 'VNC4R12345', 'Admin Pool', 'Rm 110 - Admin', 'Assigned', 'Good', '2024-02-05', '2026-02-05', 'Shared network printer.'),
  ('11111111-1111-4111-8111-111111111107', 'IT-0007', 'OptiPlex 7010', 'Dell', 'Desktop', '4KJ8NP2', 'Ana Cruz', 'Rm 205 - HR', 'Assigned', 'Good', '2025-09-12', '2027-09-12', ''),
  ('11111111-1111-4111-8111-111111111108', 'IT-0008', 'ProDesk 400 G9', 'HP', 'Desktop', '8CC1234ABC', '', 'Stock Room A', 'In Stock', 'Good', '2025-03-01', '2028-03-01', 'Spare unit for new hires.'),
  ('11111111-1111-4111-8111-111111111109', 'IT-0009', 'iPhone 14', 'Apple', 'Phone', 'F17X9QLK', 'Carlo Tan', 'Field - Sales', 'Assigned', 'Good', '2023-12-08', '2025-12-08', 'Company line: 0917-555-0134.'),
  ('11111111-1111-4111-8111-111111111110', 'IT-0010', 'Galaxy S23', 'Samsung', 'Phone', 'R58W41', '', 'Stock Room A', 'Borrowed', 'Good', '2024-08-22', '2026-11-05', 'Loaner phone for events.'),
  ('11111111-1111-4111-8111-111111111111', 'IT-0011', 'PowerEdge R650', 'Dell', 'Server', '7YH2K03', 'IT Ops', 'Server Room', 'Assigned', 'Good', '2024-04-18', '2027-04-18', 'Hosts ERP and file shares.'),
  ('11111111-1111-4111-8111-111111111112', 'IT-0012', 'UniFi U6 Pro', 'Ubiquiti', 'Network', 'F49A2B1C', '', 'Server Room', 'In Stock', 'Good', '2024-10-05', '2026-10-05', 'Spare access point.'),
  ('11111111-1111-4111-8111-111111111113', 'IT-0013', 'Brio 500', 'Logitech', 'Peripheral', '2247LZ0', '', 'Stock Room B', 'Borrowed', 'Good', '2025-01-20', '2027-01-20', 'Conference room webcam.'),
  ('11111111-1111-4111-8111-111111111114', 'IT-0014', 'TS-464', 'QNAP', 'Storage', 'QN8H47', 'IT Ops', 'Server Room', 'Assigned', 'Good', '2023-01-25', '2026-01-25', 'Nightly backup target.'),
  ('11111111-1111-4111-8111-111111111115', 'IT-0015', 'Surface Pro 9', 'Microsoft', 'Tablet', '038972615', 'IT Pool', 'Rm 302 - IT Dept', 'Under Maintenance', 'Fair', '2024-05-30', '2026-12-01', 'Battery swelling - repair in progress.'),
  ('11111111-1111-4111-8111-111111111116', 'IT-0016', 'Catalyst 9200', 'Cisco', 'Network', 'FOC2508X1', 'IT Ops', 'Server Room', 'Assigned', 'Good', '2025-05-14', '2027-05-14', 'Core switch, 3rd floor closet.'),
  ('11111111-1111-4111-8111-111111111117', 'IT-0017', 'ProBook 450 G10', 'HP', 'Laptop', '5CD3456XYZ', '', 'Stock Room B', 'Retired', 'Damaged', '2022-07-10', '2025-07-10', 'Motherboard failure - retired, awaiting disposal.')
on conflict (id) do nothing;

-- ------------------------------------------------------- maintenance
insert into public.maintenance
  (equipment_id, mtype, description, scheduled_date, completed_date, status, technician, cost)
values
  ('11111111-1111-4111-8111-111111111115', 'Repair', 'Replace swollen battery and run full diagnostics', '2026-10-14', null, 'In Progress', 'Ramon Diaz', 0),
  ('11111111-1111-4111-8111-111111111104', 'Repair', 'Replace faulty HDMI port, unit with service center', '2026-10-10', null, 'Scheduled', 'IT Ops', 0),
  ('11111111-1111-4111-8111-111111111106', 'Preventive', 'Annual preventive maintenance and toner check', '2026-10-25', null, 'Scheduled', 'KPM Services', 3500),
  ('11111111-1111-4111-8111-111111111111', 'Inspection', 'Quarterly server health and dust cleanup', '2026-09-28', '2026-09-28', 'Completed', 'Ramon Diaz', 0);

-- ------------------------------------------------------- borrowings
insert into public.borrowings
  (equipment_id, borrower, department, purpose, borrowed_date, due_date, returned_date, status, notes)
values
  ('11111111-1111-4111-8111-111111111110', 'Marco Villanueva', 'Marketing', 'Client presentation - offsite', '2026-10-10', '2026-10-24', null, 'Borrowed', ''),
  ('11111111-1111-4111-8111-111111111113', 'Diana Reyes', 'Sales', 'Product demo kit', '2026-09-25', '2026-10-05', null, 'Borrowed', 'Reminder sent twice.'),
  ('11111111-1111-4111-8111-111111111103', 'Sofia Lim', 'HR', 'New hire orientation', '2026-09-15', '2026-09-22', '2026-09-20', 'Returned', '');

-- ------------------------------------------------------- activity log
insert into public.activity_log (action, entity, detail, username, created_at)
values
  ('LOGIN', 'session', 'Signed in as admin', 'admin', now() - interval '2 hours'),
  ('CREATE', 'IT-0017', 'Registered ProBook 450 G10 (HP) and marked Retired', 'admin', now() - interval '1 day'),
  ('UPDATE', 'IT-0012', 'Updated warranty expiry for UniFi U6 Pro', 'admin', now() - interval '1 day'),
  ('BORROW', 'IT-0010', 'Galaxy S23 issued to Marco Villanueva (due 2026-10-24)', 'admin', now() - interval '3 day'),
  ('MAINTENANCE', 'IT-0015', 'Repair started for Surface Pro 9', 'admin', now() - interval '4 day'),
  ('RETURN', 'IT-0003', 'MacBook Air M2 returned by Sofia Lim', 'admin', now() - interval '9 day');

