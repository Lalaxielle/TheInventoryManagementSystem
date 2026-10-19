"""Create or reset an admin login.

Works in both modes:
  * DEMO mode  - writes to the local SQLite database
  * Supabase   - writes to the `users` table via PostgREST

Usage:
    py scripts/create_admin.py <username> <password> [Full Name]
    py scripts/create_admin.py admin "ChangeMe123!" "Administrator"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from backend.security import hash_password  # noqa: E402
from backend.store import get_store  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    username = sys.argv[1].strip()
    password = sys.argv[2]
    full_name = sys.argv[3] if len(sys.argv) > 3 else username

    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return 1

    store = get_store()
    if store.error:
        print(f"WARNING: {store.error}")

    encoded = hash_password(password)
    existing = store.get_user(username)
    if existing:
        print(f"User '{username}' already exists - updating their password.")
        if store.mode == "demo":
            import sqlite3
            with sqlite3.connect(store.db_path) as conn:
                conn.execute("UPDATE users SET password_hash = ?, full_name = ? WHERE username = ?",
                             (encoded, full_name, username))
        else:
            store._patch("users", existing["id"],
                         {"password_hash": encoded, "full_name": full_name})
    else:
        store.create_user(username, encoded, full_name)
        print(f"Created {store.mode} admin '{username}'.")

    print(f"Login: {username} / {password}")
    print(f"Data source: {'Supabase (' + config.SUPABASE_URL + ')' if config.USE_SUPABASE else 'Local DEMO database (SQLite)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
