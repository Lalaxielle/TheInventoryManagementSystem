"""Configuration loader for TheInventoryManagementSystem.

Reads the optional `.env` file in the project root and exposes the
settings the app needs.  When Supabase credentials are present the app
talks to Supabase (PostgREST); otherwise it runs in DEMO mode backed by
a local SQLite database seeded with sample IT equipment.
"""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
TIMEZONE = "Asia/Manila"


def _load_env(path: Path) -> None:
    """Tiny .env parser - no third-party dependency needed."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


# Local overrides load first; process-level environment variables still win
# because the parser only fills values that are not already set.
_load_env(BASE_DIR / ".env.local")
_load_env(BASE_DIR / ".env")

# --------------------------------------------------------------- AI assistant
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0").strip().lower() in (
    "1", "true", "yes",
)
TRUST_PROXY = os.environ.get("TRUST_PROXY", "0").strip().lower() in ("1", "true", "yes")

# ---------------------------------------------------------------- Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)

# ---------------------------------------------------------------- Sessions
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()
if not SECRET_KEY:
    _key_file = DATA_DIR / "secret_key"
    if _key_file.exists():
        SECRET_KEY = _key_file.read_text(encoding="utf-8").strip()
    if not SECRET_KEY:
        SECRET_KEY = secrets.token_hex(32)
        _key_file.write_text(SECRET_KEY, encoding="utf-8")

# ---------------------------------------------------------------- Database
DB_PATH = Path(os.environ.get("DB_PATH", str(DATA_DIR / "inventory.db")))

# ---------------------------------------------------------------- Misc
DEMO_ADMIN_USER = os.environ.get("DEMO_ADMIN_USER", "admin").strip() or "admin"
DEMO_ADMIN_PASSWORD = os.environ.get("DEMO_ADMIN_PASSWORD", "admin123").strip() or "admin123"
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "0").strip() in ("1", "true", "yes")
PORT = int(os.environ.get("PORT", "5000") or "5000")
APP_NAME = "IT Equipment Management System"
