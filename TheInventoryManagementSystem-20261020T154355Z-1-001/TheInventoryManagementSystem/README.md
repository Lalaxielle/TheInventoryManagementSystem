# TheInventoryManagementSystem

A centralized **IT Equipment Management System** for recording, monitoring and
managing every IT device in the organization - built with a plain **HTML**
frontend, a **Python (Flask)** backend, **Supabase** as the database and **Vercel** for web hosting.
The source code can be maintained in a **GitHub repository** and connected to
Vercel for deployment.

Theme: **Black / White / Grey** - flat, utilitarian, high-contrast.

## Objectives

- Centralize IT equipment records, including asset tags, assignment, location,
  condition, and warranty details.
- Support equipment lifecycle workflows for borrowing, returns, and maintenance.
- Help administrators monitor inventory through dashboards, search, filters,
  warranty tracking, and location views.
- Provide CSV/PDF reports and an activity log to support operational review
  and accountability.
- Protect administrative access and database credentials with session-based
  authentication, CSRF validation, and server-side Supabase access.

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

## Quick start (Supabase required)

```bash
cd TheInventoryManagementSystem
pip install -r requirements.txt
py scripts/check_supabase.py
py app.py
```

Before starting the app, create the Supabase tables and configure
`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the project-root `.env` file
as described below. Open <http://127.0.0.1:5000> after the connection check
succeeds.

## Supabase setup

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

5. Start or restart `py app.py`. The app reads and writes records in your
  Supabase project.

> The service-role key bypasses Row Level Security, so it must stay
> **server-side only** - it is never sent to the browser. Every table has RLS
> enabled with no policies, so the public anon key can read/write nothing.

## Qeti and deployment security

The signed-in admin assistant answers questions about using the website and,
for relevant questions, retrieves a limited read-only context from equipment,
loan, maintenance, and activity-log records. It does not modify records or
retrieve account credentials. Record lookups are restricted to signed-in admin
sessions. Relevant record details may be sent to Google's Gemini API to
generate the reply; do not enter passwords, API keys, or unrelated private
information in chat. To enable it, create a Gemini API key in Google AI Studio
and set `GEMINI_API_KEY` in the project-root `.env` or `.env.local` file;
optionally change `GEMINI_MODEL` (defaults to `gemini-3.5-flash-lite`).
`.env.local` takes precedence over `.env`, while process environment variables
take precedence over both. Install dependencies with
`pip install -r requirements.txt`; the backend uses Google's official
`google-genai` Python SDK. The key is never sent to the browser. The endpoint
requires the user's session and CSRF token and is rate-limited.

The chat widget in `templates/base.html` is connected by `static/js/app.js` to
the signed-in Flask `/api/chat` endpoint. The endpoint restricts record context
to admin sessions and sends only bounded, relevant fields to Gemini. Replies
stream into the panel and use recent messages from the selected conversation
as context. Qeti is read-only: it cannot perform record changes. The widget
preserves local browser chat history and provides a retry action when a reply
fails.

Qeti conversations are stored in the current browser's local storage, scoped to
the signed-in user on that browser. They are not saved to Supabase or shared
across devices. Use **New chat** to start another conversation or **Delete** to
remove an individual saved chat.

Gemini's free tier has model- and account-dependent quotas and may change. Check
Google's [current Gemini API pricing and data-use terms](https://ai.google.dev/gemini-api/docs/pricing)
before enabling it; free-tier content may be used to improve Google's products.

The Flask app applies browser security headers (Content Security Policy,
clickjacking protection, MIME sniffing protection, referrer and permissions
policies) directly, whether or not Apache is installed. HSTS is sent only over
HTTPS.

### Vercel deployment

Keep secrets out of the repository. Add required values such as
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, and `SECRET_KEY`
in the Vercel project's Environment Variables settings. Never commit `.env` or
`.env.local`, and rotate any key that has been exposed.

This application uses Flask. The repository does not include a `vercel.json`
or a Vercel-specific Python entry point. The existing Vercel deployment must
therefore have the appropriate runtime/build configuration in its project
settings. Check deployment logs after changes. Apache settings below do not
apply to Vercel.

### Apache deployment

For a server you control, use `apache/inventory-vhost.conf` as a starting
point for Apache 2.4 server-level hardening and the HTTPS reverse proxy.
Replace the example domain and certificate paths, enable the listed Apache
modules, and review the TLS settings for your Apache version. Run the Flask app
behind Apache with a production WSGI server, not Flask's development server:

```bash
pip install -r requirements.txt
set SESSION_COOKIE_SECURE=1
set TRUST_PROXY=1
waitress-serve --listen=127.0.0.1:5000 app:app
```

On Linux, export `SESSION_COOKIE_SECURE=1` and `TRUST_PROXY=1` in the service
environment instead of using `set`. Keep port 5000 bound to loopback and
firewalled from external access; Apache terminates HTTPS and applies the
security headers. This Apache configuration applies only to deployments that
actually use Apache.

### Creating / resetting the admin login

```bash
py scripts/create_admin.py admin "ChangeMe123!" "Administrator"
```

Configure the Supabase environment variables before running this command.

## Project structure

```
TheInventoryManagementSystem/
├── app.py                     # Flask app: all routes/pages
├── config.py                  # .env loader, mode detection
├── apache/                    # Apache HTTPS reverse-proxy hardening example
├── backend/
│   ├── models.py              # statuses, warranty logic, filters, aggregates
│   ├── security.py            # PBKDF2 hashing, CSRF tokens
│   ├── store.py               # configured data-store factory
│   ├── supabase_store.py      # Supabase PostgREST store
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
- Responses include a Content Security Policy and standard browser security
  headers; HSTS is enabled only for HTTPS requests.
- Every POST is validated against a per-session **CSRF token**.
- All output is HTML-escaped by the template engine.
- RLS enabled on every Supabase table with no policies (service-role only).

## How device status flows

- **Borrow** a device → status becomes *Borrowed*; **return** it → back to
  *Assigned* (if someone owns it) or *In Stock*.
- **Schedule** maintenance dated today or earlier (or press *Start*) → status
  becomes *Under Maintenance*; **complete** or delete the job → status reverts.
- Everything is written to the **Activity Log** automatically.

