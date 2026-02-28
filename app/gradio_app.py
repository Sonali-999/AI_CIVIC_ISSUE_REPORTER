import os
import gradio as gr
from dotenv import load_dotenv

from .auth import register_user_wrapper, login_user_wrapper
from .db_utils import save_complaint, get_complaints_by_department
from .image_processor import encode_image
from .ai_service import analyze_image_with_query

# ---------------- Load environment ----------------
load_dotenv()

# ---------------- System Prompt ----------------
system_prompt = (
    "You are an AI civic issue detector. Analyze the uploaded image, identify the type of problem "
    "(e.g., garbage, pothole, dead animal, broken streetlight, sewage), determine the relevant municipal department "
    "(Sanitation, Roads, Electricity, etc.), generate a short title and description including impact on public hygiene, safety, and environment. "
    "Output should be concise and ready to autofill the complaint form."
)

# ---------------- CSS ----------------
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700&display=swap');

:root {
    --navy:   #0B1F3A;
    --blue:   #1A3F6F;
    --teal:   #0D7A6F;
    --tealL:  #12A99A;
    --sky:    #1E90D4;
    --bg:     #F0F4F8;
    --card:   #FFFFFF;
    --border: #D8E3EE;
    --text:   #1A2B42;
    --muted:  #6B7E96;
    --done:   #10B981;
    --warn:   #F59E0B;
    --danger: #EF4444;
    --radius: 12px;
    --shadow-sm: 0 2px 12px rgba(11,31,58,0.07);
    --shadow-md: 0 4px 24px rgba(11,31,58,0.12);
}

*, *::before, *::after { box-sizing: border-box; }
body, .gradio-container {
    font-family: 'Sora', -apple-system, sans-serif !important;
    background: var(--bg) !important;
    color: var(--text) !important;
    margin: 0 !important; padding: 0 !important;
}
footer { display: none !important; }
.gradio-container { max-width: 100% !important; padding: 0 !important; }

/* ── sticky header ── */
#civicai-header {
    background: linear-gradient(135deg, var(--navy), var(--blue)) !important;
    box-shadow: 0 2px 20px rgba(11,31,58,0.4) !important;
    padding: 0 !important; margin: 0 !important;
}
#civicai-header-inner {
    display: flex; align-items: center;
    justify-content: space-between;
    padding: 16px 32px;
    max-width: 1400px; margin: 0 auto;
}
.hdr-logo { display: flex; align-items: center; gap: 12px; }
.hdr-logo-icon {
    width: 40px; height: 40px; background: var(--teal);
    border-radius: 10px; display: flex; align-items: center;
    justify-content: center; font-size: 20px;
}
.hdr-logo-name { font-size: 18px; font-weight: 700; color: white; letter-spacing: -0.3px; }
.hdr-logo-sub  { font-size: 11px; color: rgba(255,255,255,0.5); }
.hdr-user {
    display: flex; align-items: center; gap: 8px;
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 40px; padding: 6px 14px 6px 6px;
    color: white; font-size: 12px; font-weight: 600;
}
.hdr-avatar {
    width: 28px; height: 28px; border-radius: 50%;
    background: linear-gradient(135deg, var(--teal), var(--sky));
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; color: white;
}

/* ── tabs ── */
.tab-nav {
    display: flex !important; justify-content: center !important;
    gap: 0 !important;
    background: var(--card) !important;
    border-bottom: 1px solid var(--border) !important;
    padding: 0 32px !important; margin: 0 !important;
    box-shadow: var(--shadow-sm) !important;
}
.tab-nav button {
    background: transparent !important; border: none !important;
    border-bottom: 3px solid transparent !important;
    border-radius: 0 !important;
    padding: 14px 26px !important;
    font-size: 13.5px !important; font-weight: 600 !important;
    color: var(--muted) !important;
    cursor: pointer !important; transition: all 0.2s !important;
    box-shadow: none !important; transform: none !important;
}
.tab-nav button:hover {
    color: var(--text) !important;
    background: var(--bg) !important;
    transform: none !important; box-shadow: none !important;
}
.tab-nav button.selected {
    color: var(--teal) !important;
    border-bottom-color: var(--teal) !important;
    background: transparent !important; box-shadow: none !important;
}
.tabitem { padding: 28px 32px !important; }

/* ── NEW AUTH CARD ── */
.auth-wrapper {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px 16px;
}
.auth-card {
    width: 100%;
    max-width: 440px !important;
    background: var(--card) !important;
    border-radius: 24px !important;
    padding: 40px 36px !important;
    box-shadow: 0 8px 40px rgba(11,31,58,0.15) !important;
    border: 1px solid var(--border) !important;
    margin: 0 auto !important;
}

/* ── role selector ── */
.role-selector {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin: 20px 0 24px;
}
.role-btn {
    display: flex; flex-direction: column;
    align-items: center; gap: 6px;
    padding: 14px 10px;
    background: var(--bg) !important;
    border: 2px solid var(--border) !important;
    border-radius: 14px !important;
    cursor: pointer;
    transition: all 0.2s !important;
    font-size: 12px !important; font-weight: 600 !important;
    color: var(--muted) !important;
    box-shadow: none !important;
}
.role-btn:hover {
    border-color: var(--teal) !important;
    color: var(--teal) !important;
    background: rgba(13,122,111,0.05) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(13,122,111,0.15) !important;
}
.role-btn.active-citizen {
    border-color: var(--teal) !important;
    background: rgba(13,122,111,0.07) !important;
    color: var(--teal) !important;
    box-shadow: 0 0 0 3px rgba(13,122,111,0.15) !important;
}
.role-btn.active-admin {
    border-color: var(--navy) !important;
    background: rgba(11,31,58,0.07) !important;
    color: var(--navy) !important;
    box-shadow: 0 0 0 3px rgba(11,31,58,0.15) !important;
}
.role-icon { font-size: 26px; }

/* ── inputs ── */
input, textarea, select {
    border: 1.5px solid var(--border) !important;
    border-radius: 10px !important;
    padding: 12px 16px !important;
    font-size: 14px !important;
    font-family: 'Sora', sans-serif !important;
    color: var(--text) !important;
    background: #FAFCFF !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
    outline: none !important;
    width: 100% !important;
}
input:focus, textarea:focus, select:focus {
    border-color: var(--teal) !important;
    box-shadow: 0 0 0 3px rgba(13,122,111,0.1) !important;
}

/* ── buttons ── */
button { font-family: 'Sora', sans-serif !important; }

.primary-btn button, button.primary-btn {
    background: linear-gradient(135deg, var(--blue), var(--teal)) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important;
    font-size: 15px !important; font-weight: 700 !important;
    padding: 14px !important;
    box-shadow: 0 4px 14px rgba(13,122,111,0.3) !important;
    transition: all 0.2s !important;
    width: 100% !important;
}
.primary-btn button:hover, button.primary-btn:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(13,122,111,0.4) !important;
}

.secondary-btn button, button.secondary-btn {
    background: transparent !important;
    color: var(--blue) !important;
    border: 1.5px solid var(--blue) !important;
    border-radius: 10px !important;
    font-size: 14px !important; font-weight: 600 !important;
    transition: all 0.2s !important;
    box-shadow: none !important;
}
.secondary-btn button:hover, button.secondary-btn:hover {
    background: var(--blue) !important; color: white !important;
    transform: translateY(-1px) !important;
}

.signout-btn button, button.signout-btn {
    background: var(--danger) !important;
    color: white !important; border: none !important;
    border-radius: 8px !important;
    font-size: 13px !important; font-weight: 600 !important;
    transition: all 0.2s !important;
}
.signout-btn button:hover, button.signout-btn:hover {
    background: #DC2626 !important; transform: translateY(-1px) !important;
}

.success-btn button, button.success-btn {
    background: linear-gradient(135deg, var(--blue), var(--teal)) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important;
    font-size: 14px !important; font-weight: 700 !important;
    box-shadow: 0 4px 14px rgba(13,122,111,0.3) !important;
    transition: all 0.2s !important;
}
.success-btn button:hover, button.success-btn:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(13,122,111,0.4) !important;
}

/* ── divider ── */
.auth-divider {
    display: flex; align-items: center; gap: 12px;
    margin: 20px 0; color: var(--muted); font-size: 12px;
}
.auth-divider::before, .auth-divider::after {
    content: ''; flex: 1; height: 1px; background: var(--border);
}

/* ── link-style text button ── */
.link-btn button, button.link-btn {
    background: none !important; border: none !important;
    color: var(--teal) !important; font-weight: 700 !important;
    font-size: 13px !important; padding: 0 !important;
    cursor: pointer !important; box-shadow: none !important;
    text-decoration: underline !important;
    display: inline !important; width: auto !important;
}
.link-btn button:hover, button.link-btn:hover {
    color: var(--tealL) !important; transform: none !important;
    box-shadow: none !important;
}

/* ── status messages ── */
.status-success {
    background: linear-gradient(135deg, var(--teal), var(--tealL));
    color: white; padding: 12px 18px; border-radius: 10px;
    font-weight: 600; font-size: 13.5px; text-align: center;
    animation: fadeUp 0.3s ease;
}
.status-error {
    background: linear-gradient(135deg, var(--danger), #DC2626);
    color: white; padding: 12px 18px; border-radius: 10px;
    font-weight: 600; font-size: 13.5px; text-align: center;
    animation: fadeUp 0.3s ease;
}
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* ── stat strip ── */
.stat-strip {
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 14px; margin-bottom: 24px;
}
.stat-card {
    border-radius: 14px; padding: 20px 22px;
    color: white; position: relative; overflow: hidden;
}
.stat-card::after {
    content: ''; position: absolute;
    right: -18px; top: -18px; width: 80px; height: 80px;
    border-radius: 50%; background: rgba(255,255,255,0.08);
}
.stat-lbl { font-size: 11px; font-weight: 600; opacity: 0.8; letter-spacing: 0.4px; }
.stat-val { font-size: 28px; font-weight: 800; margin-top: 6px; letter-spacing: -1px; }

/* ── complaint result card ── */
.complaint-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    overflow: hidden;
    box-shadow: var(--shadow-sm);
    animation: fadeUp 0.35s ease;
    position: relative;
}
.complaint-card::before {
    content: ''; position: absolute;
    top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, var(--teal), var(--sky));
}
.complaint-card-header {
    background: linear-gradient(135deg, var(--navy), var(--blue));
    color: white; padding: 14px 20px;
    font-size: 13.5px; font-weight: 700;
}
.complaint-card-body { padding: 18px 20px; }

.info-badge {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 14px;
    margin-bottom: 10px;
}
.info-badge-label {
    font-size: 11px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;
}
.info-badge-value {
    font-size: 14px; font-weight: 600; color: var(--text);
}

.dept-header {
    background: linear-gradient(135deg, var(--navy), var(--blue));
    color: white; border-radius: 12px;
    padding: 14px 20px; margin: 20px 0 12px;
    font-size: 15px; font-weight: 700;
    display: flex; align-items: center; gap: 10px;
    box-shadow: 0 4px 12px rgba(11,31,58,0.2);
    letter-spacing: 0.3px;
}

.admin-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 18px 20px;
    margin-bottom: 12px; position: relative;
    transition: box-shadow 0.2s;
}
.admin-card::before {
    content: ''; position: absolute;
    top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, var(--teal), var(--sky));
    border-radius: 12px 12px 0 0;
}
.admin-card:hover { box-shadow: var(--shadow-md); }
.admin-meta-grid {
    display: grid; grid-template-columns: repeat(4,1fr);
    gap: 8px; margin-top: 12px;
}
.admin-meta-box {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 8px 10px; text-align: center;
}
.admin-meta-lbl {
    font-size: 10px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.4px;
}
.admin-meta-val { font-size: 12.5px; font-weight: 700; color: var(--text); margin-top: 2px; }

.image-display-card { border-radius: 12px; overflow: hidden; }

/* ── section label ── */
.section-title {
    font-size: 15px !important; font-weight: 700 !important;
    color: var(--text) !important;
    margin-bottom: 16px !important; padding-bottom: 12px !important;
    border-bottom: 2px solid var(--border) !important;
}

/* ── forgot password link area ── */
.forgot-link {
    text-align: right; margin-top: -8px; margin-bottom: 16px;
    font-size: 12px;
}
.forgot-link a {
    color: var(--teal); font-weight: 600; text-decoration: none;
}
.forgot-link a:hover { text-decoration: underline; }

/* ── responsive ── */
@media (max-width: 768px) {
    .stat-strip  { grid-template-columns: 1fr 1fr !important; }
    .auth-card   { padding: 28px 20px !important; }
    .admin-meta-grid { grid-template-columns: 1fr 1fr !important; }
    .tabitem { padding: 20px 16px !important; }
}
"""


# ════════════════════════════════════════════════════════════════════════════
# HEADER HELPER
# ════════════════════════════════════════════════════════════════════════════

def _make_header(email: str = "", role: str = "") -> str:
    user_html = ""
    if email:
        initials = "".join(p[0].upper() for p in email.split("@")[0].split(".")[:2]) or "U"
        role_label = {"citizen": "Citizen", "admin": "Administrator"}.get(role, role.title())
        user_html = f"""
        <div class="hdr-user">
            <div class="hdr-avatar">{initials}</div>
            <span>{email} &nbsp;·&nbsp; {role_label}</span>
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
            {user_html}
        </div>
    </div>"""


# ════════════════════════════════════════════════════════════════════════════
# AUTH HELPERS — role selector HTML builders
# ════════════════════════════════════════════════════════════════════════════

def _role_selector_html(selected: str = "citizen") -> str:
    """Renders the two role buttons with the active state highlighted."""
    citizen_cls = "role-btn active-citizen" if selected == "citizen" else "role-btn"
    admin_cls   = "role-btn active-admin"   if selected == "admin"   else "role-btn"
    return f"""
    <div class="role-selector">
        <button class="{citizen_cls}" onclick="(function(){{
            document.getElementById('role-hidden').value='citizen';
        }})(); return false;" type="button">
            <span class="role-icon">👤</span>
            <span>Citizen</span>
        </button>
        <button class="{admin_cls}" onclick="(function(){{
            document.getElementById('role-hidden').value='admin';
        }})(); return false;" type="button">
            <span class="role-icon">🛡️</span>
            <span>Admin</span>
        </button>
    </div>"""


# ════════════════════════════════════════════════════════════════════════════
# AUTH FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

def select_citizen_role():
    """Called when Citizen role button is clicked."""
    return "citizen", _role_selector_html("citizen")

def select_admin_role():
    """Called when Admin role button is clicked."""
    return "admin", _role_selector_html("admin")


def signup(email, password, role, state):
    """Register with the chosen role."""
    if not email or not password:
        return (
            '<div class="status-error">❌ Please fill in all fields.</div>',
            state,
            gr.update(visible=True),   # signup form stays visible
            gr.update(visible=False),
        )
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


def login(email, password, role, state):
    """Login and route to the correct dashboard."""
    result = login_user_wrapper(email, password)
    if result.get("status") == "success":
        actual_role = result.get("role", role)  # trust DB role
        state["uid"]   = result["user_id"]
        state["email"] = email
        state["role"]  = actual_role

        is_citizen = (actual_role == "citizen")
        is_admin   = (actual_role == "admin")

        return (
            f'<div class="status-success">✅ Welcome back, {email}!</div>',
            state,
            _make_header(email, actual_role),
            # Auth tab visibility
            gr.update(visible=False),   # hide auth tab content
            # Citizen tab
            gr.update(visible=is_citizen),
            # Admin tab
            gr.update(visible=is_admin),
        )
    else:
        state["uid"] = state["email"] = state["role"] = None
        return (
            '<div class="status-error">❌ Invalid credentials. Please try again.</div>',
            state,
            _make_header(),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
        )


def signout(state):
    state["uid"] = state["email"] = state["role"] = None
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


# ════════════════════════════════════════════════════════════════════════════
# AI COMPLAINT PROCESSING
# ════════════════════════════════════════════════════════════════════════════

def parse_ai_output(ai_output):
    title = category = department = description = "N/A"
    try:
        for line in ai_output.split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if "title"         in key: title       = value
            elif "category"    in key: category    = value
            elif "department"  in key: department  = value
            elif "description" in key: description = value
    except Exception as e:
        print("Error parsing AI output:", e)
    return title, category, department, description


def format_citizen_ai_output(title, category, department, description):
    dept_icons = {"Sanitation": "🗑️", "Roads": "🛣️", "Electricity": "⚡", "Water": "💧"}
    icon = dept_icons.get(department, "🏢")
    return f"""
    <div class="complaint-card">
        <div class="complaint-card-header">⚡ AI Analysis Complete — Complaint Registered</div>
        <div class="complaint-card-body">
            <div class="info-badge">
                <div class="info-badge-label">📌 Issue Title</div>
                <div class="info-badge-value" style="font-size:15px;">{title}</div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
                <div class="info-badge" style="margin-bottom:0;">
                    <div class="info-badge-label">🏷️ Category</div>
                    <div class="info-badge-value">{category}</div>
                </div>
                <div class="info-badge" style="margin-bottom:0;">
                    <div class="info-badge-label">{icon} Department</div>
                    <div class="info-badge-value">{department}</div>
                </div>
            </div>
            <div class="info-badge" style="margin-top:10px;">
                <div class="info-badge-label">📝 Description</div>
                <div style="font-size:13.5px;color:#6B7E96;line-height:1.7;margin-top:4px;">{description}</div>
            </div>
            <div style="text-align:center;margin-top:14px;padding:12px;
                 background:rgba(13,122,111,0.07);border-radius:10px;
                 color:#0D7A6F;font-weight:700;font-size:13px;">
                ✅ Complaint submitted! We'll process it shortly.
            </div>
        </div>
    </div>"""


def process_complaint(image_path, user_msg, state):
    if not state.get("uid"):
        return '<div class="status-error">❌ Please log in first to submit a complaint.</div>', None
    if not image_path:
        return '<div class="status-error">❌ Please upload an image of the issue.</div>', None
    try:
        ai_output = analyze_image_with_query(
            query_text=f"{system_prompt} {user_msg}",
            encoded_image=encode_image(image_path),
            model="meta-llama/llama-4-scout-17b-16e-instruct"
        )
        title, category, department, description = parse_ai_output(ai_output)
        save_complaint(state["uid"], title, category, department, description, image_path)
        html_content = format_citizen_ai_output(title, category, department, description)
        return html_content, image_path
    except Exception as e:
        return f'<div class="status-error">❌ Error processing complaint: {str(e)}</div>', None


# ════════════════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ════════════════════════════════════════════════════════════════════════════

def get_admin_complaints_html(state):
    if state.get("role") != "admin":
        return '<div class="status-error">🚫 Admin access required.</div>', []

    departments   = ["Sanitation", "Roads", "Electricity", "Water"]
    dept_icons    = {"Sanitation": "🗑️", "Roads": "🛣️", "Electricity": "⚡", "Water": "💧"}
    status_colors = {
        "resolved":    "#10B981",
        "in_progress": "#F59E0B",
        "pending":     "#EF4444",
    }

    html_content = '<div style="animation:fadeUp 0.4s ease;">'
    image_paths  = []

    for dept in departments:
        rows = get_complaints_by_department(dept)
        if not rows:
            continue

        html_content += f"""
        <div class="dept-header">
            {dept_icons.get(dept,'🏢')} {dept.upper()} DEPARTMENT
        </div>"""

        for row in rows:
            row_id      = str(row.get("_id"))
            user_id     = row.get("user_id")
            title       = row.get("title")
            category    = row.get("category")
            department  = row.get("department")
            description = row.get("description")
            image_path  = row.get("image_path")
            timestamp   = row.get("created_at")
            status      = row.get("status", "pending")

            status_color = status_colors.get(status.lower(), "#6B7E96")

            if image_path and os.path.exists(image_path):
                image_paths.append(image_path)
            img_idx = len(image_paths)

            html_content += f"""
            <div class="admin-card">
                <div style="display:flex;justify-content:space-between;
                     align-items:flex-start;margin-bottom:10px;">
                    <div>
                        <div style="font-size:11px;color:#6B7E96;font-weight:600;
                             font-family:monospace;margin-bottom:4px;">ID: #{row_id}</div>
                        <div style="font-size:15px;font-weight:700;color:#1A2B42;">{title}</div>
                        <div style="font-size:12px;color:#6B7E96;margin-top:2px;">Category: {category}</div>
                    </div>
                    <span style="display:inline-flex;align-items:center;gap:5px;
                          padding:3px 10px;border-radius:20px;font-size:11.5px;
                          font-weight:600;background:{status_color}1a;color:{status_color};">
                        ● {status.replace('_',' ').title()}
                    </span>
                </div>
                <div class="info-badge">
                    <div class="info-badge-label">📝 Description</div>
                    <div style="font-size:13px;color:#6B7E96;line-height:1.6;margin-top:4px;">
                        {description}
                    </div>
                </div>
                <div class="admin-meta-grid">
                    <div class="admin-meta-box">
                        <div class="admin-meta-lbl">Status</div>
                        <div class="admin-meta-val" style="color:{status_color};">
                            {status.replace('_',' ').title()}
                        </div>
                    </div>
                    <div class="admin-meta-box">
                        <div class="admin-meta-lbl">Department</div>
                        <div class="admin-meta-val">{department}</div>
                    </div>
                    <div class="admin-meta-box">
                        <div class="admin-meta-lbl">User</div>
                        <div class="admin-meta-val">#{user_id}</div>
                    </div>
                    <div class="admin-meta-box">
                        <div class="admin-meta-lbl">Time</div>
                        <div class="admin-meta-val" style="font-size:11px;">{timestamp}</div>
                    </div>
                </div>
                {f'<div style="font-size:11px;color:#6B7E96;margin-top:8px;font-style:italic;">📷 Image #{img_idx} in gallery below</div>' if img_idx else ''}
            </div>"""

    if html_content == '<div style="animation:fadeUp 0.4s ease;">':
        html_content += """
        <div style="text-align:center;padding:48px 24px;color:#6B7E96;font-size:15px;">
            📝 No complaints found in the system.
        </div>"""

    html_content += '</div>'
    return html_content, image_paths


# ════════════════════════════════════════════════════════════════════════════
# BUILD GRADIO APP
# ════════════════════════════════════════════════════════════════════════════

with gr.Blocks(css=custom_css, theme=gr.themes.Soft(),
               title="🏛️ CivicAI — Smart Civic Issue Detection") as demo:

    # ── shared state ──
    header_display     = gr.HTML(_make_header())
    current_user_state = gr.State({"uid": None, "email": None, "role": None})
    selected_role_state = gr.State("citizen")   # tracks which role button is active

    # ════════════════════════════════════════════════════════
    # TAB 1 — Authentication
    # ════════════════════════════════════════════════════════
    with gr.Tab("🔐 Authentication"):

        # ── AUTH CONTENT (shown when logged out, hidden when logged in) ──
        with gr.Column(visible=True) as auth_content:

            # centred card
            with gr.Column(elem_classes=["auth-card"],
                           scale=1,
                           min_width=320):

                # ── Logo + title ──
                gr.HTML("""
                <div style="text-align:center;margin-bottom:8px;">
                    <div style="width:56px;height:56px;border-radius:16px;
                         background:linear-gradient(135deg,#0B1F3A,#0D7A6F);
                         display:flex;align-items:center;justify-content:center;
                         font-size:28px;margin:0 auto 14px;
                         box-shadow:0 4px 16px rgba(11,31,58,0.25);">🏛️</div>
                    <div style="font-size:22px;font-weight:800;color:#1A2B42;
                         letter-spacing:-0.5px;">Welcome Back</div>
                    <div style="font-size:13px;color:#6B7E96;margin-top:4px;">
                        Sign in to CivicAI Portal
                    </div>
                </div>""")

                # ── LOGIN FORM ──
                with gr.Column(visible=True) as login_form:

                    # Role selector — two Gradio buttons that look like cards
                    role_display = gr.HTML(_role_selector_html("citizen"))
                    citizen_role_btn = gr.Button("👤  Citizen",
                                                 elem_classes=["role-btn"],
                                                 visible=False)
                    admin_role_btn   = gr.Button("🛡️  Admin",
                                                 elem_classes=["role-btn"],
                                                 visible=False)

                    # Visible role-selector UI (HTML) + two hidden Gradio buttons for click routing
                    gr.HTML("""
                    <div class="role-selector" style="margin-bottom:20px;">
                    </div>""")

                    # Actual clickable role buttons rendered inside HTML via gr.Row
                    with gr.Row(equal_height=True):
                        citizen_btn = gr.Button("👤  Citizen", elem_classes=["role-btn"])
                        admin_btn   = gr.Button("🛡️  Admin",   elem_classes=["role-btn"])

                    login_email    = gr.Textbox(label="Email Address",
                                                placeholder="your.email@example.com",
                                                elem_id="login-email")
                    login_password = gr.Textbox(label="Password", type="password",
                                                placeholder="Enter your password",
                                                elem_id="login-password")

                    gr.HTML('<div class="forgot-link"><a href="#">Forgot password?</a></div>')

                    login_btn = gr.Button("Sign In", elem_classes=["primary-btn"])

                    gr.HTML("""
                    <div class="auth-divider">or</div>
                    <div style="text-align:center;font-size:13px;color:#6B7E96;">
                        New user?
                    </div>""")

                    goto_signup_btn = gr.Button("Create Account →",
                                                elem_classes=["secondary-btn"])

                # ── SIGNUP FORM ──
                with gr.Column(visible=False) as signup_form:

                    gr.HTML("""
                    <div style="text-align:center;margin-bottom:20px;">
                        <div style="font-size:18px;font-weight:700;color:#1A2B42;">
                            Create Account
                        </div>
                        <div style="font-size:13px;color:#6B7E96;margin-top:4px;">
                            Join CivicAI and start reporting issues
                        </div>
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

                    gr.HTML('<div class="auth-divider">or</div>')
                    goto_login_btn = gr.Button("← Back to Sign In",
                                               elem_classes=["secondary-btn"])

                auth_status = gr.HTML()

            # ── Sign-out button (always accessible in Auth tab) ──
            with gr.Row():
                with gr.Column():
                    gr.HTML('<div style="height:16px;"></div>')
                    signout_btn = gr.Button("Sign Out", elem_classes=["signout-btn"])

    # ════════════════════════════════════════════════════════
    # TAB 2 — Citizen Dashboard  (hidden until citizen logs in)
    # ════════════════════════════════════════════════════════
    with gr.Tab("👥 Citizen Dashboard", visible=False) as citizen_tab:

        gr.HTML("""
        <div class="stat-strip">
            <div class="stat-card" style="background:linear-gradient(135deg,#1A3F6F,#1E90D4);">
                <div class="stat-lbl">TOTAL REPORTED</div>
                <div class="stat-val">7</div>
            </div>
            <div class="stat-card" style="background:linear-gradient(135deg,#0D7A6F,#0EA5E9);">
                <div class="stat-lbl">RESOLVED</div>
                <div class="stat-val">4</div>
            </div>
            <div class="stat-card" style="background:linear-gradient(135deg,#F59E0B,#EF4444);">
                <div class="stat-lbl">IN PROGRESS</div>
                <div class="stat-val">2</div>
            </div>
            <div class="stat-card" style="background:linear-gradient(135deg,#8B5CF6,#EC4899);">
                <div class="stat-lbl">PENDING</div>
                <div class="stat-val">1</div>
            </div>
        </div>""")

        with gr.Row():
            with gr.Column(scale=1):
                image_in = gr.Image(type="filepath", label="📷 Upload Issue Image")
                user_msg = gr.Textbox(
                    label="📝 Additional Notes (Optional)",
                    placeholder="Location, severity, or any other details...",
                    lines=3
                )
                submit_btn = gr.Button("⚡ Analyse & Submit", elem_classes=["success-btn"])

            with gr.Column(scale=1):
                gr.HTML("""
                <div style="font-size:14px;font-weight:700;color:#1A2B42;margin-bottom:8px;">
                    🤖 AI Analysis Result
                </div>""")
                ai_out_html = gr.HTML("""
                <div style="background:#F0F4F8;border:2px dashed #D8E3EE;border-radius:12px;
                     padding:40px;text-align:center;color:#6B7E96;font-size:14px;">
                    Upload an image and click <b>Analyse</b> to see the AI-generated
                    complaint details here.
                </div>""")
                uploaded_img_display = gr.Image(
                    label="📷 Uploaded Image Preview",
                    elem_classes=["image-display-card"],
                    interactive=False
                )

    # ════════════════════════════════════════════════════════
    # TAB 3 — Admin Dashboard  (hidden until admin logs in)
    # ════════════════════════════════════════════════════════
    with gr.Tab("🛡️ Admin Dashboard", visible=False) as admin_tab:

        gr.HTML("""
        <div style="display:flex;justify-content:space-between;align-items:center;
             margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #D8E3EE;">
            <div>
                <div style="font-size:18px;font-weight:700;color:#1A2B42;letter-spacing:-0.3px;">
                    All Complaints
                </div>
                <div style="font-size:13px;color:#6B7E96;margin-top:2px;">
                    Review and manage departmental complaints across the city
                </div>
            </div>
        </div>""")

        admin_view_btn = gr.Button("🔄 Refresh Complaints", elem_classes=["primary-btn"])

        admin_container = gr.HTML("""
        <div style="background:#F0F4F8;border:2px dashed #D8E3EE;border-radius:12px;
             padding:40px;text-align:center;color:#6B7E96;font-size:14px;">
            Click <b>Refresh Complaints</b> to load data.
        </div>""")

        gr.HTML("""
        <div style="margin-top:28px;padding:14px 18px;
             background:linear-gradient(135deg,#0B1F3A,#1A3F6F);
             border-radius:12px;color:white;font-weight:700;font-size:14px;">
            📸 Complaint Images Gallery
        </div>""")

        admin_gallery = gr.Gallery(
            label="All Complaint Images",
            show_label=False,
            columns=4, rows=2,
            object_fit="contain",
            height="auto"
        )

    # ════════════════════════════════════════════════════════
    # WIRING
    # ════════════════════════════════════════════════════════

    # Role selection (login form)
    citizen_btn.click(
        select_citizen_role,
        inputs=[],
        outputs=[selected_role_state, role_display]
    )
    admin_btn.click(
        select_admin_role,
        inputs=[],
        outputs=[selected_role_state, role_display]
    )

    # Role selection (signup form)
    signup_citizen_btn.click(
        select_citizen_role,
        inputs=[],
        outputs=[selected_role_state, signup_role_display]
    )
    signup_admin_btn.click(
        select_admin_role,
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

    # Login
    login_btn.click(
        login,
        inputs=[login_email, login_password, selected_role_state, current_user_state],
        outputs=[
            auth_status,
            current_user_state,
            header_display,
            auth_content,
            citizen_tab,
            admin_tab,
        ]
    )

    # Signup
    signup_btn.click(
        signup,
        inputs=[signup_email, signup_password, selected_role_state, current_user_state],
        outputs=[auth_status, current_user_state, signup_form, login_form]
    )

    # Signout
    signout_btn.click(
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

    # Citizen complaint submission
    submit_btn.click(
        process_complaint,
        inputs=[image_in, user_msg, current_user_state],
        outputs=[ai_out_html, uploaded_img_display]
    )

    # Admin refresh
    admin_view_btn.click(
        get_admin_complaints_html,
        inputs=[current_user_state],
        outputs=[admin_container, admin_gallery]
    )


demo.launch(debug=True, favicon_path=None, share=False)