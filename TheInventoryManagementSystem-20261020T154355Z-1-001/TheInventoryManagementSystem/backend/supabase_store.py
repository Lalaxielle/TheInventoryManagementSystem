"""Supabase data store - talks to Supabase's PostgREST API with plain HTTP.

Uses the server-side `service_role` key, so Row Level Security can stay
enabled with no public policies (only this backend can touch the data).
"""

import requests

from backend.models import (
    EQUIPMENT_FIELDS, now_ph, sort_activity, sort_borrowings,
    sort_equipment, sort_maintenance,
)

TIMEOUT = 20

#: Columns that are real `date` types in Postgres. An empty string is NOT a
#: valid date there ("invalid input syntax for type date: \"\""), so blank
#: values must be sent as JSON null instead.
DATE_FIELDS = ("purchase_date", "warranty_expiry")


class SupabaseError(RuntimeError):
    pass


class SupabaseStore:
    mode = "supabase"
    error = None

    def __init__(self, url, service_role_key):
        self.base = url.rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }

    # ---------------------------------------------------------------- plumbing
    def _check(self, response):
        if response.status_code >= 400:
            raise SupabaseError(f"HTTP {response.status_code}: {response.text[:300]}")
        return response

    def _get(self, table, params=None):
        response = self._check(requests.get(
            f"{self.base}/{table}", headers=self.headers, params=params, timeout=TIMEOUT
        ))
        return response.json()

    def _post(self, table, payload):
        headers = dict(self.headers, **{"Prefer": "return=representation"})
        response = self._check(requests.post(
            f"{self.base}/{table}", headers=headers, json=payload, timeout=TIMEOUT
        ))
        return response.json()

    def _patch(self, table, row_id, payload):
        headers = dict(self.headers, **{"Prefer": "return=representation"})
        response = self._check(requests.patch(
            f"{self.base}/{table}", headers=headers, params={"id": f"eq.{row_id}"},
            json=payload, timeout=TIMEOUT,
        ))
        return response.json()

    def _delete(self, table, row_id):
        response = self._check(requests.delete(
            f"{self.base}/{table}", headers=self.headers,
            params={"id": f"eq.{row_id}"}, timeout=TIMEOUT,
        ))
        # PostgREST answers 204 No Content with an empty body.
        if not response.content:
            return []
        return response.json()

    def ping(self):
        try:
            self._get("equipment", {"select": "id", "limit": 1})
        except Exception as exc:  # pragma: no cover - depends on network
            raise SupabaseError(str(exc)) from exc

    # ------------------------------------------------------------------ users
    def get_user(self, username):
        rows = self._get("users", {"username": f"eq.{username}", "select": "*"})
        return rows[0] if rows else None

    def create_user(self, username, password_hash, full_name="", role="admin"):
        self._post("users", {
            "username": username.strip(), "password_hash": password_hash,
            "full_name": full_name, "role": role,
        })

    def count_users(self):
        rows = self._get("users", {"select": "id"})
        return len(rows)

    # -------------------------------------------------------------- equipment
    def all_equipment(self):
        return sort_equipment(self._get("equipment", {"select": "*"}))

    def get_equipment(self, equipment_id):
        rows = self._get("equipment", {"id": f"eq.{equipment_id}", "select": "*"})
        return rows[0] if rows else None

    @staticmethod
    def _clean_value(field, value):
        """Normalise one column value for PostgREST.

        Empty date fields become SQL NULL: Postgres rejects ``""`` for a
        ``date`` column, which used to surface as an HTTP 400 (and therefore a
        500 page) whenever equipment was saved with blank date fields.
        """
        if isinstance(value, str):
            value = value.strip()
        if field in DATE_FIELDS and value == "":
            return None
        return value

    def insert_equipment(self, data):
        payload = {field: self._clean_value(field, data.get(field))
                   for field in EQUIPMENT_FIELDS}
        rows = self._post("equipment", payload)
        return rows[0] if rows else None

    def update_equipment(self, equipment_id, data):
        payload = {k: self._clean_value(k, v)
                   for k, v in data.items() if k in EQUIPMENT_FIELDS}
        if not payload:
            return self.get_equipment(equipment_id)
        payload["updated_at"] = now_ph().isoformat()
        rows = self._patch("equipment", equipment_id, payload)
        return rows[0] if rows else self.get_equipment(equipment_id)

    def delete_equipment(self, equipment_id):
        # dependent borrowings / maintenance rows are removed by ON DELETE CASCADE
        self._delete("equipment", equipment_id)

    def equipment_ids(self):
        return [row["id"] for row in self._get("equipment", {"select": "id"})]

    # ------------------------------------------------------------- maintenance
    def all_maintenance(self):
        rows = self._get("maintenance", {"select": "*,equipment(model,brand,asset_tag)"})
        out = []
        for row in rows:
            nested = row.pop("equipment", None) or {}
            row.update({
                "model": nested.get("model"), "brand": nested.get("brand"),
                "asset_tag": nested.get("asset_tag"),
            })
            out.append(row)
        return sort_maintenance(out)

    def insert_maintenance(self, data):
        payload = {
            "equipment_id": data.get("equipment_id"),
            "mtype": data.get("mtype") or "Preventive",
            "description": data.get("description") or "",
            "scheduled_date": data.get("scheduled_date") or None,
            "completed_date": data.get("completed_date") or None,
            "status": data.get("status") or "Scheduled",
            "technician": data.get("technician") or "",
            "cost": data.get("cost") or 0,
        }
        self._post("maintenance", payload)

    def update_maintenance(self, maintenance_id, data):
        allowed = {"mtype", "description", "scheduled_date", "completed_date",
                   "status", "technician", "cost"}
        payload = {k: v for k, v in data.items() if k in allowed and v is not None}
        if payload:
            self._patch("maintenance", maintenance_id, payload)

    def delete_maintenance(self, maintenance_id):
        self._delete("maintenance", maintenance_id)

    # -------------------------------------------------------------- borrowings
    def all_borrowings(self):
        rows = self._get("borrowings", {"select": "*,equipment(model,brand,asset_tag)"})
        out = []
        for row in rows:
            nested = row.pop("equipment", None) or {}
            row.update({
                "model": nested.get("model"), "brand": nested.get("brand"),
                "asset_tag": nested.get("asset_tag"),
            })
            out.append(row)
        return sort_borrowings(out)

    def insert_borrowing(self, data):
        payload = {
            "equipment_id": data.get("equipment_id"),
            "borrower": data.get("borrower") or "",
            "department": data.get("department") or "",
            "purpose": data.get("purpose") or "",
            "borrowed_date": data.get("borrowed_date") or None,
            "due_date": data.get("due_date") or None,
            "returned_date": data.get("returned_date") or None,
            "status": data.get("status") or "Borrowed",
            "notes": data.get("notes") or "",
        }
        self._post("borrowings", payload)

    def update_borrowing(self, borrowing_id, data):
        allowed = {"borrower", "department", "purpose", "borrowed_date",
                   "due_date", "returned_date", "status", "notes"}
        payload = {k: v for k, v in data.items() if k in allowed and v is not None}
        if payload:
            self._patch("borrowings", borrowing_id, payload)

    def delete_borrowing(self, borrowing_id):
        self._delete("borrowings", borrowing_id)

    # ---------------------------------------------------------------- activity
    def log_activity(self, action, entity, detail, username=""):
        self._post("activity_log", {
            "action": action, "entity": str(entity or ""),
            "detail": detail or "", "username": username or "",
        })

    def recent_activity(self, limit=100):
        rows = self._get("activity_log", {
            "select": "*", "order": "created_at.desc", "limit": limit,
        })
        return sort_activity(rows)
