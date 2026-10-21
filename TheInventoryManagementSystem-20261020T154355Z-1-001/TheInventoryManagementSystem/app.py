"""TheInventoryManagementSystem - Flask web application.

Pages: Login, Dashboard, Equipment (Model/Brand/Assigned), Warranty tracking
(Model/Brand/Assigned/Warranty Expiry), Borrow & Return, Maintenance,
Locations, Reports (CSV export) and Activity Log.
"""

import csv
import io
import json
import os
import re
import time
from datetime import date, datetime, timedelta

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   jsonify, request, session, stream_with_context, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from backend import security
from backend.chatbot import ChatbotError, stream_faq
from backend.models import (
    CATEGORIES, CONDITIONS, MAINT_STATUSES, MAINT_TYPES, STATUSES,
    WARRANTY_FILTERS, borrow_state, civil_time, compute_stats, days_left,
    filter_equipment, fmt_date, fmt_ts, location_summary, maint_state,
    next_asset_tag, now_ph, parse_date, renumber_plan, status_class, today_ph,
    today_str, warranty_state,
)
from backend.store import get_store

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["TIMEZONE"] = config.TIMEZONE
app.config["SESSION_COOKIE_SECURE"] = config.SESSION_COOKIE_SECURE
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["TEMPLATES_AUTO_RELOAD"] = True
if config.TRUST_PROXY:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

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
        if endpoint == "chat_api":
            return jsonify(error="Sign in to use the FAQ assistant."), 401
        if request.method == "GET" and request.endpoint:
            session["next"] = request.full_path if request.query_string else request.path
        return redirect(url_for("login"))
    if request.method == "POST":
        token = session.get("csrf")
        submitted_token = (
            request.headers.get("X-CSRF-Token")
            if request.is_json else request.form.get("csrf_token")
        )
        if not token or submitted_token != token:
            abort(400, description="Invalid or missing CSRF token. Refresh the page and try again.")
    return None


@app.after_request
def _secure_response_headers(response):
    """Apply browser security headers and keep rendered HTML fresh."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"

    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def _qeti_record_intent(message, history):
    """Return which read-only record groups are relevant to a Qeti question."""
    recent_user_messages = [
        item["text"] for item in history[-6:]
        if item.get("role") == "user"
    ]
    text = " ".join([*recent_user_messages, message]).lower()
    words = set(re.findall(r"[a-z0-9-]+", text))
    equipment_terms = {
        "equipment", "device", "inventory", "asset", "serial", "assigned",
        "laptop", "desktop", "monitor", "printer", "phone", "tablet",
        "server", "warranty", "location", "stock", "available", "retired",
        "lost", "brand", "model", "own", "owns", "owner", "ownership",
    }
    borrowing_terms = {
        "borrow", "borrowed", "borrower", "borrowers", "loan", "loans",
        "overdue", "returned", "return", "due",
    }
    maintenance_terms = {
        "maintenance", "repair", "technician", "service", "inspection",
        "scheduled", "repairs",
    }
    activity_terms = {
        "activity", "activities", "audit", "log", "logs", "changed",
        "changes", "history",
    }
    intent_words = words | {
        word[:-1] for word in words if len(word) > 4 and word.endswith("s")
    }
    broad_records = any(term in words for term in ("record", "records"))
    wants_all = broad_records and any(term in words for term in ("all", "every"))
    include_equipment = bool(intent_words & equipment_terms) or broad_records or any(
        term in intent_words for term in ("count", "counts", "total")
    ) or "how many" in text or (
        "who" in intent_words
        and bool(intent_words & {
            "has", "have", "currently", "assigned", "own", "owns", "owner",
        })
    )
    include_borrowings = bool(intent_words & borrowing_terms) or wants_all
    include_maintenance = bool(intent_words & maintenance_terms) or wants_all
    include_activity = bool(intent_words & activity_terms) or wants_all
    return (
        include_equipment, include_borrowings, include_maintenance,
        include_activity,
    )


def _qeti_context_terms(message, history):
    stop_words = {
        "about", "all", "any", "are", "can", "could", "does", "do", "for",
        "from", "has", "have", "how", "is", "it", "list", "many", "me", "of",
        "our", "please", "show", "tell", "that", "the", "there", "this",
        "currently", "own", "owns", "owner", "ownership", "we", "what",
        "which", "who", "with", "you", "your", "equipment",
        "inventory", "device", "devices", "record", "records", "every",
        "status", "borrow", "borrowed", "borrower", "loan", "loans",
        "maintenance", "repair", "inspection", "scheduled",
    }
    parts = [message]
    parts.extend(
        item["text"] for item in history[-6:]
        if item.get("role") == "user"
    )
    terms = []
    for part in parts:
        for token in re.findall(r"[a-z0-9-]+", part.lower()):
            if len(token) > 2 and token not in stop_words and token not in terms:
                terms.append(token)
    return terms[:15]


def _qeti_record_subset(rows, fields, terms, limit=20):
    records = [{field: row.get(field) for field in fields} for row in rows]
    if terms:
        matches = []
        for row in records:
            searchable = " ".join(str(value or "") for value in row.values()).lower()
            score = sum(
                token in searchable or (
                    token.endswith("s") and token[:-1] in searchable
                )
                for token in terms
            )
            if score:
                matches.append((score, row))
        matches.sort(key=lambda item: item[0], reverse=True)
        records = [row for _score, row in matches]
    return {
        "total_records": len(rows),
        "matched_records": len(records),
        "records": records[:limit],
        "truncated": len(records) > limit,
    }


def _qeti_record_context(message, history):
    """Build a bounded, read-only record context; never include auth/secrets."""
    (
        include_equipment, include_borrowings, include_maintenance,
        include_activity,
    ) = _qeti_record_intent(message, history)
    if not (
        include_equipment or include_borrowings or include_maintenance
        or include_activity
    ):
        return None
    terms = _qeti_context_terms(message, history)
    context = {"as_of": today_str()}

    if include_equipment:
        rows = store.all_equipment()
        by_status = {}
        by_category = {}
        by_category_and_status = {}
        warranty_counts = {}
        for row in rows:
            status = row.get("status") or "In Stock"
            category = (row.get("category") or "Other").strip() or "Other"
            by_status[status] = by_status.get(status, 0) + 1
            by_category[category] = by_category.get(category, 0) + 1
            category_status = by_category_and_status.setdefault(category, {})
            category_status[status] = category_status.get(status, 0) + 1
            warranty_label = warranty_state(row.get("warranty_expiry"))[0]
            warranty_counts[warranty_label] = warranty_counts.get(warranty_label, 0) + 1
        context["equipment_summary"] = {
            "total": len(rows),
            "by_status": by_status,
            "by_category": by_category,
            "by_category_and_status": by_category_and_status,
            "warranty": warranty_counts,
        }
        context["equipment"] = _qeti_record_subset(
            [
                dict(row, warranty_state=warranty_state(row.get("warranty_expiry"))[0])
                for row in rows
            ],
            (
                "asset_tag", "model", "brand", "category", "serial_no",
                "assigned_to", "location", "status", "condition",
                "purchase_date", "warranty_expiry", "warranty_state",
            ),
            terms,
        )
        context["equipment_locations"] = location_summary(rows)

    if include_borrowings:
        rows = []
        for row in store.all_borrowings():
            state = borrow_state(row)[0]
            loan_state = (
                "OVERDUE" if state == "OVERDUE"
                else "RETURNED" if state == "RETURNED"
                else "ACTIVE"
            )
            rows.append(dict(row, loan_state=loan_state))
        context["borrowings"] = _qeti_record_subset(
            rows,
            (
                "asset_tag", "model", "brand", "borrower", "department",
                "borrowed_date", "due_date", "returned_date", "status",
                "loan_state",
            ),
            terms,
        )

    if include_maintenance:
        rows = [
            dict(row, maintenance_state=maint_state(row)[0])
            for row in store.all_maintenance()
        ]
        context["maintenance"] = _qeti_record_subset(
            rows,
            (
                "asset_tag", "model", "brand", "mtype", "scheduled_date",
                "completed_date", "status", "maintenance_state", "technician",
                "cost",
            ),
            terms,
        )

    if include_activity:
        rows = store.recent_activity(500)
        context["activity_log"] = _qeti_record_subset(
            rows,
            ("action", "entity", "detail", "username", "created_at"),
            terms,
        )

    return json.dumps(context, ensure_ascii=True, default=str)


@app.context_processor
def _inject_globals():
    return {
        "csrf_token": session.get("csrf", ""),
        "chatbot_enabled": bool(config.GEMINI_API_KEY),
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


@app.route("/api/chat", methods=["POST"])
def chat_api():
    user = session.get("user") or {}
    if str(user.get("role") or "").strip().lower() != "admin":
        return jsonify(error="Qeti record access is available to administrators only."), 403
    if request.content_length and request.content_length > 16 * 1024:
        return jsonify(error="Chat requests must be 16 KB or smaller."), 413
    if not request.is_json:
        return jsonify(error="Send a JSON message."), 400
    payload = request.get_json()
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, str) or not message.strip():
        return jsonify(error="Enter a question for the FAQ assistant."), 400
    message = message.strip()
    if len(message) > 1000:
        return jsonify(error="Questions must be 1,000 characters or fewer."), 413
    history = payload.get("history", [])
    if not isinstance(history, list) or len(history) > 20:
        return jsonify(error="Chat history must contain 20 messages or fewer."), 400
    normalized_history = []
    history_size = 0
    for item in history:
        if not isinstance(item, dict):
            return jsonify(error="Chat history contains an invalid message."), 400
        role = item.get("role")
        text = item.get("text")
        if role not in ("user", "assistant") or not isinstance(text, str) or not text.strip():
            return jsonify(error="Chat history contains an invalid message."), 400
        text = text.strip()
        if len(text) > 1000:
            return jsonify(error="Chat history messages must be 1,000 characters or fewer."), 413
        history_size += len(text)
        normalized_history.append({"role": role, "text": text})
    if history_size > 12000:
        return jsonify(error="Chat history is too long. Start a new conversation."), 413
    if not normalized_history or normalized_history[-1] != {
        "role": "user",
        "text": message,
    }:
        normalized_history.append({"role": "user", "text": message})
    if not config.GEMINI_API_KEY:
        return jsonify(error="The FAQ assistant is not configured yet."), 503

    now = time.time()
    recent = [
        stamp for stamp in session.get("chat_requests", [])
        if isinstance(stamp, (int, float)) and now - stamp < 60
    ]
    if len(recent) >= 10:
        return jsonify(error="Please wait a minute before asking more questions."), 429
    recent.append(now)
    session["chat_requests"] = recent

    try:
        record_context = _qeti_record_context(message, normalized_history)
    except Exception:
        app.logger.exception("Qeti could not retrieve read-only record context")
        return jsonify(error="Qeti could not read system records. Please try again."), 503

    @stream_with_context
    def generate_reply():
        try:
            for text in stream_faq(
                message,
                config.GEMINI_API_KEY,
                config.GEMINI_MODEL,
                normalized_history,
                record_context,
            ):
                yield json.dumps({"text": text}) + "\n"
            yield json.dumps({"done": True}) + "\n"
        except ChatbotError as exc:
            app.logger.warning("FAQ assistant request failed: %s", exc)
            yield json.dumps({
                "error": "Qeti could not finish the reply. Please try again."
            }) + "\n"

    return Response(
        generate_reply(),
        mimetype="application/x-ndjson",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


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
        subtitle="A quick overview of key activity and statistics across the system",
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
                             "Manage equipment records, and status")


@app.route("/warranty", methods=["GET", "POST"])
def warranty():
    return _render_equipment("warranty", "warranty", "Warranty Tracking",
                             "Monitor warranty coverage and expiration dates for all devices")


# ------------------------------------------------------------- borrow/return
def _revert_after_loan(equipment_id):
    row = store.get_equipment(equipment_id)
    # Resting status is ALWAYS "In Stock" (user's final choice, 2026-10-18),
    # even when assigned_to is set (their example: Macbook Neo, assigned to
    # "Admin Pool", must still come back In Stock). Don't reintroduce
    # Assigned/Available branching here.
    if row and (row.get("status") or "") == "Borrowed":
        store.update_equipment(equipment_id, {"status": "In Stock"})


def _revert_after_maintenance(equipment_id):
    row = store.get_equipment(equipment_id)
    if row and (row.get("status") or "") == "Under Maintenance":
        store.update_equipment(equipment_id, {"status": "In Stock"})


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
            # "Available" (added with the Lost status) is a ready-to-lend state.
            if (equipment.get("status") or "") not in ("In Stock", "Assigned", "Available"):
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
                 if (e.get("status") or "") in ("In Stock", "Assigned", "Available")
                 and str(e.get("id")) not in lent_out]
    # Newest first: IT-0019, IT-0018, ... so a just-added device sits at the top.
    available.sort(key=_newest_first)

    return render_template(
        "borrow.html", page="borrow", title="Borrow & Return",
        subtitle="Issue devices to staff and track what is still out on loan",
        rows=rows, available=available, f_status=status_filter, q=q,
        default_due=(today_ph() + timedelta(days=7)).isoformat(),
    )


# -------------------------------------------------------------- maintenance
def _equipment_in_maintenance(equipment_id):
    row = store.get_equipment(equipment_id)
    # "Available" is a ready state like In Stock/Assigned — it must flip too
    # (Borrowed/Lost/Retired correctly stay untouched).
    if row and (row.get("status") or "") in ("In Stock", "Assigned", "Available"):
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
            if scheduled_day and scheduled_day <= today_ph():
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
        subtitle="Plan preventive servicing and track corrective repairs from start to finish",
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
        subtitle="See where every device is currently located and assigned", groups=groups, by_location=by_location,
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


def _report_context() -> dict:
    """Everything the reports page (and the PDF) needs, fetched once."""
    equipment = store.all_equipment()
    maintenance = store.all_maintenance()
    borrowings = store.all_borrowings()
    warranty_rows = sorted(
        [r for r in equipment if r.get("warranty_expiry")],
        key=lambda r: (r.get("warranty_expiry") or ""),
    )
    now = now_ph()
    user = session.get("user") or {}
    generated_by = (
        user.get("full_name") or user.get("username") or "-"
    ).strip()
    # The report head reads "Prepared by Admin" - the user asked for the short
    # label instead of the long seeded display name ("System Administrator").
    # Only the report/PDF use this; the topbar keeps showing the full name.
    if generated_by.lower() == "system administrator":
        generated_by = "Admin"
    return {
        "stats": compute_stats(equipment, maintenance, borrowings),
        "equipment": equipment,
        "borrowings": borrowings,
        "maintenance": maintenance,
        "warranty_rows": warranty_rows,
        "locations": location_summary(equipment),
        "generated_at": f"{now:%b %d, %Y} {civil_time(now)} PHT",
        "generated_by": generated_by,
    }


@app.route("/reports")
def reports():
    """The report page - "Print Report" previews the whole report in place
    (see the .preview-mode rules in style.css / app.js); nothing navigates."""
    return render_template(
        "reports.html", page="reports", title="Reports",
        subtitle="Summaries and exports",
        **_report_context(),
    )


@app.route("/report.pdf")
def report_pdf():
    """Generate the inventory report as a downloadable PDF file.

    `?paper=` picks the sheet the story is laid out for (see PAPER_SIZES in
    backend/report_pdf.py) and `?orientation=portrait|landscape` which way round
    it is printed (see ORIENTATIONS); the "Save as PDF" button asks for both
    before it opens the save destination dialog. Anything unknown falls back to
    landscape A4.
    """
    from backend.report_pdf import (DEFAULT_ORIENTATION, DEFAULT_PAPER,
                                    ORIENTATIONS, PAPER_SIZES,
                                    build_report_pdf)

    paper = (request.args.get("paper") or DEFAULT_PAPER).strip().lower()
    if paper not in PAPER_SIZES:
        paper = DEFAULT_PAPER
    orientation = (request.args.get("orientation") or DEFAULT_ORIENTATION)
    orientation = orientation.strip().lower()
    if orientation not in ORIENTATIONS:
        orientation = DEFAULT_ORIENTATION

    context = _report_context()
    payload = build_report_pdf(
        context["stats"],
        context["equipment"],
        context["warranty_rows"],
        context["locations"],
        generated_by=context["generated_by"],
        generated_at=context["generated_at"],
        paper=paper,
        orientation=orientation,
    )
    filename = "inventory-report-%s.pdf" % now_ph().strftime("%Y%m%d")
    return Response(payload, mimetype="application/pdf", headers={
        "Content-Disposition": "attachment; filename=%s" % filename,
        "Cache-Control": "no-store",
    })


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
        subtitle="Full history of changes and actions performed in the system",
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
