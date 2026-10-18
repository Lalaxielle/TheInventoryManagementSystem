"""Data store factory.

Uses Supabase when credentials are configured, otherwise falls back to the
local SQLite DEMO database (auto-created and seeded with sample data).
"""

import config
from backend.sqlite_store import SqliteStore
from backend.supabase_store import SupabaseStore


def get_store():
    if config.USE_SUPABASE:
        store = SupabaseStore(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
        try:
            store.ping()
        except Exception as exc:
            store.error = (
                f"Cannot reach Supabase at {config.SUPABASE_URL} - check the "
                f"SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY values in .env ({exc})"
            )
        return store
    return SqliteStore(config.DB_PATH)
