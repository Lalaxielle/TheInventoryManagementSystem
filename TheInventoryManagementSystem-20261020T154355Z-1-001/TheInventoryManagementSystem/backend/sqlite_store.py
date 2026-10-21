"""SQLite data store - used when Supabase credentials are not configured (DEMO mode).

The schema mirrors `database/schema.sql` so the app behaves the same way
in DEMO mode and against a real Supabase project.
"""

import sqlite3
from pathlib import Path

from backend import seed
from backend.models import (
    EQUIPMENT_FIELDS, now_str, sort_activity, sort_borrowings,
    sort_equipment, sort_maintenance,
)
from backend.security import hash_password

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT DEFAULT '',
    role          TEXT DEFAULT 'admin',
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS equipment (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_tag       TEXT,
    model           TEXT NOT NULL,
    brand           TEXT,
    category        TEXT,
    serial_no       TEXT,
    assigned_to     TEXT,
    location        TEXT,
    status          TEXT DEFAULT 'In Stock',
    condition       TEXT DEFAULT 'Good',
    purchase_date   TEXT,
    warranty_expiry TEXT,
    notes           TEXT,
    created_at      TEXT,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS maintenance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id    INTEGER NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
    mtype           TEXT,
    description     TEXT,
    scheduled_date  TEXT,
    completed_date  TEXT,
    status          TEXT DEFAULT 'Scheduled',
    technician      TEXT,
    cost            REAL DEFAULT 0,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS borrowings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id  INTEGER NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
    borrower      TEXT,
    department    TEXT,
    purpose       TEXT,
    borrowed_date TEXT,
    due_date      TEXT,
    returned_date TEXT,
    status        TEXT DEFAULT 'Borrowed',
    notes         TEXT,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS activity_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    action     TEXT,
    entity     TEXT,
    detail     TEXT,
    username   TEXT,
    created_at TEXT
);
"""

EQ_COLS = ",".join(EQUIPMENT_FIELDS)


class SqliteStore:
    mode = "demo"
    error = None

    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # ---------------------------------------------------------------- plumbing
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA_SQL)
            empty = conn.execute("SELECT COUNT(*) FROM equipment").fetchone()[0] == 0
            if empty:
                self._seed(conn)

    def _seed(self, conn):
        now = now_str()
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role, created_at) "
            "VALUES (?, ?, ?, 'admin', ?)",
            (seed.ADMIN_USERNAME, hash_password(seed.ADMIN_PASSWORD),
             seed.ADMIN_FULL_NAME, now),
        )
        tag_to_id = {}
        for row in seed.EQUIPMENT:
            cur = conn.execute(
                f"INSERT INTO equipment ({EQ_COLS}, created_at, updated_at) "
                f"VALUES ({','.join('?' * (len(EQUIPMENT_FIELDS) + 2))})",
                list(row) + [now, now],
            )
            tag_to_id[row[0]] = cur.lastrowid
        for tag, mtype, desc, sched, done, status, tech, cost in seed.MAINTENANCE:
            conn.execute(
                "INSERT INTO maintenance (equipment_id, mtype, description, scheduled_date, "
                "completed_date, status, technician, cost, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (tag_to_id[tag], mtype, desc, sched, done, status, tech, cost, now),
            )
        for tag, borrower, dept, purpose, bdate, ddate, rdate, status, notes in seed.BORROWINGS:
            conn.execute(
                "INSERT INTO borrowings (equipment_id, borrower, department, purpose, "
                "borrowed_date, due_date, returned_date, status, notes, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (tag_to_id[tag], borrower, dept, purpose, bdate, ddate, rdate, status, notes, now),
            )
        for action, entity, detail, created in seed.ACTIVITY:
            conn.execute(
                "INSERT INTO activity_log (action, entity, detail, username, created_at) "
                "VALUES (?,?,?,?,?)",
                (action, entity, detail, seed.ADMIN_USERNAME, created),
            )

    # ------------------------------------------------------------------ users
    def get_user(self, username):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (str(username).strip(),)
            ).fetchone()
            return dict(row) if row else None

    def create_user(self, username, password_hash, full_name="", role="admin"):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username.strip(), password_hash, full_name, role, now_str()),
            )

    def count_users(self):
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    # -------------------------------------------------------------- equipment
    def all_equipment(self):
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM equipment").fetchall()
        return sort_equipment(dict(r) for r in rows)

    def get_equipment(self, equipment_id):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM equipment WHERE id = ?", (equipment_id,)
            ).fetchone()
            return dict(row) if row else None

    def insert_equipment(self, data):
        payload = {field: (data.get(field) or "").strip() for field in EQUIPMENT_FIELDS}
        payload["model"] = data.get("model", "").strip()
        now = now_str()
        cols = ",".join(list(payload) + ["created_at", "updated_at"])
        marks = ",".join("?" * (len(payload) + 2))
        with self._conn() as conn:
            cur = conn.execute(
                f"INSERT INTO equipment ({cols}) VALUES ({marks})",
                list(payload.values()) + [now, now],
            )
            return self.get_equipment(cur.lastrowid)

    def update_equipment(self, equipment_id, data):
        payload = {k: (v or "").strip() for k, v in data.items() if k in EQUIPMENT_FIELDS}
        if not payload:
            return self.get_equipment(equipment_id)
        sets = ",".join(f"{k} = ?" for k in payload)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE equipment SET {sets}, updated_at = ? WHERE id = ?",
                list(payload.values()) + [now_str(), equipment_id],
            )
        return self.get_equipment(equipment_id)

    def delete_equipment(self, equipment_id):
        with self._conn() as conn:
            conn.execute("DELETE FROM borrowings WHERE equipment_id = ?", (equipment_id,))
            conn.execute("DELETE FROM maintenance WHERE equipment_id = ?", (equipment_id,))
            conn.execute("DELETE FROM equipment WHERE id = ?", (equipment_id,))

    def equipment_ids(self):
        with self._conn() as conn:
            return [r[0] for r in conn.execute("SELECT id FROM equipment").fetchall()]

    # ------------------------------------------------------------- maintenance
    def all_maintenance(self):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT m.*, e.model, e.brand, e.asset_tag FROM maintenance m "
                "LEFT JOIN equipment e ON e.id = m.equipment_id"
            ).fetchall()
        return sort_maintenance(dict(r) for r in rows)

    def insert_maintenance(self, data):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO maintenance (equipment_id, mtype, description, scheduled_date, "
                "completed_date, status, technician, cost, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (data.get("equipment_id"), data.get("mtype") or "Preventive",
                 data.get("description") or "", data.get("scheduled_date") or "",
                 data.get("completed_date") or "", data.get("status") or "Scheduled",
                 data.get("technician") or "", data.get("cost") or 0, now_str()),
            )

    def update_maintenance(self, maintenance_id, data):
        allowed = {"mtype", "description", "scheduled_date", "completed_date",
                   "status", "technician", "cost"}
        payload = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not payload:
            return
        sets = ",".join(f"{k} = ?" for k in payload)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE maintenance SET {sets} WHERE id = ?",
                list(payload.values()) + [maintenance_id],
            )

    def delete_maintenance(self, maintenance_id):
        with self._conn() as conn:
            conn.execute("DELETE FROM maintenance WHERE id = ?", (maintenance_id,))

    # -------------------------------------------------------------- borrowings
    def all_borrowings(self):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT b.*, e.model, e.brand, e.asset_tag FROM borrowings b "
                "LEFT JOIN equipment e ON e.id = b.equipment_id"
            ).fetchall()
        return sort_borrowings(dict(r) for r in rows)

    def insert_borrowing(self, data):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO borrowings (equipment_id, borrower, department, purpose, "
                "borrowed_date, due_date, returned_date, status, notes, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (data.get("equipment_id"), data.get("borrower") or "",
                 data.get("department") or "", data.get("purpose") or "",
                 data.get("borrowed_date") or "", data.get("due_date") or "",
                 data.get("returned_date") or "", data.get("status") or "Borrowed",
                 data.get("notes") or "", now_str()),
            )

    def update_borrowing(self, borrowing_id, data):
        allowed = {"borrower", "department", "purpose", "borrowed_date",
                   "due_date", "returned_date", "status", "notes"}
        payload = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not payload:
            return
        sets = ",".join(f"{k} = ?" for k in payload)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE borrowings SET {sets} WHERE id = ?",
                list(payload.values()) + [borrowing_id],
            )

    def delete_borrowing(self, borrowing_id):
        with self._conn() as conn:
            conn.execute("DELETE FROM borrowings WHERE id = ?", (borrowing_id,))

    # ---------------------------------------------------------------- activity
    def log_activity(self, action, entity, detail, username=""):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO activity_log (action, entity, detail, username, created_at) "
                "VALUES (?,?,?,?,?)",
                (action, str(entity or ""), detail or "", username or "", now_str()),
            )

    def recent_activity(self, limit=100):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return sort_activity(dict(r) for r in rows)
