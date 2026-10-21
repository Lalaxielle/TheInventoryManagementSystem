"""Domain constants and pure helper functions shared by stores, routes and templates."""

from datetime import date, datetime, timedelta, timezone

import config

# --------------------------------------------------------------- clock (PHT)
# Every date/time the app shows or stamps is Philippine Standard Time (UTC+8),
# independent of whatever timezone the machine is set to. The Philippines has
# had no DST since 1978, so the fixed +08:00 fallback is exact; the real zone
# is preferred when the host has a tz database.
try:
    from zoneinfo import ZoneInfo

    PH_TZ = ZoneInfo(config.TIMEZONE)
except Exception:  # pragma: no cover - Windows without tzdata
    PH_TZ = timezone(timedelta(hours=8), "PHT")


def now_ph() -> datetime:
    """Current time in Philippine Standard Time (UTC+8)."""
    return datetime.now(PH_TZ)


def today_ph() -> date:
    """Current date in Philippine Standard Time."""
    return now_ph().date()


# ------------------------------------------------------------------ statuses
STATUS_IN_STOCK = "In Stock"
STATUS_ASSIGNED = "Assigned"
STATUS_BORROWED = "Borrowed"
STATUS_MAINTENANCE = "Under Maintenance"
STATUS_RETIRED = "Retired"
STATUS_AVAILABLE = "Available"
STATUS_LOST = "Lost"
STATUSES = [
    STATUS_IN_STOCK, STATUS_ASSIGNED, STATUS_BORROWED, STATUS_MAINTENANCE,
    STATUS_RETIRED, STATUS_AVAILABLE, STATUS_LOST,
]

CATEGORIES = [
    "Laptop", "Desktop", "Monitor", "Printer", "Phone", "Tablet",
    "Server", "Network", "Storage", "Peripheral", "Other",
]
CONDITIONS = ["Good", "Fair", "Poor", "Damaged"]
MAINT_TYPES = ["Preventive", "Repair", "Inspection", "Upgrade", "Other"]
MAINT_STATUSES = ["Scheduled", "In Progress", "Completed"]

WARRANTY_FILTERS = [
    ("", "All warranty"),
    ("expired", "Expired"),
    ("30", "Expiring <= 30 days"),
    ("90", "Expiring <= 90 days"),
    ("ok", "Active (> 90 days)"),
    ("none", "No warranty date"),
]

EQUIPMENT_FIELDS = [
    "asset_tag", "model", "brand", "category", "serial_no", "assigned_to",
    "location", "status", "condition", "purchase_date", "warranty_expiry", "notes",
]


# ------------------------------------------------------------------ date helpers
def now_str() -> str:
    """Timestamp (Philippine Standard Time), stored as 'YYYY-MM-DD HH:MM:SS'."""
    return now_ph().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return today_ph().isoformat()


def parse_date(value) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def days_left(value) -> int | None:
    day = parse_date(value)
    return (day - today_ph()).days if day else None


def warranty_state(value):
    """Return (label, css_class, days_left) for a warranty expiry date."""
    left = days_left(value)
    if left is None:
        return ("NO DATE", "badge-none", None)
    if left < 0:
        return ("EXPIRED", "badge-expired", left)
    if left <= 30:
        return ("EXPIRING", "badge-critical", left)
    if left <= 90:
        return ("DUE SOON", "badge-warning", left)
    return ("ACTIVE", "badge-ok", left)


def fmt_date(value) -> str:
    day = parse_date(value)
    return day.strftime("%b %d, %Y") if day else "-"


def civil_time(dt: datetime) -> str:
    """12-hour civilian clock: '3:44 PM' - uppercase AM/PM and no leading
    zero (the %-I flag is Windows-only, hence the arithmetic). User asked for
    "standard civic time" instead of the 24-hour '15:44'."""
    return f"{dt.hour % 12 or 12}:{dt:%M} {dt:%p}"


def fmt_ts(value) -> str:
    """Format a timestamp coming from SQLite text or Supabase timestamptz."""
    if not value:
        return "-"
    text = str(value).strip()
    try:
        if len(text) == 10:
            return date.fromisoformat(text).strftime("%b %d, %Y")
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(PH_TZ)
        return f"{dt:%b %d, %Y} {civil_time(dt)} PHT"
    except ValueError:
        return text


# ------------------------------------------------------------------ badge helpers
STATUS_CLASSES = {
    STATUS_IN_STOCK: "st-stock",
    STATUS_ASSIGNED: "st-assigned",
    STATUS_BORROWED: "st-borrowed",
    STATUS_MAINTENANCE: "st-maint",
    STATUS_RETIRED: "st-retired",
    STATUS_AVAILABLE: "st-available",
    STATUS_LOST: "st-lost",
}


def status_class(status: str) -> str:
    return STATUS_CLASSES.get(status, "st-assigned")


def borrow_state(row: dict):
    """Return (label, css_class) for a borrowing record."""
    if (row.get("status") or "") == "Returned":
        return ("RETURNED", "b-back")
    due = parse_date(row.get("due_date"))
    if due and due < today_ph():
        return ("OVERDUE", "b-late")
    return ("ON LOAN", "b-out")


def maint_state(row: dict):
    """Return (label, css_class) for a maintenance record."""
    status = row.get("status") or "Scheduled"
    if status == "Completed":
        return ("COMPLETED", "m-done")
    if status == "In Progress":
        return ("IN PROGRESS", "m-prog")
    scheduled = parse_date(row.get("scheduled_date"))
    if scheduled and scheduled < today_ph():
        return ("OVERDUE", "m-late")
    return ("SCHEDULED", "m-sched")


# ------------------------------------------------------------------ filtering
def filter_equipment(rows, q=None, status="", category="", location="", warranty=""):
    out = list(rows)
    if q:
        needle = q.strip().lower()
        out = [
            r for r in out
            if any(
                needle in (r.get(field) or "").lower()
                for field in ("asset_tag", "model", "brand", "assigned_to",
                              "serial_no", "location", "category")
            )
        ]
    if status:
        out = [r for r in out if (r.get("status") or "") == status]
    if category:
        out = [r for r in out if (r.get("category") or "") == category]
    if location:
        out = [r for r in out if (r.get("location") or "") == location]
    if warranty:
        kept = []
        for row in out:
            left = days_left(row.get("warranty_expiry"))
            if warranty == "expired" and left is not None and left < 0:
                kept.append(row)
            elif warranty in ("30", "90") and left is not None and 0 <= left <= int(warranty):
                kept.append(row)
            elif warranty == "ok" and left is not None and left > 90:
                kept.append(row)
            elif warranty == "none" and left is None:
                kept.append(row)
        out = kept
    return out


def sort_equipment(rows):
    return sorted(rows, key=lambda r: ((r.get("asset_tag") or "~"), (r.get("model") or "")))


def sort_maintenance(rows):
    return sorted(rows, key=lambda r: (r.get("scheduled_date") or ""), reverse=True)


def sort_borrowings(rows):
    return sorted(rows, key=lambda r: (r.get("borrowed_date") or ""), reverse=True)


def sort_activity(rows):
    return sorted(rows, key=lambda r: (r.get("created_at") or ""), reverse=True)


# ------------------------------------------------------------------ aggregates
def location_summary(rows):
    """Group equipment by location: [{'location': .., 'total': .., 'by_status': {..}}, ...]"""
    groups: dict[str, dict] = {}
    for row in rows:
        name = (row.get("location") or "").strip() or "Unassigned"
        group = groups.setdefault(name, {"location": name, "total": 0, "by_status": {}})
        group["total"] += 1
        status = row.get("status") or STATUS_IN_STOCK
        group["by_status"][status] = group["by_status"].get(status, 0) + 1
    return sorted(groups.values(), key=lambda g: (-g["total"], g["location"]))


def compute_stats(equipment, maintenance, borrowings) -> dict:
    by_status = {s: 0 for s in STATUSES}
    by_category: dict[str, int] = {}
    by_brand: dict[str, int] = {}
    warranty = {"expired": 0, "exp30": 0, "exp90": 0, "active": 0, "none": 0}

    for row in equipment:
        status = row.get("status") or STATUS_IN_STOCK
        by_status[status] = by_status.get(status, 0) + 1
        category = (row.get("category") or "Other").strip() or "Other"
        by_category[category] = by_category.get(category, 0) + 1
        brand = (row.get("brand") or "Unknown").strip() or "Unknown"
        by_brand[brand] = by_brand.get(brand, 0) + 1
        left = days_left(row.get("warranty_expiry"))
        if left is None:
            warranty["none"] += 1
        elif left < 0:
            warranty["expired"] += 1
        elif left <= 30:
            warranty["exp30"] += 1
        elif left <= 90:
            warranty["exp90"] += 1
        else:
            warranty["active"] += 1

    today = today_ph()
    active_loans, overdue_loans = [], []
    for row in borrowings:
        if (row.get("status") or "") == "Returned":
            continue
        active_loans.append(row)
        due = parse_date(row.get("due_date"))
        if due and due < today:
            overdue_loans.append(row)

    maint_open, maint_overdue = [], []
    for row in maintenance:
        if (row.get("status") or "") == "Scheduled":
            maint_open.append(row)
            scheduled = parse_date(row.get("scheduled_date"))
            if scheduled and scheduled < today:
                maint_overdue.append(row)

    locations = {((r.get("location") or "").strip() or "Unassigned") for r in equipment}

    return {
        "total": len(equipment),
        "by_status": by_status,
        "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        "by_brand": dict(sorted(by_brand.items(), key=lambda kv: -kv[1])),
        "warranty": warranty,
        "active_loans": len(active_loans),
        "overdue_loans": len(overdue_loans),
        "maint_open": len(maint_open),
        "maint_overdue": len(maint_overdue),
        "locations": len(locations),
    }


def renumber_plan(rows):
    """Plan the asset tags for *rows*, which must already be in display order.

    Asset tags are positional: the first record is IT-0001, the next IT-0002 and
    so on, so the newest record always carries the highest number - equal to the
    number of records. Deleting a record therefore closes the gap instead of
    leaving a skipped number behind.

    Returns ``[(equipment_id, new_tag), ...]`` for the rows that need changing.
    """
    changes = []
    for index, row in enumerate(rows, start=1):
        new_tag = f"IT-{index:04d}"
        if (row.get("asset_tag") or "").strip().upper() != new_tag:
            changes.append((row.get("id"), new_tag))
    return changes


def next_asset_tag(existing_tags) -> str:
    """Generate the next IT-0001 style asset tag that is not in use."""
    used = {str(t).strip().upper() for t in existing_tags if t}
    highest = 0
    for tag in used:
        if tag.startswith("IT-") and tag[3:].isdigit():
            highest = max(highest, int(tag[3:]))
    candidate = highest + 1
    while f"IT-{candidate:04d}" in used:
        candidate += 1
    return f"IT-{candidate:04d}"
