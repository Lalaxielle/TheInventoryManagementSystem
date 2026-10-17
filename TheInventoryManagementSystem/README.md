# TheInventoryManagementSystem

A centralized **IT Equipment Management System** for recording, monitoring and
managing every IT device in the organization - built with a plain **HTML**
frontend, a **Python (Flask)** backend and **Supabase** as the database.

Theme: **Black / White / Grey** - flat, utilitarian, high-contrast.

## Features

| Page | What it does |
| --- | --- |
| **Login (admin)** | Session-based admin sign-in, CSRF-protected forms, PBKDF2 password hashes |
| **Dashboard** | Live stat cards (total, assigned, in stock, under maintenance, on loan, warranty ≤ 90 days), status/category charts, next warranties to expire, open maintenance, devices on loan, recent activity |
| **Equipment** | The classic view - **Model, Brand, Assigned** table plus the *IT EQUIPMENT INFORMATION* form (SAVE / DELETE), search + status/category filters, asset tags auto-generated |
| **Warranty Tracking** | **Model, Brand, Assigned, Warranty Expiry** with EXPIRED / EXPIRING / DUE SOON / ACTIVE badges and warranty filters |
| **Borrow & Return** | Issue devices to staff (status flips to *Borrowed*), record returns, spot overdue loans |
| **Maintenance** | Schedule preventive/repair/inspection jobs, start/complete them, devices flip to *Under Maintenance* and back |
| **Locations** | Every device grouped by where it physically lives |
| **Reports** | Summary tables (status, category, brand, location, warranty) + CSV exports + printable report |
| **Activity Log** | Full audit trail of who did what and when |

## Quick start (no Supabase needed - DEMO mode)

```bash
cd TheInventoryManagementSystem
pip install -r requirements.txt
py app.py
```

Open <http://127.0.0.1:5000> and sign in with **admin / admin123**.

In DEMO mode everything is stored in `data/inventory.db` (SQLite) and
auto-seeded with 17 sample IT devices, maintenance jobs, borrowings and
activity history, so every page is populated immediately.

## Connecting Supabase (production mode)

1. Create a project at [supabase.com](https://supabase.com).
2. **SQL Editor → New query**: paste the whole of `database/setup_all.sql`
   and click **RUN**. That one file creates all the tables *and* loads the
   sample data + the default `admin` login.
   (Prefer them separately? Run `database/schema.sql`, then `database/seed.sql`.)
3. Create the `.env` file **in this project folder** (next to `app.py`) and add
   your credentials:

   ```bash
   copy .env.example .env       # Windows
   # or: cp .env.example .env   # macOS / Linux
   ```

   | Variable | Where to find it |
   | --- | --- |
   | `SUPABASE_URL` | Project Settings → API → Project URL |
   | `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API → `service_role` secret |

4. Check the connection:

   ```bash
   py scripts/check_supabase.py
   ```

   It confirms the API answers, that every table exists, and that an admin
   login is present - with a clear hint for anything missing.

5. Restart `py app.py`. The sidebar chip switches from *Demo mode* to
   *Supabase connected* - the app now reads and writes your Supabase tables.

> The service-role key bypasses Row Level Security, so it must stay
> **server-side only** - it is never sent to the browser. Every table has RLS
> enabled with no policies, so the public anon key can read/write nothing.

### Creating / resetting the admin login

```bash
py scripts/create_admin.py admin "ChangeMe123!" "Administrator"
```

Works in both DEMO and Supabase mode.

## Project structure

```
TheInventoryManagementSystem/
├── app.py                     # Flask app: all routes/pages
├── config.py                  # .env loader, mode detection
├── backend/
│   ├── models.py              # statuses, warranty logic, filters, aggregates
│   ├── security.py            # PBKDF2 hashing, CSRF tokens
│   ├── store.py               # store factory (Supabase or SQLite)
│   ├── sqlite_store.py        # DEMO-mode store (+ auto schema & seed)
│   ├── supabase_store.py      # Supabase PostgREST store
│   └── seed.py                # sample data used by DEMO mode
├── templates/                 # plain HTML (Jinja) pages
│   ├── base.html              # sidebar + topbar shell
│   ├── login.html  dashboard.html  equipment.html
│   ├── borrow.html  maintenance.html  locations.html
│   ├── reports.html  activity.html  error.html
│   └── partials/equipment_form.html
├── static/
│   ├── css/style.css          # black / white / grey theme
│   └── js/app.js              # row select, edit form, confirms
├── database/
│   ├── schema.sql             # run once in Supabase
│   ├── seed.sql               # optional sample data for Supabase
│   └── setup_all.sql          # schema + seed in ONE file (easiest)
├── scripts/
│   ├── create_admin.py        # create / reset an admin login
│   └── check_supabase.py      # verify the Supabase connection
├── run.bat / run.sh
└── requirements.txt
```

## Security notes

- Passwords hashed with **PBKDF2-HMAC-SHA256** (260k iterations), verified with
  constant-time comparison.
- Sessions use `HttpOnly`, `SameSite=Lax` cookies.
- Every POST is validated against a per-session **CSRF token**.
- All output is HTML-escaped by the template engine.
- RLS enabled on every Supabase table with no policies (service-role only).

## How device status flows

- **Borrow** a device → status becomes *Borrowed*; **return** it → back to
  *Assigned* (if someone owns it) or *In Stock*.
- **Schedule** maintenance dated today or earlier (or press *Start*) → status
  becomes *Under Maintenance*; **complete** or delete the job → status reverts.
- Everything is written to the **Activity Log** automatically.
