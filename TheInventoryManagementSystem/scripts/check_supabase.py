"""Check the Supabase connection and database.

Run this after you paste your SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
into `.env` and restart nothing - this script reads `.env` directly.

    py scripts/check_supabase.py

It reports:
  * which mode the app is in (demo / supabase)
  * whether the Supabase API answers
  * whether every expected table exists and how many rows each holds
  * whether an admin login exists
  * a clear hint for whatever is wrong
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from backend.store import get_store  # noqa: E402

TABLES = ["users", "equipment", "maintenance", "borrowings", "activity_log"]


def ok(label, extra=""):
    print(f"  [ OK ]  {label}{(' - ' + extra) if extra else ''}")


def bad(label, extra=""):
    print(f"  [FAIL]  {label}{(' - ' + extra) if extra else ''}")


def main() -> int:
    print("TheInventoryManagementSystem - Supabase connection check")
    print("=" * 58)
    print(f"  SUPABASE_URL   : {config.SUPABASE_URL or '(not set)'}")
    print(f"  service key    : {'set' if config.SUPABASE_SERVICE_ROLE_KEY else '(not set)'}")
    print(f"  USE_SUPABASE   : {config.USE_SUPABASE}")
    print()

    if not config.USE_SUPABASE:
        print("Result: the app is in DEMO mode (SQLite).")
        print()
        print("To connect Supabase, edit the .env file in the project root and set:")
        print("  SUPABASE_URL=https://<your-project-ref>.supabase.co")
        print("  SUPABASE_SERVICE_ROLE_KEY=<your service_role secret>")
        print()
        print("Then run this script again.")
        return 1

    store = get_store()
    if store.error:
        bad("could not reach Supabase")
        print(f"        {store.error}")
        print()
        print("Hints:")
        print("  - Check SUPABASE_URL has no trailing slash and starts with https://")
        print("  - Check the key is the service_role secret, not the anon key")
        print("  - Make sure the project is not paused in the Supabase dashboard")
        return 2

    ok("Supabase API reached")

    # --- tables ---------------------------------------------------------
    print()
    print("Tables:")
    failures = 0
    for table in TABLES:
        try:
            rows = store._get(table, {"select": "id"})
            ok(table, f"{len(rows)} row(s)")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            message = str(exc)
            if "42P01" in message or "does not exist" in message or "404" in message:
                bad(table, "table missing - run database/setup_all.sql in Supabase")
            else:
                bad(table, message[:160])

    # --- admin login ----------------------------------------------------
    print()
    print("Admin login:")
    try:
        users = store._get("users", {"select": "username"})
        if users:
            ok("admin login(s) present", ", ".join(u["username"] for u in users))
        else:
            bad("no users - run database/setup_all.sql, or: py scripts/create_admin.py")
            failures += 1
    except Exception as exc:  # noqa: BLE001
        failures += 1
        bad("could not read users", str(exc)[:160])

    # --- summary --------------------------------------------------------
    print()
    if failures:
        print(f"Result: connected, but {failures} problem(s) above need fixing.")
        return 3

    print("Result: ALL GOOD - Supabase is connected and fully set up.")
    print("        Start the app with:  py app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
