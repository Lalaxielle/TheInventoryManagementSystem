"""TheInventoryManagementSystem - Flask web application.

Pages: Login, Dashboard, Equipment (Model/Brand/Assigned), Warranty tracking
(Model/Brand/Assigned/Warranty Expiry), Borrow & Return, Maintenance,
Locations, Reports (CSV export) and Activity Log.
"""

import csv
import io
import os
from datetime import date, timedelta

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, session, url_for)

import config
from backend import security
from backend.models import (
    CATEGORIES, CONDITIONS, MAINT_STATUSES, MAINT_TYPES, STATUSES,
    WARRANTY_FILTERS, borrow_state, compute_stats, days_left, filter_equipment,
    fmt_date, fmt_ts, location_summary, maint_state, next_asset_tag, parse_date,
    renumber_plan, status_class, today_str, warranty_state,
)
from backend.store import get_store

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["TEMPLATES_AUTO_RELOAD"] = True

store = get_store()

PUBLIC_ENDPOINTS = ("login", "static", "favicon")


def _safe_next(destination):
    """Only allow redirecting to real app pages after login."""
    if not destination or not destination.startswith("/") or destination.startswith("//"):
        return "/dashboard"
    try:
        endpoint, _args = app.url_map.bind("localhost").match(destination)
    except Exception:
        return "/dashboard"
    if endpoint in ("login", "static", "favicon"):
        return "/dashboard"
    return destination


def _newest_first(item):
    """Dropdown sort key: highest IT-#### number first.

    Auto tags sort descending (IT-0019, IT-0018, ...) so a newly added device
    lands at the top of the list. Any non-standard tag sorts after the
    numbered ones, alphabetically.
    """
    tag = str(item.get("asset_tag") or "").strip().upper()
    if tag.startswith("IT-") and tag[3:].isdigit():
        return (0, -int(tag[3:]), tag)
    return (1, 0, tag)


# --------------------------------------------------------------------- guards
@app.before_request
def _guard():
    endpoint = request.endpoint
    if endpoint in PUBLIC_ENDPOINTS:
        if endpoint == "login":
            if "csrf" not in session:
                session["csrf"] = security.new_token()
            if session.get("user") and request.method == "GET":
                return redirect(url_for("dashboard"))
        return None
    if not session.get("user"):
        if request.method == "GET" and request.endpoint:
            session["next"] = request.full_path if request.query_string else request.path
        return redirect(url_for("login"))
    if request.method == "POST":
        token = session.get("csrf")
        if not token or request.form.get("csrf_token") != token:
            abort(400, description="Invalid or missing CSRF token. Refresh the page and try again.")
    return None


@app.after_request
def _no_cache_html(response):
    """Serve HTML fresh so UI changes appear without a hard refresh.

    Flask sends no Cache-Control header for rendered pages, which lets browsers
    heuristically cache them - so a removed button/chip can keep showing the old
    markup. HTML here is cheap, so always revalidate it.
    """
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.context_processor
def _inject_globals():
    return {
        "csrf_token": session.get("csrf", ""),
        "mode": store.mode,
        "mode_error": getattr(store, "error", None),
        "current_user": session.get("user"),
        "appName": config.APP_NAME,
        "warranty_state": warranty_state,
        "status_class": status_class,
        "borrow_state": borrow_state,
        "maint_state": maint_state,
        "fmt_date": fmt_date,
        "fmt_ts": fmt_ts,
        "today": today_str(),
        "STATUSES": STATUSES,
        "CATEGORIES": CATEGORIES,
        "CONDITIONS": CONDITIONS,
        "MAINT_TYPES": MAINT_TYPES,
        "MAINT_STATUSES": MAINT_STATUSES,
        "WARRANTY_FILTERS": WARRANTY_FILTERS,
    }


def _log(action, entity, detail):
    user = session.get("user") or {}
    try:
        store.log_activity(action, entity, detail, user.get("username", ""))
    except Exception:  # pragma: no cover - logging must never break a request
        pass


# ------------------------------------------------------------------- auth
@app.route("/")
def index():
    return redirect(url_for("dashboard" if session.get("user") else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = store.get_user(username) if username else None
        if user and security.verify_password(password, user.get("password_hash")):
            destination = _safe_next(session.get("next"))
            session.clear()
            session["user"] = {
                "id": user.get("id"),
                "username": user["username"],
                "full_name": user.get("full_name") or user["username"],
                "role": user.get("role") or "admin",
            }
            session["csrf"] = security.new_token()
            store.log_activity("LOGIN", "session",
                               f"Signed in as {user['username']}", user["username"])
            return redirect(destination)
        _log("LOGIN-FAILED", "session", f"Failed login attempt for '{username}'")
        flash("Invalid username or password.", "error")
    if "csrf" not in session:
        session["csrf"] = security.new_token()
    return render_template("login.html", page="login", title="Login",
                           demo=(store.mode == "demo"),
                           demo_user=config.DEMO_ADMIN_USER,
                           demo_pass=config.DEMO_ADMIN_PASSWORD)


@app.route("/logout", methods=["POST"])
def logout():
    _log("LOGOUT", "session", "Signed out")
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- dashboard
@app.route("/favicon.ico")
def favicon():
    # Serve the ITEQ brand mark rather than an empty response, so bookmarks and
    # clients that request /favicon.ico directly get the same icon as the pages.
    return redirect(url_for("static", filename="img/iteq.svg"))


@app.route("/dashboard")
def dashboard():
    equipment = store.all_equipment()
    maintenance = store.all_maintenance()
    borrowings = store.all_borrowings()
    stats = compute_stats(equipment, maintenance, borrowings)

    upcoming = sorted(
        [m for m in maintenance if (m.get("status") or "") in ("Scheduled", "In Progress")],
        key=lambda m: (m.get("scheduled_date") or ""),
    )[:5]

    loans = sorted(
        [b for b in borrowings if (b.get("status") or "") != "Returned"],
        key=lambda b: (b.get("due_date") or ""),
    )[:5]

    warranty_rows = sorted(
        [r for r in equipment
         if r.get("warranty_expiry") and (r.get("status") or "") != "Retired"],
        key=lambda r: (r.get("warranty_expiry") or ""),
    )[:6]

    return render_template(
        "dashboard.html", page="dashboard", title="Dashboard",
        subtitle="Real-time overview of every IT asset",
        stats=stats, upcoming=upcoming, loans=loans, warranty_rows=warranty_rows,
        activity=store.recent_activity(8),
    )


# ---------------------------------------------------- equipment / warranty
def _renumber_asset_tags():
    """Close the numbering gap after a record disappears.

    Asset tags are positional (IT-0001..IT-00N in list order) so the newest
    record always carries the number that matches the record count. Deleting a
    record shifts the later tags down instead of leaving a skipped number.
    """
    changes = renumber_plan(store.all_equipment())
    for equipment_id, new_tag in changes:
        store.update_equipment(equipment_id, {"asset_tag": new_tag})
    if changes:
        _log("UPDATE", "equipment",
             f"Asset tags renumbered after delete ({len(changes)} record(s) shifted)")
    return changes


def _handle_equipment_form(page):
    # A delete click must always win. If more than one control named "action"
    # is ever submitted, the first one would otherwise shadow the clicked
    # button - so honour "delete" if it appears anywhere in the form.
    posted_actions = request.form.getlist("action")
    if "delete" in posted_actions:
        action = "delete"
    else:
        action = posted_actions[0] if posted_actions else "save"
    equipment_id = (request.form.get("equipment_id") or "").strip()

    if action == "delete":
        row = store.get_equipment(equipment_id) if equipment_id else None
        if not row:
            flash("Select a record first, then press DELETE.", "error")
            return redirect(url_for(page))
        store.delete_equipment(equipment_id)
        _log("DELETE", row.get("asset_tag") or equipment_id,
             f"Deleted {row.get('model')} ({row.get('brand') or 'no brand'})")
        _renumber_asset_tags()
        flash(f"{row.get('model')} deleted.", "success")
        return redirect(url_for(page))

    # ---- save (create or update)
    data = {field: (request.form.get(field) or "").strip()
            for field in ("asset_tag", "model", "brand", "category", "serial_no",
                          "assigned_to", "location", "status", "condition",
                          "purchase_date", "warranty_expiry", "notes")}
    if not data["model"]:
        flash("MODEL is required.", "error")
        return redirect(url_for(page, edit=equipment_id or None))
    if not data["category"]:
        data["category"] = "Other"
    if not data["status"]:
        data["status"] = "In Stock"
    if data["purchase_date"] == "":
        data["purchase_date"] = None
    if data["warranty_expiry"] == "":
        data["warranty_expiry"] = None

    if equipment_id:
        row = store.get_equipment(equipment_id)
        if not row:
            flash("Record not found - it may have been deleted.", "error")
            return redirect(url_for(page))
        saved = store.update_equipment(equipment_id, data)
        _log("UPDATE", data.get("asset_tag") or equipment_id,
             f"Updated {data['model']} ({data['brand'] or 'no brand'})")
        flash(f"{data['model']} updated.", "success")
    else:
        if not data["asset_tag"]:
            data["asset_tag"] = next_asset_tag([r.get("asset_tag") for r in store.all_equipment()])
        saved = store.insert_equipment(data)
        _log("CREATE", data["asset_tag"],
             f"Registered {data['model']} ({data['brand'] or 'no brand'})")
        flash(f"{data['model']} added as {data['asset_tag']}.", "success")

    # Back to the default state: the list page with the drawer closed and the
    # form empty.  Previously this redirected to `?edit=<id>`, which re-opened
    # the drawer with the record that had just been saved still in every field.
    return redirect(url_for(page))


def _render_equipment(page, view, title, subtitle):
    if request.method == "POST":
        return _handle_equipment_form(page)

    q = (request.args.get("q") or "").strip()
    status = request.args.get("status", "")
    category = request.args.get("category", "")
    warranty = request.args.get("w", "") if view == "warranty" else ""
    rows = filter_equipment(store.all_equipment(), q=q, status=status,
                            category=category, warranty=warranty)

    form = None
    edit_id = (request.args.get("edit") or "").strip()
    if edit_id:
        form = store.get_equipment(edit_id)
        if not form:
            flash("Record not found - it may have been deleted.", "error")

    locations = sorted({(r.get("location") or "").strip()
                        for r in store.all_equipment() if (r.get("location") or "").strip()})

    return render_template(
        "equipment.html", page=page, title=title, subtitle=subtitle, view=view,
        rows=rows, q=q, f_status=status, f_category=category, f_warranty=warranty,
        form=form or {}, form_id=(form or {}).get("id"), locations=locations,
        editing=bool(form),
    )


@app.route("/equipment", methods=["GET", "POST"])
def equipment():
    return _render_equipment("equipment", "basic", "Equipment Inventory",
                             "Model, Brand, Assigned")


@app.route("/warranty", methods=["GET", "POST"])
def warranty():
    return _render_equipment("warranty", "warranty", "Warranty Tracking",
                             "Model, Brand, Assigned, Warranty Expiry")


# ------------------------------------------------------------- borrow/return
def _revert_after_loan(equipment_id):
    row = store.get_equipment(equipment_id)
    if row and (row.get("status") or "") == "Borrowed":
        store.update_equipment(equipment_id, {
            "status": "Assigned" if row.get("assigned_to") else "In Stock"})


def _revert_after_maintenance(equipment_id):
    row = store.get_equipment(equipment_id)
    if row and (row.get("status") or "") == "Under Maintenance":
        store.update_equipment(equipment_id, {
            "status": "Assigned" if row.get("assigned_to") else "In Stock"})


@app.route("/borrow", methods=["GET", "POST"])
def borrow():
    if request.method == "POST":
        action = request.form.get("action")
        borrowing_id = (request.form.get("borrowing_id") or "").strip()

        if action == "lend":
            equipment_id = (request.form.get("equipment_id") or "").strip()
            borrower = (request.form.get("borrower") or "").strip()
            equipment = store.get_equipment(equipment_id) if equipment_id else None
            if not equipment:
                flash("Choose the device to lend out.", "error")
                return redirect(url_for("borrow"))
            if not borrower:
                flash("Borrower name is required.", "error")
                return redirect(url_for("borrow"))
            if (equipment.get("status") or "") not in ("In Stock", "Assigned"):
                flash(f"{equipment['model']} is currently {equipment.get('status')} "
                      "and cannot be lent out.", "error")
                return redirect(url_for("borrow"))
            active = [b for b in store.all_borrowings()
                      if str(b.get("equipment_id")) == str(equipment_id)
                      and (b.get("status") or "") != "Returned"]
            if active:
                flash(f"{equipment['model']} already has an open borrowing record.", "error")
                return redirect(url_for("borrow"))
            store.insert_borrowing({
                "equipment_id": equipment_id,
                "borrower": borrower,
                "department": (request.form.get("department") or "").strip(),
                "purpose": (request.form.get("purpose") or "").strip(),
                "borrowed_date": request.form.get("borrowed_date") or today_str(),
                "due_date": request.form.get("due_date") or "",
                "status": "Borrowed",
            })
            store.update_equipment(equipment_id, {"status": "Borrowed"})
            _log("BORROW", equipment.get("asset_tag") or equipment_id,
                 f"{equipment['model']} issued to {borrower}")
            flash(f"{equipment['model']} issued to {borrower}.", "success")
            return redirect(url_for("borrow"))

        if action == "return":
            record = None
            for b in store.all_borrowings():
                if str(b.get("id")) == str(borrowing_id):
                    record = b
                    break
            if not record:
                flash("Borrowing record not found.", "error")
                return redirect(url_for("borrow"))
            store.update_borrowing(borrowing_id, {
                "status": "Returned", "returned_date": today_str()})
            _revert_after_loan(record.get("equipment_id"))
            _log("RETURN", record.get("asset_tag") or record.get("equipment_id"),
                 f"{record.get('model') or 'Device'} returned by {record.get('borrower')}")
            flash(f"{record.get('model') or 'Device'} returned by "
                  f"{record.get('borrower')}.", "success")
            return redirect(url_for("borrow"))

        if action == "delete":
            record = None
            for b in store.all_borrowings():
                if str(b.get("id")) == str(borrowing_id):
                    record = b
                    break
            if not record:
                flash("Borrowing record not found.", "error")
                return redirect(url_for("borrow"))
            if (record.get("status") or "") != "Returned":
                _revert_after_loan(record.get("equipment_id"))
            store.delete_borrowing(borrowing_id)
            _log("DELETE", record.get("asset_tag") or record.get("equipment_id"),
                 f"Borrowing record removed ({record.get('borrower')})")
            flash("Borrowing record deleted.", "success")
            return redirect(url_for("borrow"))

    status_filter = request.args.get("status", "")
    q = (request.args.get("q") or "").strip().lower()
    rows = store.all_borrowings()
    if status_filter == "active":
        rows = [b for b in rows if (b.get("status") or "") != "Returned"]
    elif status_filter == "returned":
        rows = [b for b in rows if (b.get("status") or "") == "Returned"]
    if q:
        rows = [b for b in rows if any(
            q in (b.get(f) or "").lower()
            for f in ("borrower", "department", "purpose", "model", "brand", "asset_tag"))]

    lent_out = {str(b.get("equipment_id")) for b in store.all_borrowings()
                if (b.get("status") or "") != "Returned"}
    available = [e for e in store.all_equipment()
                 if (e.get("status") or "") in ("In Stock", "Assigned")
                 and str(e.get("id")) not in lent_out]
    # Newest first: IT-0019, IT-0018, ... so a just-added device sits at the top.
    available.sort(key=_newest_first)

    return render_template(
        "borrow.html", page="borrow", title="Borrow & Return",
        subtitle="Issue devices to staff and track what is still out on loan",
        rows=rows, available=available, f_status=status_filter, q=q,
        default_due=(date.today() + timedelta(days=7)).isoformat(),
    )


# -------------------------------------------------------------- maintenance
def _equipment_in_maintenance(equipment_id):
    row = store.get_equipment(equipment_id)
    if row and (row.get("status") or "") in ("In Stock", "Assigned"):
        store.update_equipment(equipment_id, {"status": "Under Maintenance"})


@app.route("/maintenance", methods=["GET", "POST"])
def maintenance():
    if request.method == "POST":
        action = request.form.get("action")
        maintenance_id = (request.form.get("maintenance_id") or "").strip()

        if action == "schedule":
            equipment_id = (request.form.get("equipment_id") or "").strip()
            equipment = store.get_equipment(equipment_id) if equipment_id else None
            if not equipment:
                flash("Choose the device for this maintenance job.", "error")
                return redirect(url_for("maintenance"))
            scheduled = request.form.get("scheduled_date") or today_str()
            store.insert_maintenance({
                "equipment_id": equipment_id,
                "mtype": request.form.get("mtype") or "Preventive",
                "description": (request.form.get("description") or "").strip(),
                "scheduled_date": scheduled,
                "status": "Scheduled",
                "technician": (request.form.get("technician") or "").strip(),
            })
            scheduled_day = parse_date(scheduled)
            if scheduled_day and scheduled_day <= date.today():
                _equipment_in_maintenance(equipment_id)
            _log("MAINTENANCE", equipment.get("asset_tag") or equipment_id,
                 f"Maintenance scheduled for {equipment['model']} on {scheduled}")
            flash(f"Maintenance scheduled for {equipment['model']} on {fmt_date(scheduled)}.",
                  "success")
            return redirect(url_for("maintenance"))

        record = None
        for m in store.all_maintenance():
            if str(m.get("id")) == str(maintenance_id):
                record = m
                break
        if not record and action in ("start", "complete", "delete"):
            flash("Maintenance record not found.", "error")
            return redirect(url_for("maintenance"))

        if action == "start":
            store.update_maintenance(maintenance_id, {"status": "In Progress"})
            _equipment_in_maintenance(record.get("equipment_id"))
            _log("MAINTENANCE", record.get("asset_tag") or record.get("equipment_id"),
                 f"Work started: {record.get('description') or record.get('mtype')}")
            flash("Maintenance marked as In Progress.", "success")
            return redirect(url_for("maintenance"))

        if action == "complete":
            store.update_maintenance(maintenance_id, {
                "status": "Completed", "completed_date": today_str()})
            _revert_after_maintenance(record.get("equipment_id"))
            _log("MAINTENANCE", record.get("asset_tag") or record.get("equipment_id"),
                 f"Completed: {record.get('description') or record.get('mtype')}")
            flash("Maintenance completed.", "success")
            return redirect(url_for("maintenance"))

        if action == "delete":
            if (record.get("status") or "") != "Completed":
                _revert_after_maintenance(record.get("equipment_id"))
            store.delete_maintenance(maintenance_id)
            _log("DELETE", record.get("asset_tag") or record.get("equipment_id"),
                 f"Maintenance record removed ({record.get('mtype')})")
            flash("Maintenance record deleted.", "success")
            return redirect(url_for("maintenance"))

    status_filter = request.args.get("status", "")
    rows = store.all_maintenance()
    if status_filter == "Overdue":
        rows = [m for m in rows if maint_state(m)[0] == "OVERDUE"]
    elif status_filter:
        rows = [m for m in rows if (m.get("status") or "") == status_filter]

    lendable = [e for e in store.all_equipment() if (e.get("status") or "") != "Retired"]

    return render_template(
        "maintenance.html", page="maintenance", title="Maintenance",
        subtitle="Schedule, track and complete preventive and corrective work",
        rows=rows, lendable=lendable, f_status=status_filter, default_date=today_str(),
    )


# ---------------------------------------------------------------- locations
@app.route("/locations")
def locations():
    equipment = store.all_equipment()
    groups = location_summary(equipment)
    by_location = {}
    for row in equipment:
        name = (row.get("location") or "").strip() or "Unassigned"
        by_location.setdefault(name, []).append(row)
    return render_template(
        "locations.html", page="locations", title="Locations",
        subtitle="Where every device is right now", groups=groups, by_location=by_location,
    )


# ------------------------------------------------------------------ reports
def _csv_response(rows, columns, filename):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(col, "") for col in columns])
    data = "﻿" + buffer.getvalue()
    return Response(data, mimetype="text/csv; charset=utf-8", headers={
        "Content-Disposition": f"attachment; filename={filename}"})


@app.route("/reports")
def reports():
    equipment = store.all_equipment()
    maintenance = store.all_maintenance()
    borrowings = store.all_borrowings()
    stats = compute_stats(equipment, maintenance, borrowings)
    warranty_rows = sorted(
        [r for r in equipment if r.get("warranty_expiry")],
        key=lambda r: (r.get("warranty_expiry") or ""),
    )
    return render_template(
        "reports.html", page="reports", title="Reports",
        subtitle="Inventory summaries and CSV exports", stats=stats,
        equipment=equipment, borrowings=borrowings, maintenance=maintenance,
        warranty_rows=warranty_rows, locations=location_summary(equipment),
    )


@app.route("/export/<kind>.csv")
def export(kind):
    if kind == "equipment":
        rows = store.all_equipment()
        columns = ["asset_tag", "model", "brand", "category", "serial_no", "assigned_to",
                   "location", "status", "condition", "purchase_date", "warranty_expiry", "notes"]
        return _csv_response(rows, columns, "equipment.csv")
    if kind == "warranty":
        rows = sorted([r for r in store.all_equipment() if r.get("warranty_expiry")],
                      key=lambda r: (r.get("warranty_expiry") or ""))
        columns = ["asset_tag", "model", "brand", "assigned_to", "warranty_expiry", "status"]
        return _csv_response(rows, columns, "warranty.csv")
    if kind == "borrowings":
        columns = ["asset_tag", "model", "brand", "borrower", "department", "purpose",
                   "borrowed_date", "due_date", "returned_date", "status"]
        return _csv_response(store.all_borrowings(), columns, "borrowings.csv")
    if kind == "maintenance":
        columns = ["asset_tag", "model", "brand", "mtype", "description", "scheduled_date",
                   "completed_date", "status", "technician", "cost"]
        return _csv_response(store.all_maintenance(), columns, "maintenance.csv")
    if kind == "activity":
        columns = ["created_at", "username", "action", "entity", "detail"]
        return _csv_response(store.recent_activity(1000), columns, "activity.csv")
    abort(404)


# -------------------------------------------------------------- activity log
@app.route("/activity")
def activity():
    action_filter = request.args.get("action", "")
    q = (request.args.get("q") or "").strip().lower()
    rows = store.recent_activity(500)
    actions = sorted({(r.get("action") or "") for r in rows})
    if action_filter:
        rows = [r for r in rows if (r.get("action") or "") == action_filter]
    if q:
        rows = [r for r in rows if any(
            q in (r.get(f) or "").lower() for f in ("detail", "entity", "username"))]
    return render_template(
        "activity.html", page="activity", title="Activity Log",
        subtitle="Audit trail of everything done in the system",
        rows=rows, actions=actions, f_action=action_filter, q=q,
    )


# --------------------------------------------------------------------- about
TEAM = [
    {"name": "Alexa Nicole C. Abril", "roles": ["Project Manager", "Backend / Database Developer"]},
    {"name": "Alaricquisha A. Angeles", "roles": ["CEO", "Frontend Developer"]},
    {"name": "Edrio May D. Marquez", "roles": ["System Owner", "Web Administrator"]},
]


@app.route("/about")
def about():
    return render_template(
        "about.html", page="about", title="About",
        subtitle="About this system and the team behind it",
        team=TEAM,
    )


# ------------------------------------------------------------- error pages
@app.errorhandler(404)
def _not_found(_error):
    return render_template("error.html", code=404,
                           message="That page does not exist."), 404


@app.errorhandler(400)
def _bad_request(error):
    return render_template("error.html", code=400,
                           message=getattr(error, "description", "Bad request.")), 400


@app.errorhandler(500)
def _server_error(_error):
    return render_template("error.html", code=500,
                           message="Something went wrong. Check the server console "
                                   "for details."), 500


if __name__ == "__main__":
    print(f" * {config.APP_NAME}")
    print(f" * Data source : {'Supabase (' + config.SUPABASE_URL + ')' if config.USE_SUPABASE else 'Local DEMO database (SQLite)'}")
    if store.error:
        print(f" * WARNING      : {store.error}")
    print(f" * Opening     : http://127.0.0.1:{config.PORT}")
    app.run(host="127.0.0.1", port=config.PORT, debug=config.FLASK_DEBUG)
