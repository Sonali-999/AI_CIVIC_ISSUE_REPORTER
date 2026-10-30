import os
import sys
import gradio as gr
from dotenv import load_dotenv
import shutil
import tempfile
from datetime import datetime

# Windows terminals default to the cp1252 codepage, which cannot encode the
# emoji this app prints - most consequentially the admin OTP banner. Without
# this, clicking "Get OTP" raises UnicodeEncodeError and the login is
# unusable in a normal terminal. errors="replace" keeps a stray glyph from
# ever taking down a request.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from .auth import register_user_wrapper, login_user_wrapper
from .db_utils import (
    save_complaint, get_complaints_by_department, get_all_complaints,
    update_complaint_status, get_notifications, get_unread_count,
    mark_all_notifications_read, STATUS_LABELS,get_user_complaint_stats,get_complaints_by_user, get_all_departments
)
from .admin_signature import (
    generate_admin_keypair,
    create_login_challenge,
    sign_challenge,
    verify_admin_signature,
)
from .ai_service import (
    analyze_complaint, ModelNotTrainedError,
    is_available as model_is_available, warm_up as warm_up_model,
)
from .geo_service import resolve_location, map_link
from .image_encryption import encrypt_image, decrypt_image
from .security_audit import log_security_event, verify_chain
from .jwt_tokens import create_token, verify_token, token_required
# ---------------- Load environment ----------------
load_dotenv()

import hashlib

# Whitelist of emails allowed to register as admin
ALLOWED_ADMIN_EMAILS = {
    "admin@gmail.com",
    "munic@gov.in",
    
}

# In-memory OTP store: {email: otp_string}  — cleared after each use
admin_otp_store = {}

# ---------------- Issue analysis ----------------
# There is no system prompt any more. Complaint categorisation is done by the
# locally trained CNN in ai_service.analyze_complaint(), which returns the same
# Title / Category / Department / Description fields the LLM used to produce.

# ---------------- Look & feel ----------------
# The stylesheet and Gradio theme live in app/theme.py: several hundred lines of
# CSS inlined here buried the application logic, and the visual layer changes on
# a completely different schedule from the routing and crypto code.
from .theme import APP_THEME, CUSTOM_CSS

custom_css = CUSTOM_CSS


# ════════════════════════════════════════════════════════════════════════════
# HEADER HELPER
# ════════════════════════════════════════════════════════════════════════════

def _make_header(email: str = "", role: str = "") -> str:
    """
    The application top bar.

    Signed out it carries the brand and a live status chip; signed in it also
    carries the account pill, so who you are logged in as is answerable at a
    glance from any tab rather than only on the auth screen.
    """
    right = '<div class="hdr-chip"><span class="dot"></span>On-device AI</div>'

    if email:
        local = email.split("@")[0]
        parts = [p for p in local.replace("_", ".").split(".") if p]
        initials = "".join(p[0].upper() for p in parts[:2]) or local[:1].upper() or "U"
        role_label = {"citizen": "Citizen", "admin": "Administrator"}.get(role, role.title())
        right += f"""
        <div class="hdr-user">
            <div class="hdr-avatar">{initials}</div>
            <div class="hdr-user-meta">
                <span class="hdr-user-mail">{email}</span>
                <span class="hdr-user-role">{role_label}</span>
            </div>
        </div>"""

    return f"""
    <div id="civicai-header">
        <div id="civicai-header-inner">
            <div class="hdr-logo">
                <div class="hdr-logo-icon">🏛️</div>
                <div>
                    <div class="hdr-logo-name">CivicAI</div>
                    <div class="hdr-logo-sub">Smart Civic Issue Detection</div>
                </div>
            </div>
            <div class="hdr-right">{right}</div>
        </div>
    </div>"""


# ════════════════════════════════════════════════════════════════════════════
# AUTH HELPERS — role selector HTML builders
# ════════════════════════════════════════════════════════════════════════════

def _role_selector_html(selected: str = "citizen") -> str:
    """
    Renders the two role cards with the active one highlighted.

    Purely an indicator - the real selection happens through the Gradio buttons
    above it, which is what actually flips the sub-form. These cards exist so
    the choice stays visible after the click.
    """
    citizen_cls = "role-btn active-citizen" if selected == "citizen" else "role-btn"
    admin_cls   = "role-btn active-admin"   if selected == "admin"   else "role-btn"
    return f"""
    <div class="role-selector">
        <div class="{citizen_cls}">
            <span class="role-icon">👤</span>
            <span>Citizen</span>
        </div>
        <div class="{admin_cls}">
            <span class="role-icon">🛡️</span>
            <span>Admin</span>
        </div>
    </div>"""


# ════════════════════════════════════════════════════════════════════════════
# AUTH FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

def select_citizen_role():
    """Show citizen sub-form, hide admin sub-form."""
    return (
        "citizen",
        _role_selector_html("citizen"),
        gr.update(visible=True),   # citizen_login_panel
        gr.update(visible=False),  # admin_login_panel
    )

def select_admin_role():
    """Show admin sub-form, hide citizen sub-form."""
    return (
        "admin",
        _role_selector_html("admin"),
        gr.update(visible=False),  # citizen_login_panel
        gr.update(visible=True),   # admin_login_panel
    )

def request_admin_otp(email, password):
    """Validate admin credentials then print OTP to terminal."""
    if not email or not password:
        return '<div class="status-error">❌ Please enter your email and password first.</div>'
    result = login_user_wrapper(email, password)
    if result.get("status") != "success":
        return '<div class="status-error">❌ Invalid credentials.</div>'
    if result.get("role") != "admin":
        return '<div class="status-error">❌ This account is not an admin account.</div>'
    generate_admin_otp(email)
    return '<div class="status-error">🔐 OTP sent to terminal. Enter it above and click Sign In.</div>'


def signup(email, password, role, state):
    """Register with the chosen role."""
    if not email or not password:
        return (
            '<div class="status-error">❌ Please fill in all fields.</div>',
            state,
            gr.update(visible=True),   # signup form stays visible
            gr.update(visible=False),
        )

    # ── Block unauthorized admin registration ──
    if role == "admin" and email.strip().lower() not in ALLOWED_ADMIN_EMAILS:
        return (
            '<div class="status-error">❌ This email is not authorized for admin registration.</div>',
            state,
            gr.update(visible=True),
            gr.update(visible=False),
        )
    # ───────────────────────────────────────────
    result = register_user_wrapper(email, password, role)
    if "success" in result.get("status", "").lower():
        return (
            f'<div class="status-success">✨ {result["status"]} — Now please sign in!</div>',
            state,
            gr.update(visible=False),   # hide signup
            gr.update(visible=True),    # show login
        )
    else:
        return (
            f'<div class="status-error">❌ {result.get("status","Error")}</div>',
            state,
            gr.update(visible=True),
            gr.update(visible=False),
        )


def login(email, password, role, state, admin_otp=""):
    """Login and route to the correct dashboard."""
    result = login_user_wrapper(email, password)

    # ── Admin OTP verification ──────────────────
    if result.get("status") == "success" and result.get("role") == "admin":
        expected_otp = admin_otp_store.get(email)
        if not expected_otp:
            return (
                '<div class="status-error">❌ Please click <b>Get OTP</b> first, then enter the code.</div>',
                state, _make_header(), gr.update(visible=True),
                gr.update(visible=False), gr.update(visible=False),
                gr.update(), [], "", "", "", gr.update(),
            )
        if admin_otp.strip() != expected_otp:
            del admin_otp_store[email]
            return (
                '<div class="status-error">❌ Invalid OTP. Click <b>Get OTP</b> again to request a new one.</div>',
                state, _make_header(), gr.update(visible=True),
                gr.update(visible=False), gr.update(visible=False),
                gr.update(), [], "", "", "", gr.update(),
            )
        del admin_otp_store[email]   # one-time use
        print(f"[✅] Admin {email} passed OTP verification.")
    # ────────────────────────────────────────────

    if result.get("status") == "success":
        actual_role = result.get("role", role)  # trust DB role
        log_security_event(
            "LOGIN_SUCCESS",
            f"user={email}, role={actual_role}"
        )
        state["uid"]   = result["user_id"]
        state["email"] = email
        state["role"]  = actual_role

        token = create_token(result['user_id'], email, actual_role)
        state['token'] = token     # store signed JWT in session state

        is_citizen = (actual_role == "citizen")
        is_admin   = (actual_role == "admin")

        stats_html = generate_user_stats(state) if is_citizen else ""
        history_html = generate_user_complaints_html(state) if is_citizen else ""

        # Pre-load admin data on login if admin, else return empty defaults
        if is_admin:
            admin_html, admin_images, admin_picker = get_admin_complaints_html(state)
        else:
            admin_html = empty_state(
                "🗃️", "Queue not loaded",
                "Press Refresh to pull the current complaints from the database.")
            admin_images, admin_picker = [], gr.update(choices=[])

        # Build notification bell for citizen
        bell_html = build_notification_bell_html(state["uid"]) if is_citizen else ""

        return (
            f'<div class="status-success">✅ Welcome back, {email}!</div>',
            state,
            _make_header(email, actual_role),
            gr.update(visible=False),   # hide auth content
            gr.update(visible=is_citizen),
            gr.update(visible=is_admin),
            admin_html,
            admin_images,
            stats_html,
            history_html,
            bell_html,
            admin_picker,
        )
    else:
        log_security_event(
            "LOGIN_FAILED",
            f"user={email}"
        )
        state["uid"] = state["email"] = state["role"] = None
        return (
            '<div class="status-error">❌ Invalid credentials. Please try again.</div>',
            state,
            _make_header(),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(),  # no change to admin_container
            [],           # empty gallery
            "",           # no stats
            "",           # no history
            "",           # empty bell
            gr.update(),  # no change to complaint picker
        )


def signout(state):
    state["uid"] = state["email"] = state["role"] = state['token'] = None
    return (
        '<div class="status-success">✅ Successfully signed out!</div>',
        state,
        _make_header(),
        gr.update(visible=True),    # show auth content
        gr.update(visible=False),   # hide citizen
        gr.update(visible=False),   # hide admin
    )


def show_signup():
    return gr.update(visible=False), gr.update(visible=True)

def show_login():
    return gr.update(visible=True), gr.update(visible=False)

def generate_admin_otp(email: str) -> str:
    """Sign a challenge with the admin's private key, derive a 6-digit OTP from it."""
    challenge = create_login_challenge(email)
    safe      = email.replace("@", "_at_").replace(".", "_")
    priv_path = f"keys/admin_{safe}_private.pem"
    try:
        signature = sign_challenge(challenge, priv_path)
        otp = str(int(hashlib.sha256(signature.encode()).hexdigest(), 16))[-6:]
        admin_otp_store[email] = otp
        print(f"\n{'='*40}")
        print(f"  🔐 ADMIN OTP FOR {email}")
        print(f"  Code: {otp}")
        print(f"{'='*40}\n")
        return otp
    except FileNotFoundError:
        print(f"[WARN] No private key found for {email}")
        return None

# ════════════════════════════════════════════════════════════════════════════
# AI COMPLAINT PROCESSING
# ════════════════════════════════════════════════════════════════════════════

DEPT_ICONS = {
    "Sanitation": "🗑️", "Roads": "🛣️", "Electricity": "⚡", "Water": "💧",
    "Parks & Horticulture": "🌳", "Public Works": "🏗️", "Traffic": "🚦",
    "General Administration": "🏛️",
}


def _location_line(location: dict) -> str:
    """One-line human summary of where a complaint was reported."""
    if not location:
        return "Location not provided"
    address = location.get("address") or "Location not provided"
    source = location.get("source")
    if source == "gps":
        return f"📍 {address}"
    if source == "manual":
        return f"✏️ {address} — typed by citizen, not GPS-verified"
    return address


def format_citizen_ai_output(title, category, department, description,
                             location=None, confidence=None, low_confidence=False):
    """The receipt a citizen sees the moment their complaint is registered."""
    icon = DEPT_ICONS.get(department, "🏢")
    pretty_category = str(category).replace("_", " ").title()

    return f"""
    <div class="complaint-card">
        <div class="complaint-card-header">
            <span>⚡</span>
            <span>AI Analysis Complete — Complaint Registered</span>
        </div>
        <div class="complaint-card-body">
            <div class="info-badge">
                <div class="info-badge-label">Issue Title</div>
                <div class="info-badge-value" style="font-size:15.5px;">{title}</div>
            </div>
            <div class="info-grid">
                <div class="info-badge" style="margin-bottom:0;">
                    <div class="info-badge-label">Category</div>
                    <div class="info-badge-value">🏷️ {pretty_category}</div>
                </div>
                <div class="info-badge" style="margin-bottom:0;">
                    <div class="info-badge-label">Routed To</div>
                    <div class="info-badge-value">{icon} {department}</div>
                </div>
            </div>
            <div class="info-badge" style="margin-top:12px;">
                <div class="info-badge-label">Location</div>
                <div style="font-size:13px;color:var(--text-2);line-height:1.6;margin-top:4px;">
                    {_location_line(location)}
                </div>
            </div>
            <div class="info-badge">
                <div class="info-badge-label">Description</div>
                <div style="font-size:13.5px;color:var(--muted);line-height:1.7;margin-top:4px;">{description}</div>
            </div>
            {_confidence_badge(confidence, low_confidence)}
            <div class="status-success" style="justify-content:center;">
                <span>✅</span>
                <span>Complaint submitted — the {department} desk has it now.</span>
            </div>
        </div>
    </div>"""


def _confidence_badge(confidence, low_confidence: bool) -> str:
    """
    Render the model's confidence as a meter.

    Shown to the citizen deliberately: when the classifier is unsure, the person
    who actually saw the issue is told so and can correct the record, rather
    than a wrong department being assigned invisibly.
    """
    if confidence is None:
        return ""

    pct = confidence * 100
    if low_confidence:
        colour, note = "#F04438", "Low confidence — an officer will confirm the category."
    elif pct < 75:
        colour, note = "#F79009", "Moderate confidence — the category may be reviewed."
    else:
        colour, note = "#12B76A", "High confidence — classified on this device, no data left it."

    return f"""
            <div class="info-badge">
                <div class="info-badge-label">Model Confidence</div>
                <div style="display:flex;align-items:center;gap:12px;margin-top:8px;">
                    <div class="conf-track">
                        <div class="conf-fill" style="width:{pct:.0f}%;background:{colour};"></div>
                    </div>
                    <span style="font-size:13.5px;font-weight:700;color:{colour};
                          font-variant-numeric:tabular-nums;">{pct:.0f}%</span>
                </div>
                <div style="font-size:11.5px;color:var(--muted);margin-top:6px;">{note}</div>
            </div>"""


def process_complaint(image_path, user_msg, gps_lat, gps_lon, manual_address, state):
    """
    Full citizen submission pipeline.

        JWT check -> classify -> resolve location -> encrypt image
                  -> scrub plaintext -> persist with CivicHash-512
    """
    def fail(message):
        return f'<div class="status-error">❌ {message}</div>', None, "", ""

    # The JWT is the authority on who is submitting, not the session dict:
    # state can be manipulated client-side, a signed token cannot.
    try:
        payload = token_required(state.get('token'), required_role='citizen')
    except ValueError as e:
        return fail(str(e))

    uid = payload['sub']

    if not image_path:
        return fail("Please upload an image of the issue.")

    try:
        # ── 1. Where is it? Resolved first so the address can be folded into
        #       the generated title and description.
        location = resolve_location(gps_lat, gps_lon, manual_address)

        # ── 2. What is it? Local CNN, no API call.
        try:
            result = analyze_complaint(
                image_path,
                user_note=user_msg,
                location=location.get("address") if location.get("verified") else manual_address,
            )
        except ModelNotTrainedError as e:
            return fail(
                "The issue classifier has not been trained yet.<br>"
                f"<span style='font-size:12px;font-weight:400;'>{e}</span>"
            )

        # ── 3. Persist the photograph encrypted, then scrub the plaintext.
        os.makedirs("uploads", exist_ok=True)
        # Timestamp prefix: two citizens uploading "photo.jpg" must not
        # overwrite each other's evidence.
        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        filename = f"{stamp}_{os.path.basename(image_path)}"
        saved_path = os.path.join("uploads", filename)
        shutil.copy2(image_path, saved_path)

        enc_path = encrypt_image(saved_path)
        os.remove(saved_path)          # plaintext scrubbing

        # ── 4. Store, bound to its CivicHash-512 integrity digest.
        save_complaint(
            uid,
            result["title"], result["category"], result["department"],
            result["description"], enc_path,
            location=location,
            ai_meta={
                "raw_category": result["raw_category"],
                "confidence": result["confidence"],
                "low_confidence": result["low_confidence"],
                "top_k": result["top_k"],
                "source": "local_cnn",
            },
        )

        html_content = format_citizen_ai_output(
            result["title"], result["category"], result["department"],
            result["description"], location=location,
            confidence=result["confidence"], low_confidence=result["low_confidence"],
        )
        return (
            html_content,
            image_path,
            generate_user_stats(state),
            generate_user_complaints_html(state),
        )

    except Exception as e:
        log_security_event("COMPLAINT_FAILED", f"user={uid}, error={e}")
        return fail(f"Error processing complaint: {e}")


# ════════════════════════════════════════════════════════════════════════════
# LOCATION CAPTURE
# ════════════════════════════════════════════════════════════════════════════

# Runs in the citizen's browser. Gradio awaits the returned promise and feeds
# the resolved array into the hidden latitude/longitude textboxes.
GEOLOCATION_JS = """
async () => {
    if (!navigator.geolocation) {
        return ["", "", "unsupported"];
    }
    try {
        const position = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 0
            });
        });
        return [
            String(position.coords.latitude),
            String(position.coords.longitude),
            "ok"
        ];
    } catch (err) {
        // 1 = permission denied, 2 = position unavailable, 3 = timeout
        const reason = err && err.code === 1 ? "denied"
                     : err && err.code === 3 ? "timeout"
                     : "unavailable";
        return ["", "", reason];
    }
}
"""

_GPS_MESSAGES = {
    "denied":      "Location permission denied — type your address below instead.",
    "timeout":     "Location request timed out — try again or type your address.",
    "unavailable": "Could not determine your position — type your address below.",
    "unsupported": "This browser does not support location — type your address.",
}


def describe_location(gps_lat, gps_lon, manual_address, gps_status):
    """Resolve captured coordinates to an address and render it for the citizen."""
    def readout(tone: str, icon: str, headline: str, detail: str = "") -> str:
        """A single card shape for all four location outcomes."""
        body = (f'<div style="font-size:12px;opacity:0.85;margin-top:4px;'
                f'line-height:1.5;">{detail}</div>' if detail else "")
        return (f'<div class="info-badge" style="border-color:var(--{tone});'
                f'background:var(--{tone}-bg);margin:6px 0 0;">'
                f'<div style="font-size:12.5px;font-weight:700;">{icon} {headline}</div>'
                f'{body}</div>')

    if gps_status and gps_status != "ok":
        message = _GPS_MESSAGES.get(
            gps_status, "Location unavailable — type your address below."
        )
        return readout("danger", "⚠️", "GPS unavailable", message)

    if not gps_lat and not (manual_address or "").strip():
        return ('<div class="pill pill-muted" style="margin-top:6px;">'
                '📍 No location captured yet</div>')

    location = resolve_location(gps_lat, gps_lon, manual_address)

    if location.get("verified"):
        district = location.get("district") or location.get("city") or ""
        detail = location["address"]
        if district:
            detail += f'<br>Ward / district: {district}'
        detail += (f'<br><span class="mono" style="font-size:11px;">'
                   f'{location["latitude"]:.5f}, {location["longitude"]:.5f}</span>')
        return readout("ok", "📍", "GPS location confirmed", detail)

    return readout("warn", "✏️",
                   f'Using typed address: {location.get("address", "")}',
                   "Not GPS-verified — an officer may need to confirm it on site.")

# Each KPI tile carries an accent rail and a matching icon wash. The four
# values are counts of the same thing in different states, so they share one
# tile design and differ only by hue - which is what makes them scannable as a
# row rather than four unrelated boxes.
_STAT_TILES = [
    ("total",       "Total Reported", "📋", "#1B4F8F", "reports you filed"),
    ("resolved",    "Resolved",       "✅",     "#12B76A", "closed by the department"),
    ("in_progress", "In Progress",    "⚡",     "#F79009", "being worked on"),
    ("pending",     "Pending",        "⏳",     "#F04438", "awaiting triage"),
]


def _stat_tile(label: str, value, icon: str, colour: str, foot: str) -> str:
    return f"""
        <div class="stat-card" style="--accent:{colour};--accent-bg:{colour}1a;">
            <div class="stat-head">
                <div class="stat-lbl">{label}</div>
                <div class="stat-ico" style="color:{colour};">{icon}</div>
            </div>
            <div class="stat-val">{value}</div>
            <div class="stat-foot">{foot}</div>
        </div>"""


def generate_user_stats(state):
    if not state.get("uid"):
        return ""

    stats = get_user_complaint_stats(state["uid"])
    tiles = "".join(
        _stat_tile(label, stats.get(key, 0), icon, colour, foot)
        for key, label, icon, colour, foot in _STAT_TILES
    )
    return f'<div class="stat-strip">{tiles}</div>'


# status -> (pill class, dot colour, label). One table, so a status renders
# identically wherever it appears - citizen history, admin queue, notification.
STATUS_STYLE = {
    "resolved":    ("pill-ok",     "#12B76A", "Resolved"),
    "in_progress": ("pill-warn",   "#F79009", "In Progress"),
    "pending":     ("pill-danger", "#F04438", "Pending"),
}


def _status_pill(status: str) -> str:
    cls, _, label = STATUS_STYLE.get(status, ("pill-muted", "#667085",
                                              str(status).replace("_", " ").title()))
    return f'<span class="pill {cls}"><span class="dot"></span>{label}</span>'


def _status_colour(status: str) -> str:
    return STATUS_STYLE.get(status, ("", "#667085", ""))[1]


def empty_state(icon: str, title: str, body: str) -> str:
    """A placeholder that says what belongs here and how it gets here."""
    return f"""
    <div class="empty-state">
        <div class="empty-ico">{icon}</div>
        <div class="empty-title">{title}</div>
        <div class="empty-body">{body}</div>
    </div>"""


def generate_user_complaints_html(state):
    if not state.get("uid"):
        return ""

    complaints = get_complaints_by_user(state["uid"])

    if not complaints:
        return empty_state(
            "📬", "No complaints yet",
            "Upload a photo of a civic issue and submit it — your reports "
            "and their status will be listed here.")

    cards = ""
    for c in complaints:
        status = c.get("status", "pending")
        cards += f"""
        <div class="admin-card" style="--status:{_status_colour(status)};">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
                <div class="info-badge-value">{c.get("title")}</div>
                {_status_pill(status)}
            </div>
            <div style="font-size:13px;color:var(--muted);margin-top:6px;line-height:1.6;">
                {c.get("description")}
            </div>
            <div style="font-size:12px;color:var(--faint);margin-top:8px;">
                {_location_line(c.get("location"))}
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;">
                <span class="pill pill-info">🏢 {c.get("department")}</span>
                <span class="pill pill-muted">🏷️ {c.get("category")}</span>
            </div>
        </div>"""

    return cards


# ════════════════════════════════════════════════════════════════════════════
# NOTIFICATION HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _time_ago(dt) -> str:
    """Return a human-readable relative time string."""
    if not dt:
        return ""
    try:
        diff = datetime.utcnow() - dt
        s = int(diff.total_seconds())
        if s < 60:       return "just now"
        if s < 3600:     return f"{s//60}m ago"
        if s < 86400:    return f"{s//3600}h ago"
        return f"{s//86400}d ago"
    except Exception:
        return ""


def build_notification_bell_html(user_id: str) -> str:
    """Render the bell with its unread badge for the citizen header area."""
    count = get_unread_count(user_id) if user_id else 0
    badge = f'<span class="badge-pill">{count}</span>' if count > 0 else ""
    label = f"{count} unread" if count else "No new updates"
    return f"""
    <div class="notif-bell-wrap">
        <span style="font-size:12px;color:var(--muted);">{label}</span>
        <span style="font-size:19px;" title="Notifications">\U0001F514</span>
        {badge}
    </div>"""


def build_notifications_panel_html(user_id: str) -> str:
    """Render the full notifications dropdown panel."""
    if not user_id:
        return ""

    notifs = get_notifications(user_id)
    unread = sum(1 for n in notifs if not n.get("read"))
    mark_all_notifications_read(user_id)   # mark as read once opened

    if not notifs:
        return """
        <div class="notif-panel">
            <div class="notif-panel-header">
                <span>\U0001F514 Notifications</span>
            </div>
            <div class="notif-empty">
                <b>Nothing yet.</b><br>
                <span style="font-size:12.5px;">You will be notified here whenever a
                department moves one of your complaints forward.</span>
            </div>
        </div>"""

    items_html = ""
    for n in notifs:
        new_status = n.get("new_status", "")
        old_lbl = STATUS_LABELS.get(n.get("old_status", ""), n.get("old_status", ""))
        new_lbl = STATUS_LABELS.get(new_status, new_status)
        unread_cls = "" if n.get("read") else " unread"
        # The dot colour is the status the complaint moved *to*, so a glance
        # down the list reads as a progress trail rather than a wall of text.
        colour = _status_colour(new_status)
        items_html += f"""
        <div class="notif-item{unread_cls}">
            <span class="dot" style="width:8px;height:8px;border-radius:50%;
                  background:{colour};margin-top:6px;flex:none;"></span>
            <div style="min-width:0;">
                <div class="notif-item-title">{n.get('title', 'Complaint update')}</div>
                <div class="notif-item-body">
                    Moved from <b>{old_lbl}</b> to <b>{new_lbl}</b>
                </div>
                <div class="notif-item-time">{_time_ago(n.get('created_at'))}</div>
            </div>
        </div>"""

    counter = f"{unread} new" if unread else f"{len(notifs)} total"
    return f"""
    <div class="notif-panel">
        <div class="notif-panel-header">
            <span>\U0001F514 Notifications</span>
            <span style="font-size:12px;font-weight:600;opacity:0.8;">{counter}</span>
        </div>
        {items_html}
    </div>"""


def handle_bell_click(state):
    """Called when citizen clicks the bell — returns the notification panel HTML and updated bell."""
    uid = state.get("uid") if state else None
    panel = build_notifications_panel_html(uid)
    bell  = build_notification_bell_html(uid)   # re-render with 0 badge now
    return panel, bell


def refresh_bell(state):
    """Refresh just the bell badge (called on tab load / periodic refresh)."""
    uid = state.get("uid") if state else None
    return build_notification_bell_html(uid)


def refresh_citizen_view(state):
    """
    Re-read this citizen's stats, complaint history and unread badge.

    Driven by a timer so an admin's status change appears on the citizen's
    screen on its own. Without this the citizen sees stale data until they log
    out and back in, which makes a working notification look broken.

    Returns gr.update() (i.e. "leave alone") for anyone who is not a logged-in
    citizen, so the timer never clobbers the admin's or a logged-out view.
    """
    if not state or state.get("role") != "citizen" or not state.get("uid"):
        return gr.update(), gr.update(), gr.update()

    return (
        generate_user_stats(state),
        generate_user_complaints_html(state),
        build_notification_bell_html(state["uid"]),
    )


# ════════════════════════════════════════════════════════════════════════════
# ADMIN STATUS UPDATE
# ════════════════════════════════════════════════════════════════════════════

def handle_status_update(complaint_id: str, new_status: str, state: dict):
    """Admin handler: update a complaint's status and return feedback HTML."""
    try:
        token_required(state.get('token'), required_role='admin')
    except ValueError as e:
        return f'<div class="status-error">❌ Access denied: {e}</div>'

    if state.get("role") != "admin":
        return '<div class="status-error">🚫 Admin access required.</div>'
    if not complaint_id:
        return ('<div class="status-error">❌ Select a complaint from the dropdown '
                'first — nothing is selected.</div>')
    if not new_status:
        return '<div class="status-error">❌ Please choose a status.</div>'

    result = update_complaint_status(str(complaint_id).strip(), new_status)
    outcome = result.get("status")

    if outcome == "success":
        label = STATUS_LABELS.get(new_status, new_status)
        return (f'<div class="status-success">✅ Complaint updated to {label} '
                f'— citizen notified.</div>')
    if outcome == "unchanged":
        # Not an error, but explicitly NOT a notification either.
        return (f'<div class="status-error">ℹ️ {result.get("message")}. '
                f'No notification was sent.</div>')
    return f'<div class="status-error">❌ {result.get("error", "Update failed.")}</div>'


# ════════════════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ════════════════════════════════════════════════════════════════════════════

_ADMIN_LIST_OPEN = '<div style="animation:rise 0.32s ease;">'


def _tamper_banner(tampered: bool) -> str:
    """
    Shown when a complaint's row no longer matches its CivicHash-512 chain.

    Deliberately loud and never collapsible: a mismatch means someone edited
    MongoDB directly, so the record in front of the officer cannot be trusted.
    """
    if not tampered:
        return ""
    return """
                <div class="status-error" style="margin-top:10px;">
                    <span>⚠️</span>
                    <span><b>Integrity check failed.</b> This complaint was modified
                    directly in the database, bypassing the audit chain.</span>
                </div>"""


def get_admin_complaints_html(state):
    """
    Render every complaint for the admin dashboard.

    Returns (html, gallery_image_paths, complaint_picker_update) - the third
    value populates the status-update dropdown so an admin selects a complaint
    instead of copying an ObjectId by hand.
    """
    try:
        token_required(state.get('token'), required_role='admin')
    except ValueError as e:
        return f'<div class="status-error">❌ {e}</div>', [], gr.update(choices=[])

    if state.get("role") != "admin":
        return ('<div class="status-error">🚫 Admin access required.</div>',
                [], gr.update(choices=[]))

    # ── REPLACE hardcoded list with dynamic fetch from MongoDB ──────────
    departments = get_all_departments()
    
    # ────────────────────────────────────────────────────────────────────

    dept_icons = DEPT_ICONS

    html_content = _ADMIN_LIST_OPEN
    image_paths  = []
    picker_choices = []      # (label, complaint_id) pairs for the status dropdown

    for dept in departments:
        rows = get_complaints_by_department(dept)
        if not rows:
            continue

        html_content += f"""
        <div class="dept-header">
            <span>{dept_icons.get(dept, '🏢')}</span>
            <span>{dept.upper()}</span>
            <span class="pill pill-muted" style="margin-left:auto;">{len(rows)} logged</span>
        </div>"""

        for row in rows:
            row_id      = str(row.get("_id"))
            user_id     = row.get("user_id")
            title       = row.get("title", "Untitled")
            category    = row.get("category")
            department  = row.get("department")
            description = row.get("description")
            image_path  = row.get("image_path")
            timestamp   = row.get("created_at")
            status      = row.get("status", "pending")
            tampered    = row.get("tampered", False)
            location    = row.get("location") or {}
            ai_meta     = row.get("ai_meta") or {}

            # Label the picker with something an admin can actually recognise.
            picker_choices.append((
                f"[{status.replace('_', ' ').title()}] {title[:58]} · {row_id[-6:]}",
                row_id,
            ))
            status_color = _status_colour(status.lower())

            confidence = ai_meta.get("confidence")
            confidence_text = f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "—"

            lat, lon = location.get("latitude"), location.get("longitude")
            link = map_link(lat, lon)
            location_html = (
                f'<a href="{link}" target="_blank" rel="noopener" '
                f'style="color:var(--info);font-weight:600;text-decoration:none;">'
                f'{location.get("address", "")} ↗</a>'
                if link else _location_line(location)
            )

            #gallery only supports actual image files, so if it's encrypted we need to decrypt to a temp file first
            img_idx = 0   # default = no image, so the HTML tag won't show
            if image_path and os.path.exists(image_path):
                if image_path.endswith(".enc"):
                    try:
                        raw_bytes = decrypt_image(image_path)          # returns bytes
                        base      = image_path.replace(".enc", "")
                        suffix    = os.path.splitext(base)[1] or ".jpg"
                        tmp       = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                        tmp.write(raw_bytes)
                        tmp.close()
                        image_paths.append(tmp.name)                   # temp file path
                        img_idx = len(image_paths)                     # set AFTER appending
                    except Exception as e:
                        print(f"[gallery] Could not decrypt {image_path}: {e}")
                else:
                    image_paths.append(image_path)
                    img_idx = len(image_paths)

            evidence_text = f"Image #{img_idx}" if img_idx else "—"

            # Status badge + inline update hint
            html_content += f"""
            <div class="admin-card" id="card-{row_id}" style="--status:{status_color};">
                <div style="display:flex;justify-content:space-between;
                     align-items:flex-start;gap:12px;margin-bottom:10px;">
                    <div style="min-width:0;">
                        <div class="mono" style="font-size:10.5px;color:var(--faint);
                             font-weight:600;margin-bottom:5px;">#{row_id}</div>
                        <div style="font-size:15px;font-weight:700;color:var(--text);
                             letter-spacing:-0.2px;">{title}</div>
                        <div style="font-size:12px;color:var(--muted);margin-top:3px;">
                            {str(category).replace('_', ' ').title()}
                        </div>
                    </div>
                    {_status_pill(status)}
                </div>
                <div class="info-badge">
                    <div class="info-badge-label">Description</div>
                    <div style="font-size:13px;color:var(--muted);line-height:1.6;margin-top:4px;">
                        {description}
                    </div>
                </div>
                <div class="admin-meta-grid">
                    <div class="admin-meta-box">
                        <div class="admin-meta-lbl">Department</div>
                        <div class="admin-meta-val">{department}</div>
                    </div>
                    <div class="admin-meta-box">
                        <div class="admin-meta-lbl">Citizen</div>
                        <div class="admin-meta-val mono" style="font-size:11px;">{str(user_id)[:8]}…</div>
                    </div>
                    <div class="admin-meta-box">
                        <div class="admin-meta-lbl">Confidence</div>
                        <div class="admin-meta-val">{confidence_text}</div>
                    </div>
                    <div class="admin-meta-box">
                        <div class="admin-meta-lbl">Reported</div>
                        <div class="admin-meta-val" style="font-size:11px;">{timestamp}</div>
                    </div>
                    <div class="admin-meta-box">
                        <div class="admin-meta-lbl">Evidence</div>
                        <div class="admin-meta-val" style="font-size:11px;">{evidence_text}</div>
                    </div>
                </div>
                <div style="margin-top:12px;padding:10px 13px;
                     background:var(--info-bg);border-radius:10px;
                     border:1px solid rgba(46,155,224,0.22);">
                    <div class="admin-meta-lbl">Reported Location</div>
                    <div style="font-size:12.5px;color:var(--text-2);margin-top:4px;line-height:1.5;">
                        {location_html}
                    </div>
                </div>
                {_tamper_banner(tampered)}
            </div>"""

    if html_content == _ADMIN_LIST_OPEN:
        html_content += empty_state(
            "📝", "No complaints in the system",
            "Once citizens start reporting issues they will appear here, grouped "
            "by the department that owns them.")

    html_content += '</div>'
    # Deliberately no default selection. Pre-selecting the first complaint means
    # an admin who does not open the dropdown silently updates whichever record
    # happens to sort first — belonging to some unrelated citizen.
    return html_content, image_paths, gr.update(choices=picker_choices, value=None)


# ════════════════════════════════════════════════════════════════════════════
# BUILD GRADIO APP
# ════════════════════════════════════════════════════════════════════════════

with gr.Blocks(title="🏛️ CivicAI — Smart Civic Issue Detection") as demo:

    # ── shared state ──
    header_display     = gr.HTML(_make_header())
    current_user_state = gr.State({"uid": None, "email": None, "role": None})
    selected_role_state = gr.State("citizen")   # tracks which role button is active

    # ════════════════════════════════════════════════════════
    # TAB 1 — Authentication
    # ════════════════════════════════════════════════════════
    # ── AUTH CONTENT (shown when logged out, hidden when logged in) ──
    with gr.Column(visible=True) as auth_content:

        # centred card
        with gr.Column(elem_classes=["auth-card"],
                        scale=1,
                        min_width=320):

            # ── Logo + title ──
            gr.HTML("""
            <div class="auth-brand">
                <div class="auth-mark">🏛️</div>
                <div class="auth-title">Welcome back</div>
                <div class="auth-sub">Sign in to the CivicAI reporting portal</div>
            </div>""")

            # ── LOGIN FORM ──
            with gr.Column(visible=True) as login_form:

                # Role selector buttons
                with gr.Row(equal_height=True):
                    citizen_btn = gr.Button("👤  Citizen", elem_classes=["role-btn"])
                    admin_btn   = gr.Button("🛡️  Admin",   elem_classes=["role-btn"])

                role_display = gr.HTML(_role_selector_html("citizen"))

                # Shared email + password fields
                login_email    = gr.Textbox(label="Email Address",
                                            placeholder="your.email@example.com",
                                            elem_id="login-email")
                login_password = gr.Textbox(label="Password", type="password",
                                            placeholder="Enter your password",
                                            elem_id="login-password")

                gr.HTML('<div class="forgot-link"><a href="#">Forgot password?</a></div>')

                # ── CITIZEN sub-form (visible by default) ──
                with gr.Column(visible=True) as citizen_login_panel:
                    citizen_signin_btn = gr.Button("Sign In", elem_classes=["primary-btn"])

                # ── ADMIN sub-form (hidden until Admin role is selected) ──
                with gr.Column(visible=False) as admin_login_panel:
                    admin_otp_input = gr.Textbox(
                        label="Admin OTP",
                        placeholder="Enter 6-digit code from terminal...",
                        max_lines=1,
                    )
                    with gr.Row(equal_height=True):
                        get_otp_btn  = gr.Button("Get OTP",  elem_classes=["secondary-btn"])
                        admin_signin_btn = gr.Button("Sign In", elem_classes=["primary-btn"])

                gr.HTML("""
                <div class="auth-divider">New here</div>
                <div class="auth-foot">Create an account to start reporting issues.</div>""")

                goto_signup_btn = gr.Button("Create Account →",
                                            elem_classes=["secondary-btn"])

            # ── SIGNUP FORM ──
            with gr.Column(visible=False) as signup_form:

                gr.HTML("""
                <div class="auth-brand">
                    <div class="auth-mark">✨</div>
                    <div class="auth-title">Create account</div>
                    <div class="auth-sub">Join CivicAI and start reporting issues</div>
                </div>""")

                # role selector repeated for signup
                with gr.Row(equal_height=True):
                    signup_citizen_btn = gr.Button("👤  Citizen", elem_classes=["role-btn"])
                    signup_admin_btn   = gr.Button("🛡️  Admin",   elem_classes=["role-btn"])

                signup_role_display = gr.HTML(_role_selector_html("citizen"))

                signup_email    = gr.Textbox(label="Email Address",
                                                placeholder="your.email@example.com")
                signup_password = gr.Textbox(label="Password", type="password",
                                                placeholder="Create a password (min 6 chars)")

                signup_btn = gr.Button("Create Account ✓", elem_classes=["primary-btn"])

                gr.HTML('<div class="auth-divider">Already registered</div>')
                goto_login_btn = gr.Button("← Back to Sign In",
                                            elem_classes=["secondary-btn"])

            auth_status = gr.HTML()


    # ════════════════════════════════════════════════════════
    # TAB 2 — Citizen Dashboard  (hidden until citizen logs in)
    # ════════════════════════════════════════════════════════
    with gr.Tab("👥 Citizen Dashboard", visible=False) as citizen_tab:

        citizen_stats=gr.HTML()

        # ── Notification Bell Row ──
        with gr.Row():
            with gr.Column(scale=3):
                notif_bell_html = gr.HTML(
                    '<div class="notif-bell-wrap">🔔</div>',
                    elem_id="notif-bell-area"
                )
            with gr.Column(scale=1, min_width=150):
                bell_btn = gr.Button("🔔 Notifications",
                                     elem_classes=["secondary-btn"], size="sm")
            with gr.Column(scale=1, min_width=120):
                citizen_refresh_btn = gr.Button("🔄 Refresh",
                                                elem_classes=["secondary-btn"], size="sm")

        # Polls for status changes made by an admin so the citizen's view
        # updates without a re-login. 15s is frequent enough to feel live
        # without hammering MongoDB.
        citizen_poll = gr.Timer(15)

        # Notification panel (hidden until bell is clicked)
        notif_panel_html = gr.HTML("", visible=False, elem_id="notif-panel")

        with gr.Row():
            with gr.Column(scale=1):
                gr.HTML("""
                <div class="section-title" style="margin-top:0;">Report an issue</div>
                <div class="section-sub">A photo is all the classifier needs — it runs
                on this machine, so the image never leaves the building.</div>""")
                image_in = gr.Image(type="filepath", label="📷 Photograph of the issue")
                user_msg = gr.Textbox(
                    label="Additional Notes (Optional)",
                    placeholder="Severity, landmark, or any other details...",
                    lines=3
                )

                # ── Location capture (Module 5) ──────────────────────────
                gr.HTML('<div class="section-title">📍 Where is it?</div>')

                locate_btn = gr.Button("📍 Use My Current Location",
                                       elem_classes=["secondary-btn"])

                # Hidden carriers: the browser's Geolocation API writes into
                # these via JS, then Python reads them like any other input.
                gps_lat    = gr.Textbox(visible=False, elem_id="gps-lat")
                gps_lon    = gr.Textbox(visible=False, elem_id="gps-lon")
                gps_status = gr.Textbox(visible=False, elem_id="gps-status")

                manual_address = gr.Textbox(
                    label="Or type the address / landmark",
                    placeholder="e.g. 3rd Cross Street, near the bus stop",
                    lines=2,
                )

                location_display = gr.HTML(
                    '<div class="pill pill-muted" style="margin-top:6px;">'
                    '📍 No location captured yet</div>'
                )

                submit_btn = gr.Button("⚡  Analyse & Submit",
                                       elem_classes=["success-btn"])

            with gr.Column(scale=1):
                gr.HTML("""
                <div class="section-title" style="margin-top:0;">Analysis result</div>
                <div class="section-sub">Category, department and confidence, produced
                on device.</div>""")
                ai_out_html = gr.HTML(empty_state(
                    "🧭", "Nothing analysed yet",
                    "Upload a photo and press Analyse & Submit — the predicted "
                    "category, the department it routes to and the model's confidence "
                    "will appear here."))
                uploaded_img_display = gr.Image(
                    label="Uploaded Image Preview",
                    elem_classes=["image-display-card"],
                    interactive=False
                )
                gr.HTML('<div class="section-title">📋 My reports</div>')

                citizen_history = gr.HTML(empty_state(
                    "📬", "No complaints yet",
                    "Reports you submit will be listed here with their current status."))

        # ── Sign-out button (always accessible in Auth tab) ──
        with gr.Row():
            with gr.Column():
                gr.HTML('<div style="height:16px;"></div>')
                citizen_signout_btn = gr.Button("Sign Out", elem_classes=["signout-btn"])

    # ════════════════════════════════════════════════════════
    # TAB 3 — Admin Dashboard  (hidden until admin logs in)
    # ════════════════════════════════════════════════════════
    with gr.Tab("🛡️ Admin Dashboard", visible=False) as admin_tab:

        with gr.Row(equal_height=True):
            with gr.Column(scale=4):
                gr.HTML("""
                <div style="padding:4px 0 8px;">
                    <div class="toolbar-title">Complaint queue</div>
                    <div class="toolbar-sub">Every report in the city, grouped by the
                    department that owns it.</div>
                </div>""")
            with gr.Column(scale=1, min_width=170):
                admin_view_btn = gr.Button("🔄 Refresh",
                                           elem_classes=["primary-btn"])

        admin_container = gr.HTML(empty_state(
            "🗃️", "Queue not loaded",
            "Press Refresh to pull the current complaints from the database."))

        # ── Status Update Panel ──
        gr.HTML("""
        <div class="section-title">🔧 Update complaint status</div>
        <div class="section-sub">Pick a complaint, set its new state, and the citizen
        who filed it is notified.</div>""")

        with gr.Row(equal_height=True):
            with gr.Column(scale=3):
                status_complaint_id = gr.Dropdown(
                    label="Complaint",
                    choices=[],
                    interactive=True,
                    filterable=True,
                    info="Populated when complaints load — no need to copy IDs.",
                    elem_id="status-complaint-id",
                )
            with gr.Column(scale=2):
                status_new_value = gr.Dropdown(
                    label="New Status",
                    choices=[
                        ("🔴 Pending",      "pending"),
                        ("🟡 In Progress",  "in_progress"),
                        ("✅ Resolved",     "resolved"),
                    ],
                    value="in_progress",
                    elem_classes=["status-select"]
                )
            with gr.Column(scale=1):
                status_update_btn = gr.Button("Update →", elem_classes=["update-btn"])

        status_update_result = gr.HTML("")

        gr.HTML("""
        <div class="section-title">🖼️ Evidence gallery</div>
        <div class="section-sub">Every submitted photograph, decrypted for review in
        the order the cards above reference them.</div>""")

        admin_gallery = gr.Gallery(
            label="All Complaint Images",
            show_label=False,
            columns=3,
            rows=3,
            height="auto",
            object_fit="cover",
            preview=False,          # ← CRITICAL: disable preview panel (removes the split layout)
            elem_id="admin-gallery",
            elem_classes=["fixed-gallery"]
        )

        # ── Sign-out button (always accessible in Auth tab) ──
        with gr.Row():
            with gr.Column():
                gr.HTML('<div style="height:16px;"></div>')
                admin_signout_btn = gr.Button("Sign Out", elem_classes=["signout-btn"])
    # ════════════════════════════════════════════════════════
    # WIRING
    # ════════════════════════════════════════════════════════

    # Role selection (login form) — switches between citizen/admin sub-forms
    citizen_btn.click(
        select_citizen_role,
        inputs=[],
        outputs=[selected_role_state, role_display, citizen_login_panel, admin_login_panel]
    )
    admin_btn.click(
        select_admin_role,
        inputs=[],
        outputs=[selected_role_state, role_display, citizen_login_panel, admin_login_panel]
    )

    # Role selection (signup form)
    signup_citizen_btn.click(
        lambda: ("citizen", _role_selector_html("citizen")),
        inputs=[],
        outputs=[selected_role_state, signup_role_display]
    )
    signup_admin_btn.click(
        lambda: ("admin", _role_selector_html("admin")),
        inputs=[],
        outputs=[selected_role_state, signup_role_display]
    )

    # Toggle login ↔ signup
    goto_signup_btn.click(
        show_signup,
        inputs=[],
        outputs=[login_form, signup_form]
    )
    goto_login_btn.click(
        show_login,
        inputs=[],
        outputs=[login_form, signup_form]
    )

    # Citizen Sign In
    citizen_signin_btn.click(
        login,
        inputs=[login_email, login_password, selected_role_state, current_user_state, admin_otp_input],
        outputs=[
            auth_status,
            current_user_state,
            header_display,
            auth_content,
            citizen_tab,
            admin_tab,
            admin_container,
            admin_gallery,
            citizen_stats,
            citizen_history,
            notif_bell_html,
            status_complaint_id,
        ]
    )

    # Admin: Get OTP button
    get_otp_btn.click(
        request_admin_otp,
        inputs=[login_email, login_password],
        outputs=[auth_status]
    )

    # Admin: Sign In button
    admin_signin_btn.click(
        login,
        inputs=[login_email, login_password, selected_role_state, current_user_state, admin_otp_input],
        outputs=[
            auth_status,
            current_user_state,
            header_display,
            auth_content,
            citizen_tab,
            admin_tab,
            admin_container,
            admin_gallery,
            citizen_stats,
            citizen_history,
            notif_bell_html,
            status_complaint_id,
        ]
    )

    # Signup
    signup_btn.click(
        signup,
        inputs=[signup_email, signup_password, selected_role_state, current_user_state],
        outputs=[auth_status, current_user_state, signup_form, login_form]
    )

    # Signout
    admin_signout_btn.click(
        signout,
        inputs=[current_user_state],
        outputs=[
            auth_status,
            current_user_state,
            header_display,
            auth_content,
            citizen_tab,
            admin_tab,
        ]
    )
    citizen_signout_btn.click(
        signout,
        inputs=[current_user_state],
        outputs=[
            auth_status,
            current_user_state,
            header_display,
            auth_content,
            citizen_tab,
            admin_tab,
        ]
    )

    # ── Location capture ──────────────────────────────────────────────
    # The JS runs in the citizen's browser and resolves to [lat, lon, status];
    # .then() hands those values to Python for reverse geocoding.
    locate_btn.click(
        fn=None,
        inputs=None,
        outputs=[gps_lat, gps_lon, gps_status],
        js=GEOLOCATION_JS,
    ).then(
        describe_location,
        inputs=[gps_lat, gps_lon, manual_address, gps_status],
        outputs=[location_display],
    )

    # Typing an address re-renders the preview, so the citizen sees exactly
    # what will be filed before submitting.
    manual_address.blur(
        describe_location,
        inputs=[gps_lat, gps_lon, manual_address, gps_status],
        outputs=[location_display],
    )

    # Citizen complaint submission
    submit_btn.click(
        process_complaint,
        inputs=[image_in, user_msg, gps_lat, gps_lon, manual_address, current_user_state],
        outputs=[ai_out_html, uploaded_img_display, citizen_stats, citizen_history]
    )

    # Admin refresh
    admin_view_btn.click(
        get_admin_complaints_html,
        inputs=[current_user_state],
        outputs=[admin_container, admin_gallery, status_complaint_id]
    )

    # Admin status update, then reload the board so the new status and the
    # refreshed picker are visible without a manual refresh.
    status_update_btn.click(
        handle_status_update,
        inputs=[status_complaint_id, status_new_value, current_user_state],
        outputs=[status_update_result]
    ).then(
        get_admin_complaints_html,
        inputs=[current_user_state],
        outputs=[admin_container, admin_gallery, status_complaint_id]
    )

    # Citizen view auto-refresh — picks up admin status changes live
    citizen_poll.tick(
        refresh_citizen_view,
        inputs=[current_user_state],
        outputs=[citizen_stats, citizen_history, notif_bell_html],
        show_progress="hidden",      # a spinner every 15s would be distracting
    )
    citizen_refresh_btn.click(
        refresh_citizen_view,
        inputs=[current_user_state],
        outputs=[citizen_stats, citizen_history, notif_bell_html],
    )

    # Citizen notification bell
    bell_btn.click(
        handle_bell_click,
        inputs=[current_user_state],
        outputs=[notif_panel_html, notif_bell_html]
    )
    bell_btn.click(
        lambda: gr.update(visible=True),
        inputs=[],
        outputs=[notif_panel_html]
    )


def _startup_report() -> None:
    """Print the state of each subsystem so failures are visible immediately."""
    print("\n" + "=" * 66)
    print("  CivicAI — Civic Issue Reporting and Resolution System")
    print("=" * 66)

    # Must run before anything hashes a complaint: CivicHash-512 loads this key
    # but never creates it.
    from .image_encryption import ensure_key
    print(f"  [OK]   AES-256 key ready at {ensure_key()}")

    if warm_up_model():
        from .civic_classifier import _load
        predictor = _load()
        print(f"  [OK]   Issue classifier loaded on {predictor.device}")
        print(f"         Model     : {predictor.describe()}")
        print(f"         Categories: {', '.join(predictor.classes)}")
    else:
        print("  [WARN] No trained classifier found — complaint submission will")
        print("         fail until you run:")
        print("           python -m training.download_civic")
        print("           python -m training.prepare_civic")
        print("           python -m training.train_civic")

    chain = verify_chain()
    marker = "OK" if chain["valid"] else "ALERT"
    print(f"  [{marker}]{'':<3}Audit log: {chain['message']}")

    from .geo_service import MUNICIPAL_LAT, MUNICIPAL_LON, MUNICIPAL_RADIUS_KM
    print(f"  [OK]   Geolocation: centroid ({MUNICIPAL_LAT}, {MUNICIPAL_LON}), "
          f"radius {MUNICIPAL_RADIUS_KM:.0f} km")
    print("=" * 66 + "\n")


# Guarded so the module can be imported for tests and tooling without starting
# a server on the port the real app wants.
if __name__ == "__main__":
    _startup_report()
    demo.launch(debug=True, favicon_path=None, share=False,
                css=custom_css, theme=APP_THEME)