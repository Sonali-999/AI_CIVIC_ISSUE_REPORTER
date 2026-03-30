import os
import gradio as gr
from dotenv import load_dotenv
import shutil
import tempfile

from .auth import register_user_wrapper, login_user_wrapper
from .db_utils import (
    save_complaint, get_complaints_by_department, get_all_complaints,
    update_complaint_status, get_notifications, get_unread_count,
    mark_all_notifications_read, STATUS_LABELS, get_user_complaint_stats,
    get_complaints_by_user, get_all_departments,
    # ── NEW ──
    get_complaints_by_district, get_all_districts,
)
from .admin_signature import (
    generate_admin_keypair,
    create_login_challenge,
    sign_challenge,
    verify_admin_signature,
)
from .image_processor import encode_image
from .ai_service import analyze_image_with_query
from .image_encryption import encrypt_image, decrypt_image
from .security_audit import log_security_event
from .jwt_tokens import create_token, verify_token, token_required

# ── NEW: location service ──────────────────────────────────────────────────
from .location_service import (
    get_location_from_image_or_coords,
    is_in_chennai_district,
    CHENNAI_DISTRICT_NAMES,
)

load_dotenv()

import hashlib
from datetime import datetime

ALLOWED_ADMIN_EMAILS = {
    "admin@gmail.com",
    "munic@gov.in",
}

admin_otp_store = {}

# ─────────────────────────────────────────────────────────────────────────────
# System prompt (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
system_prompt = (
    "You are an AI civic issue detector. Analyze the uploaded image, identify the type of problem "
    "(e.g., garbage, pothole, dead animal, broken streetlight, sewage), determine the relevant municipal department "
    "(Sanitation, Roads, Electricity, etc.), generate a short title and description including impact on public "
    "hygiene, safety, and environment. Output should be concise and ready to autofill the complaint form."
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS  (original preserved, new classes added at bottom)
# ─────────────────────────────────────────────────────────────────────────────
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

/* location button */
.location-btn button, button.location-btn {
    background: linear-gradient(135deg, #0D7A6F, #1E90D4) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important;
    font-size: 14px !important; font-weight: 700 !important;
    transition: all 0.2s !important;
    box-shadow: 0 3px 10px rgba(13,122,111,0.25) !important;
}
.location-btn button:hover, button.location-btn:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 5px 16px rgba(13,122,111,0.35) !important;
}

/* analyse-only button */
.analyse-btn button, button.analyse-btn {
    background: linear-gradient(135deg, #8B5CF6, #EC4899) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important;
    font-size: 14px !important; font-weight: 700 !important;
    transition: all 0.2s !important;
    box-shadow: 0 3px 10px rgba(139,92,246,0.25) !important;
}
.analyse-btn button:hover, button.analyse-btn:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 5px 16px rgba(139,92,246,0.4) !important;
}

.auth-divider {
    display: flex; align-items: center; gap: 12px;
    margin: 20px 0; color: var(--muted); font-size: 12px;
}
.auth-divider::before, .auth-divider::after {
    content: ''; flex: 1; height: 1px; background: var(--border);
}

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

.section-title {
    font-size: 15px !important; font-weight: 700 !important;
    color: var(--text) !important;
    margin-bottom: 16px !important; padding-bottom: 12px !important;
    border-bottom: 2px solid var(--border) !important;
}

.forgot-link {
    text-align: right; margin-top: -8px; margin-bottom: 16px;
    font-size: 12px;
}
.forgot-link a {
    color: var(--teal); font-weight: 600; text-decoration: none;
}
.forgot-link a:hover { text-decoration: underline; }

#admin-gallery {
    height: auto !important;
    max-height: none !important;
    overflow: visible !important;
}
#admin-gallery svg[data-testid="chevron-up"],
#admin-gallery svg[data-testid="chevron-down"] {
    display: none !important;
}
#admin-gallery .grid-wrap {
    display: grid !important;
    grid-template-columns: repeat(3, 1fr) !important;
}

/* ── location strip ── */
.location-strip {
    background: linear-gradient(135deg,rgba(13,122,111,0.06),rgba(30,144,212,0.06));
    border: 1.5px solid rgba(13,122,111,0.2);
    border-radius: 12px; padding: 14px 18px;
    margin-bottom: 14px;
}
.location-strip-label {
    font-size: 11px; font-weight: 700; color: var(--teal);
    text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;
}
.location-strip-value {
    font-size: 13px; color: var(--text); font-weight: 500;
}

/* ── update btn ── */
.update-btn button, button.update-btn {
    background: linear-gradient(135deg, var(--teal), var(--tealL)) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important; font-weight: 700 !important;
    font-size: 14px !important; transition: all 0.2s !important;
    box-shadow: 0 3px 10px rgba(13,122,111,0.25) !important;
}
.update-btn button:hover, button.update-btn:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 5px 16px rgba(13,122,111,0.4) !important;
}

/* ── status select ── */
.status-select select {
    border: 1.5px solid var(--border) !important;
    border-radius: 10px !important;
    padding: 10px 14px !important;
}

/* ── notifications ── */
.notif-panel {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    box-shadow: var(--shadow-md);
    overflow: hidden;
    margin-top: 8px;
}
.notif-panel-header {
    background: linear-gradient(135deg, var(--navy), var(--blue));
    color: white; padding: 14px 18px;
    font-size: 14px; font-weight: 700;
    display: flex; align-items: center; justify-content: space-between;
}
.notif-item {
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
}
.notif-item.unread { background: rgba(13,122,111,0.04); }
.notif-item-title  { font-size: 13px; font-weight: 700; color: var(--text); }
.notif-item-body   { font-size: 12px; color: var(--muted); margin-top: 4px; }
.notif-item-time   { font-size: 11px; color: var(--muted); margin-top: 6px; }
.notif-empty { padding: 28px 18px; text-align: center; color: var(--muted); font-size: 13px; }
.badge-pill {
    background: var(--danger); color: white;
    border-radius: 20px; padding: 2px 7px;
    font-size: 11px; font-weight: 700;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# Small helpers (unchanged from original)
# ─────────────────────────────────────────────────────────────────────────────

def _make_header(email=None, role=None):
    if not email:
        return """
        <div id="civicai-header">
          <div id="civicai-header-inner">
            <div class="hdr-logo">
              <div class="hdr-logo-icon">🏛️</div>
              <div>
                <div class="hdr-logo-name">CivicAI</div>
                <div class="hdr-logo-sub">Smart Civic Issue Platform</div>
              </div>
            </div>
          </div>
        </div>"""
    initials = email[:2].upper()
    role_badge = "🛡️ Admin" if role == "admin" else "👤 Citizen"
    return f"""
    <div id="civicai-header">
      <div id="civicai-header-inner">
        <div class="hdr-logo">
          <div class="hdr-logo-icon">🏛️</div>
          <div>
            <div class="hdr-logo-name">CivicAI</div>
            <div class="hdr-logo-sub">Smart Civic Issue Platform</div>
          </div>
        </div>
        <div class="hdr-user">
          <div class="hdr-avatar">{initials}</div>
          {email} &nbsp;·&nbsp; {role_badge}
        </div>
      </div>
    </div>"""


def _role_selector_html(active):
    c_cls = "role-btn active-citizen" if active == "citizen" else "role-btn"
    a_cls = "role-btn active-admin"   if active == "admin"   else "role-btn"
    return f"""
    <div class="role-selector">
      <div class="{c_cls}"><div class="role-icon">👤</div>Citizen</div>
      <div class="{a_cls}"><div class="role-icon">🛡️</div>Admin</div>
    </div>"""


def select_citizen_role():
    return (
        "citizen",
        _role_selector_html("citizen"),
        gr.update(visible=True),
        gr.update(visible=False),
    )


def select_admin_role():
    return (
        "admin",
        _role_selector_html("admin"),
        gr.update(visible=False),
        gr.update(visible=True),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Auth helpers (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def request_admin_otp(email, password):
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
    if not email or not password:
        return (
            '<div class="status-error">❌ Please fill in all fields.</div>',
            state, gr.update(visible=True), gr.update(visible=False),
        )
    if role == "admin" and email.strip().lower() not in ALLOWED_ADMIN_EMAILS:
        return (
            '<div class="status-error">❌ This email is not authorized for admin registration.</div>',
            state, gr.update(visible=True), gr.update(visible=False),
        )
    result = register_user_wrapper(email, password, role)
    if "success" in result.get("status", "").lower():
        return (
            f'<div class="status-success">✨ {result["status"]} — Now please sign in!</div>',
            state, gr.update(visible=False), gr.update(visible=True),
        )
    else:
        return (
            f'<div class="status-error">❌ {result.get("status","Error")}</div>',
            state, gr.update(visible=True), gr.update(visible=False),
        )


def login(email, password, role, state, admin_otp=""):
    result = login_user_wrapper(email, password)

    if result.get("status") == "success" and result.get("role") == "admin":
        expected_otp = admin_otp_store.get(email)
        if not expected_otp:
            return (
                '<div class="status-error">❌ Please click <b>Get OTP</b> first, then enter the code.</div>',
                state, _make_header(), gr.update(visible=True),
                gr.update(visible=False), gr.update(visible=False),
                gr.update(), [], "", "", "",
            )
        if admin_otp.strip() != expected_otp:
            del admin_otp_store[email]
            return (
                '<div class="status-error">❌ Invalid OTP. Click <b>Get OTP</b> again.</div>',
                state, _make_header(), gr.update(visible=True),
                gr.update(visible=False), gr.update(visible=False),
                gr.update(), [], "", "", "",
            )
        del admin_otp_store[email]
        print(f"[✅] Admin {email} passed OTP verification.")

    if result.get("status") == "success":
        actual_role = result.get("role", role)
        log_security_event("LOGIN_SUCCESS", f"user={email}, role={actual_role}")
        state["uid"]   = result["user_id"]
        state["email"] = email
        state["role"]  = actual_role

        token = create_token(result["user_id"], email, actual_role)
        state["token"] = token

        is_citizen = (actual_role == "citizen")
        is_admin   = (actual_role == "admin")

        stats_html   = generate_user_stats(state) if is_citizen else ""
        history_html = generate_user_complaints_html(state) if is_citizen else ""

        admin_html, admin_images = (
            get_admin_complaints_html(state) if is_admin
            else ("""<div style="background:#F0F4F8;border:2px dashed #D8E3EE;border-radius:12px;
                 padding:40px;text-align:center;color:#6B7E96;font-size:14px;">
                 Click <b>Refresh Complaints</b> to load data.</div>""", [])
        )

        bell_html = build_notification_bell_html(state["uid"]) if is_citizen else ""

        return (
            f'<div class="status-success">✅ Welcome back, {email}!</div>',
            state,
            _make_header(email, actual_role),
            gr.update(visible=False),
            gr.update(visible=is_citizen),
            gr.update(visible=is_admin),
            admin_html, admin_images,
            stats_html, history_html, bell_html,
        )
    else:
        log_security_event("LOGIN_FAILED", f"user={email}")
        state["uid"] = state["email"] = state["role"] = None
        return (
            '<div class="status-error">❌ Invalid credentials. Please try again.</div>',
            state, _make_header(), gr.update(visible=True),
            gr.update(visible=False), gr.update(visible=False),
            gr.update(), [], "", "", "",
        )


def signout(state):
    state["uid"] = state["email"] = state["role"] = state["token"] = None
    return (
        '<div class="status-success">✅ Successfully signed out!</div>',
        state, _make_header(),
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False),
    )


def show_signup(): return gr.update(visible=False), gr.update(visible=True)
def show_login():  return gr.update(visible=True),  gr.update(visible=False)


def generate_admin_otp(email: str) -> str:
    challenge = create_login_challenge(email)
    safe      = email.replace("@", "_at_").replace(".", "_")
    priv_path = f"keys/admin_{safe}_private.pem"
    try:
        signature = sign_challenge(challenge, priv_path)
        otp = str(int(hashlib.sha256(signature.encode()).hexdigest(), 16))[-6:]
        admin_otp_store[email] = otp
        print(f"\n{'='*40}\n  🔐 ADMIN OTP FOR {email}\n  Code: {otp}\n{'='*40}\n")
        return otp
    except FileNotFoundError:
        print(f"[WARN] No private key found for {email}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# AI complaint processing  — SPLIT into Analyze + Submit
# ─────────────────────────────────────────────────────────────────────────────

def parse_ai_output(ai_output):
    title = category = department = description = "N/A"
    try:
        for line in ai_output.split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if "title"        in key: title       = value
            elif "category"   in key: category    = value
            elif "department" in key: department  = value
            elif "description"in key: description = value
    except Exception as e:
        print("Error parsing AI output:", e)
    return title, category, department, description


CATEGORY_CHOICES = [
    "Garbage", "Streetlight", "Dead Animal", "Sewage",
    "Pothole", "Waterlogging", "Noise", "Other",
]

DEPARTMENT_CHOICES = [
    "Sanitation", "Roads", "Electricity", "Water",
    "Public Health", "Parks", "Other",
]


def analyze_image_only(image_path, user_msg, state):
    """
    Step 1 — Only run AI analysis; return editable field values.
    Does NOT save to DB.
    """
    try:
        token_required(state.get("token"), required_role="citizen")
    except ValueError as e:
        return (
            f'<div class="status-error">❌ {e}</div>',
            gr.update(), gr.update(), gr.update(), gr.update(),
        )

    if not image_path:
        return (
            '<div class="status-error">❌ Please upload an image first.</div>',
            gr.update(), gr.update(), gr.update(), gr.update(),
        )

    try:
        ai_output = analyze_image_with_query(
            query_text=f"{system_prompt} {user_msg}",
            encoded_image=encode_image(image_path),
            model="meta-llama/llama-4-scout-17b-16e-instruct",
        )
        title, category, department, description = parse_ai_output(ai_output)

        status_html = """
        <div style="padding:10px 14px;background:rgba(139,92,246,0.08);border:1.5px solid rgba(139,92,246,0.25);
             border-radius:10px;color:#7C3AED;font-weight:700;font-size:13px;">
             🤖 AI analysis complete — review and edit the fields below, then click <b>Submit Complaint</b>.
        </div>"""

        return (
            status_html,
            gr.update(value=title),
            gr.update(value=category   if category   in CATEGORY_CHOICES   else "Other"),
            gr.update(value=department if department in DEPARTMENT_CHOICES else "Other"),
            gr.update(value=description),
        )
    except Exception as e:
        return (
            f'<div class="status-error">❌ AI analysis failed: {str(e)}</div>',
            gr.update(), gr.update(), gr.update(), gr.update(),
        )


def submit_complaint_final(
    image_path, user_msg,
    title, category, department, description,
    lat_str, lon_str, address, district,
    state,
):
    """
    Step 2 — Save complaint (with editable AI fields + location data).
    """
    try:
        payload = token_required(state.get("token"), required_role="citizen")
    except ValueError as e:
        return f'<div class="status-error">❌ {e}</div>', ""

    uid = payload["sub"]

    if not image_path:
        return '<div class="status-error">❌ Please upload an image.</div>', ""
    if not title or title == "N/A":
        return '<div class="status-error">❌ Please run AI analysis first (or fill in the Title).</div>', ""

    # Parse coords from hidden textboxes (populated by JS geolocation)
    lat = lon = None
    try:
        if lat_str: lat = float(lat_str)
        if lon_str: lon = float(lon_str)
    except ValueError:
        pass

    # If browser coords not available, try EXIF; also reverse-geocode if needed
    if lat is None or not address:
        loc = get_location_from_image_or_coords(image_path, lat, lon)
        lat     = loc.get("latitude")  or lat
        lon     = loc.get("longitude") or lon
        address = address or loc.get("address", "")
        district= district or loc.get("district", "")

    try:
        os.makedirs("uploads", exist_ok=True)
        filename   = os.path.basename(image_path)
        saved_path = os.path.join("uploads", filename)
        shutil.copy2(image_path, saved_path)

        enc_path = encrypt_image(saved_path)
        os.remove(saved_path)

        save_complaint(
            user_id    = uid,
            title      = title,
            category   = category,
            department = department,
            description= description,
            image_path = enc_path,
            latitude   = lat,
            longitude  = lon,
            address    = address,
            district   = district,
        )

        dept_icons = {"Sanitation": "🗑️", "Roads": "🛣️", "Electricity": "⚡", "Water": "💧"}
        icon = dept_icons.get(department, "🏢")

        loc_html = ""
        if lat and lon:
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            loc_html = f"""
            <div class="info-badge" style="margin-top:10px;">
                <div class="info-badge-label">📍 Location</div>
                <div style="font-size:13px;color:#6B7E96;margin-top:4px;">
                    {address or f"{lat:.5f}, {lon:.5f}"}
                    {"&nbsp;·&nbsp; <b>" + district + "</b>" if district else ""}
                    &nbsp;<a href="{maps_url}" target="_blank"
                       style="color:#0D7A6F;font-weight:700;font-size:12px;">🗺 View Map</a>
                </div>
            </div>"""

        html_content = f"""
        <div class="complaint-card">
            <div class="complaint-card-header">⚡ Complaint Registered Successfully</div>
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
                {loc_html}
                <div style="text-align:center;margin-top:14px;padding:12px;
                     background:rgba(13,122,111,0.07);border-radius:10px;
                     color:#0D7A6F;font-weight:700;font-size:13px;">
                    ✅ Complaint submitted! We'll process it shortly.
                </div>
            </div>
        </div>"""

        stats_html = generate_user_stats({"uid": uid})
        return html_content, stats_html

    except Exception as e:
        return f'<div class="status-error">❌ Error: {str(e)}</div>', ""


# ── Location capture helper called by JS ──────────────────────────────────────

def handle_location_capture(lat_str, lon_str):
    """
    Called when JS pushes browser geolocation into hidden Gradio textboxes.
    Reverse-geocodes and returns display-ready values.
    """
    try:
        lat = float(lat_str)
        lon = float(lon_str)
    except (TypeError, ValueError):
        return "", "", '<div class="status-error">❌ Could not read coordinates.</div>'

    loc = get_location_from_image_or_coords(None, lat, lon)
    address  = loc.get("address", "")
    district = loc.get("district", "")

    display = f"""
    <div class="location-strip">
        <div class="location-strip-label">📍 Location Captured</div>
        <div class="location-strip-value">{address or f"{lat:.5f}, {lon:.5f}"}</div>
        {"<div style='font-size:12px;color:#0D7A6F;font-weight:600;margin-top:4px;'>District: " + district + "</div>" if district else ""}
    </div>"""

    return address, district, display


# ─────────────────────────────────────────────────────────────────────────────
# Stat / history helpers (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def generate_user_stats(state):
    if not state.get("uid"):
        return ""
    stats = get_user_complaint_stats(state["uid"])
    return f"""
    <div class="stat-strip">
        <div class="stat-card" style="background:linear-gradient(135deg,#1A3F6F,#1E90D4);">
            <div class="stat-lbl">TOTAL REPORTED</div>
            <div class="stat-val">{stats["total"]}</div>
        </div>
        <div class="stat-card" style="background:linear-gradient(135deg,#0D7A6F,#0EA5E9);">
            <div class="stat-lbl">RESOLVED</div>
            <div class="stat-val">{stats["resolved"]}</div>
        </div>
        <div class="stat-card" style="background:linear-gradient(135deg,#F59E0B,#EF4444);">
            <div class="stat-lbl">IN PROGRESS</div>
            <div class="stat-val">{stats["in_progress"]}</div>
        </div>
        <div class="stat-card" style="background:linear-gradient(135deg,#8B5CF6,#EC4899);">
            <div class="stat-lbl">PENDING</div>
            <div class="stat-val">{stats["pending"]}</div>
        </div>
    </div>"""


def generate_user_complaints_html(state):
    if not state.get("uid"):
        return ""
    complaints = get_complaints_by_user(state["uid"])
    if not complaints:
        return '<div style="text-align:center;padding:30px;color:#6B7E96;">No complaints submitted yet.</div>'

    html = ""
    for c in complaints:
        status = c.get("status", "pending")
        color  = {"resolved": "#10B981", "in_progress": "#F59E0B", "pending": "#EF4444", "rejected": "#6B7E96"}.get(status, "#6B7E96")
        lat    = c.get("latitude")
        lon    = c.get("longitude")
        loc_tag = ""
        if lat and lon:
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            loc_tag  = f'<a href="{maps_url}" target="_blank" style="font-size:11px;color:#0D7A6F;font-weight:600;">🗺 Map</a>'

        html += f"""
        <div class="admin-card">
            <div style="font-size:15px;font-weight:700;color:#1A2B42;">{c.get("title")}</div>
            <div style="font-size:13px;color:#6B7E96;margin-top:4px;">{c.get("description")}</div>
            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;font-size:12px;">
                <span style="background:#E0F2FE;color:#0369A1;padding:5px 10px;border-radius:20px;font-weight:600;">
                    🏢 {c.get("department")}
                </span>
                <span style="background:#F5F3FF;color:#6D28D9;padding:5px 10px;border-radius:20px;font-weight:600;">
                    🏷 {c.get("category")}
                </span>
                <span style="background:{color}20;color:{color};padding:5px 10px;border-radius:20px;font-weight:600;">
                    Status: {status.replace("_"," ").title()}
                </span>
                {loc_tag}
            </div>
        </div>"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
# Notification helpers (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def _time_ago(dt) -> str:
    if not dt:
        return ""
    try:
        diff = datetime.utcnow() - dt
        s = int(diff.total_seconds())
        if s < 60:    return "just now"
        if s < 3600:  return f"{s//60}m ago"
        if s < 86400: return f"{s//3600}h ago"
        return f"{s//86400}d ago"
    except Exception:
        return ""


def build_notification_bell_html(user_id: str) -> str:
    count = get_unread_count(user_id) if user_id else 0
    badge = f'<span class="badge-pill">{count}</span>' if count > 0 else ""
    return f"""
    <div style="display:inline-flex;align-items:center;gap:6px;">
        <span style="font-size:20px;cursor:pointer;" title="Notifications">🔔</span>
        {badge}
    </div>"""


def build_notifications_panel_html(user_id: str) -> str:
    if not user_id:
        return ""
    notifs = get_notifications(user_id)
    mark_all_notifications_read(user_id)
    if not notifs:
        return """
        <div class="notif-panel">
            <div class="notif-panel-header">🔔 Notifications</div>
            <div class="notif-empty">No notifications yet.<br>
            <span style="font-size:12px;">You'll be notified when your complaint status changes.</span>
            </div>
        </div>"""

    items_html = ""
    for n in notifs:
        old_lbl = STATUS_LABELS.get(n.get("old_status",""), n.get("old_status",""))
        new_lbl = STATUS_LABELS.get(n.get("new_status",""), n.get("new_status",""))
        unread_cls = "" if n.get("read") else " unread"
        items_html += f"""
        <div class="notif-item{unread_cls}">
            <div class="notif-item-title">📋 {n.get("title","Complaint Update")}</div>
            <div class="notif-item-body">Status changed: <b>{old_lbl}</b> → <b>{new_lbl}</b></div>
            <div class="notif-item-time">{_time_ago(n.get("created_at"))}</div>
        </div>"""

    return f"""
    <div class="notif-panel">
        <div class="notif-panel-header">
            🔔 Notifications
            <span style="font-size:12px;font-weight:400;opacity:0.75;">{len(notifs)} total</span>
        </div>
        {items_html}
    </div>"""


def handle_bell_click(state):
    uid   = state.get("uid") if state else None
    panel = build_notifications_panel_html(uid)
    bell  = build_notification_bell_html(uid)
    return panel, bell


# ─────────────────────────────────────────────────────────────────────────────
# Admin handlers
# ─────────────────────────────────────────────────────────────────────────────

def handle_status_update(complaint_id: str, new_status: str, state: dict):
    try:
        token_required(state.get("token"), required_role="admin")
    except ValueError as e:
        return f'<div class="status-error">❌ Access denied: {e}</div>'

    if state.get("role") != "admin":
        return '<div class="status-error">🚫 Admin access required.</div>'
    if not complaint_id or not new_status:
        return '<div class="status-error">❌ Please select a complaint and a status.</div>'

    result = update_complaint_status(complaint_id.strip(), new_status)
    if result.get("status") == "success":
        label = STATUS_LABELS.get(new_status, new_status)
        return f'<div class="status-success">✅ Complaint updated to {label} — citizen notified!</div>'
    return f'<div class="status-error">❌ {result.get("error","Update failed.")}</div>'


def _render_complaint_card(row) -> tuple[str, str | None]:
    """
    Render a single admin complaint card.
    Returns (html_fragment, decrypted_image_path_or_None).
    """
    dept_icons    = {"Sanitation": "🗑️", "Roads": "🛣️", "Electricity": "⚡", "Water": "💧"}
    status_colors = {
        "resolved":    "#10B981",
        "in_progress": "#F59E0B",
        "pending":     "#EF4444",
        "rejected":    "#6B7E96",
    }

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
    lat         = row.get("latitude")
    lon         = row.get("longitude")
    address     = row.get("address", "")
    district    = row.get("district", "")

    status_color = status_colors.get(status.lower(), "#6B7E96")

    # Decrypt image for gallery
    img_path_out = None
    img_idx_label = ""
    if image_path and os.path.exists(image_path):
        if image_path.endswith(".enc"):
            try:
                raw_bytes = decrypt_image(image_path)
                base      = image_path.replace(".enc", "")
                suffix    = os.path.splitext(base)[1] or ".jpg"
                tmp       = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(raw_bytes)
                tmp.close()
                img_path_out = tmp.name
            except Exception as e:
                print(f"[gallery] Could not decrypt {image_path}: {e}")
        else:
            img_path_out = image_path

    # Location section
    location_html = ""
    if lat and lon:
        maps_url = f"https://www.google.com/maps?q={lat},{lon}"
        map_iframe = (
            f'<iframe width="100%" height="160" frameborder="0" style="border-radius:8px;margin-top:8px;" '
            f'src="https://maps.google.com/maps?q={lat},{lon}&z=15&output=embed" '
            f'allowfullscreen loading="lazy"></iframe>'
        )
        district_badge = (
            f'<span style="background:#E0F2FE;color:#0369A1;padding:3px 10px;border-radius:20px;'
            f'font-size:11px;font-weight:600;">🏙️ {district}</span>'
            if district else ""
        )
        location_html = f"""
        <div style="margin-top:10px;padding:12px;background:rgba(13,122,111,0.05);
             border:1.5px solid rgba(13,122,111,0.18);border-radius:10px;">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
                <span style="font-size:12px;font-weight:700;color:#0D7A6F;">📍 Location</span>
                {district_badge}
                <a href="{maps_url}" target="_blank"
                   style="font-size:11.5px;font-weight:700;color:#0D7A6F;text-decoration:none;
                          background:#e8f4f3;padding:3px 10px;border-radius:20px;">
                    🗺 Open in Google Maps
                </a>
            </div>
            <div style="font-size:12px;color:#6B7E96;">{address or f"{lat:.5f}, {lon:.5f}"}</div>
            {map_iframe}
        </div>"""

    tamper_html = (
        '<div style="background:#EF444420;border:2px solid #EF4444;border-radius:8px;'
        'padding:8px 14px;margin-top:8px;color:#EF4444;font-weight:700;font-size:13px;">'
        '⚠️ TAMPERED — This complaint was modified directly in the database!</div>'
        if tampered else ""
    )

    card_html = f"""
    <div class="admin-card" id="card-{row_id}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">
            <div>
                <div style="font-size:11px;color:#6B7E96;font-weight:600;font-family:monospace;margin-bottom:4px;">
                    ID: {row_id}
                </div>
                <div style="font-size:15px;font-weight:700;color:#1A2B42;">{title}</div>
                <div style="font-size:12px;color:#6B7E96;margin-top:2px;">Category: {category}</div>
            </div>
            <span style="display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
                  border-radius:20px;font-size:11.5px;font-weight:600;
                  background:{status_color}1a;color:{status_color};">
                ● {status.replace("_"," ").title()}
            </span>
        </div>
        <div class="info-badge">
            <div class="info-badge-label">📝 Description</div>
            <div style="font-size:13px;color:#6B7E96;line-height:1.6;margin-top:4px;">{description}</div>
        </div>
        <div class="admin-meta-grid">
            <div class="admin-meta-box">
                <div class="admin-meta-lbl">Status</div>
                <div class="admin-meta-val" style="color:{status_color};">{status.replace("_"," ").title()}</div>
            </div>
            <div class="admin-meta-box">
                <div class="admin-meta-lbl">Department</div>
                <div class="admin-meta-val">{department}</div>
            </div>
            <div class="admin-meta-box">
                <div class="admin-meta-lbl">User</div>
                <div class="admin-meta-val" style="font-size:10px;">#{user_id[:8]}…</div>
            </div>
            <div class="admin-meta-box">
                <div class="admin-meta-lbl">Time</div>
                <div class="admin-meta-val" style="font-size:11px;">{timestamp}</div>
            </div>
        </div>
        {location_html}
        <div style="margin-top:12px;padding:10px 14px;background:rgba(13,122,111,0.05);
             border-radius:8px;border:1px solid rgba(13,122,111,0.15);
             display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
            <span style="font-size:12px;font-weight:600;color:#0D7A6F;">🔧 Quick actions:</span>
            <code style="font-size:11px;background:#e8f4f3;padding:2px 8px;border-radius:6px;
                  color:#0B1F3A;font-weight:700;">{row_id}</code>
            <span style="font-size:11px;color:#6B7E96;">← paste ID below to update status</span>
            {"" if status == "rejected" else f'''
            <span style="margin-left:auto;">
                <a onclick="
                    const box = document.querySelector(\'#status-complaint-id textarea, #status-complaint-id input\');
                    if(box){{box.value=\'{row_id}\';box.dispatchEvent(new Event(\'input\',{{bubbles:true}}));}}
                    const dd = document.querySelectorAll(\'.status-select select\');
                    dd.forEach(s=>{{s.value=\'rejected\';s.dispatchEvent(new Event(\'change\',{{bubbles:true}}));}});
                " style="cursor:pointer;font-size:11.5px;font-weight:700;color:#EF4444;
                         background:#FEF2F2;padding:4px 12px;border-radius:20px;
                         border:1px solid #FECACA;text-decoration:none;display:inline-block;">
                    ❌ Reject
                </a>
            </span>'''}
        </div>
        {tamper_html}
    </div>"""

    return card_html, img_path_out


def get_admin_complaints_html(state, district_filter: str = "All Cities"):
    try:
        token_required(state.get("token"), required_role="admin")
    except ValueError as e:
        return f'<div class="status-error">❌ {e}</div>', []

    if state.get("role") != "admin":
        return '<div class="status-error">🚫 Admin access required.</div>', []

    departments  = get_all_departments()
    html_content = '<div style="animation:fadeUp 0.4s ease;">'
    image_paths  = []

    filtering = district_filter and district_filter != "All Cities"

    for dept in departments:
        rows = get_complaints_by_department(dept)
        if not rows:
            continue

        if filtering:
            # ── Coordinate-based filter: keep only complaints whose
            #    (lat, lon) falls inside the selected district's bounding box
            filtered = []
            for r in rows:
                lat = r.get("latitude")
                lon = r.get("longitude")
                if lat is not None and lon is not None:
                    if is_in_chennai_district(lat, lon, district_filter):
                        filtered.append(r)
                # Complaints with no coords are hidden when a district is selected
            rows = filtered

        if not rows:
            continue

        # Sort by latitude (north → south) within each dept; no-coord complaints last
        rows.sort(key=lambda r: (r.get("latitude") is None, r.get("latitude") or 0))

        dept_icon = {"Sanitation": "🗑️", "Roads": "🛣️", "Electricity": "⚡", "Water": "💧"}.get(dept, "🏢")
        html_content += f'<div class="dept-header">{dept_icon} {dept.upper()} DEPARTMENT</div>'

        for row in rows:
            card_html, img_path = _render_complaint_card(row)
            html_content += card_html
            if img_path:
                image_paths.append(img_path)

    if html_content == '<div style="animation:fadeUp 0.4s ease;">':
        msg = (
            f"📍 No complaints with coordinates in <b>{district_filter}</b>."
            if filtering else
            "📝 No complaints found."
        )
        html_content += f'<div style="text-align:center;padding:48px 24px;color:#6B7E96;font-size:15px;">{msg}</div>'

    html_content += "</div>"
    return html_content, image_paths


def get_admin_complaints_filtered(district_filter: str, state):
    """Wrapper for district-filter dropdown."""
    return get_admin_complaints_html(state, district_filter)


# ─────────────────────────────────────────────────────────────────────────────
# BUILD GRADIO APP
# ─────────────────────────────────────────────────────────────────────────────

# JavaScript injected into the page to capture browser geolocation
_GEOLOCATION_JS = """
async () => {
    const btn = document.getElementById("geo-capture-btn");
    const statusEl = document.getElementById("geo-status-display");

    if (!navigator.geolocation) {
        if (statusEl) statusEl.innerHTML =
            '<div class="status-error">❌ Geolocation not supported by your browser.</div>';
        return [null, null];
    }

    return new Promise((resolve) => {
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const lat = pos.coords.latitude;
                const lon = pos.coords.longitude;
                // Push into Gradio hidden textboxes via their underlying <input> elements
                ["#lat-hidden input", "#lon-hidden input"].forEach((sel, i) => {
                    const el = document.querySelector(sel);
                    if (el) {
                        el.value = i === 0 ? lat : lon;
                        el.dispatchEvent(new Event("input", {bubbles: true}));
                    }
                });
                resolve([String(lat), String(lon)]);
            },
            (err) => {
                if (statusEl) statusEl.innerHTML =
                    '<div class="status-error">❌ Location denied — please enter manually below.</div>';
                resolve([null, null]);
            },
            {enableHighAccuracy: true, timeout: 8000}
        );
    });
}
"""

with gr.Blocks(title="🏛️ CivicAI — Smart Civic Issue Detection") as demo:

    header_display      = gr.HTML(_make_header())
    current_user_state  = gr.State({"uid": None, "email": None, "role": None})
    selected_role_state = gr.State("citizen")

    # ══════════════════════════════════════════════════════════
    # Auth panel
    # ══════════════════════════════════════════════════════════
    with gr.Column(visible=True) as auth_content:
        with gr.Column(elem_classes=["auth-card"], scale=1, min_width=320):

            gr.HTML("""
            <div style="text-align:center;margin-bottom:8px;">
                <div style="width:56px;height:56px;border-radius:16px;
                        background:linear-gradient(135deg,#0B1F3A,#0D7A6F);
                        display:flex;align-items:center;justify-content:center;
                        font-size:28px;margin:0 auto 14px;
                        box-shadow:0 4px 16px rgba(11,31,58,0.25);">🏛️</div>
                <div style="font-size:22px;font-weight:800;color:#1A2B42;letter-spacing:-0.5px;">Welcome</div>
                <div style="font-size:13px;color:#6B7E96;margin-top:4px;">Sign in to CivicAI Portal</div>
            </div>""")

            with gr.Column(visible=True) as login_form:
                with gr.Row(equal_height=True):
                    citizen_btn = gr.Button("  Citizen", elem_classes=["role-btn"])
                    admin_btn   = gr.Button("  Admin",   elem_classes=["role-btn"])
                role_display   = gr.HTML(_role_selector_html("citizen"))
                login_email    = gr.Textbox(label="Email Address", placeholder="your.email@example.com")
                login_password = gr.Textbox(label="Password", type="password", placeholder="Enter your password")
                gr.HTML('<div class="forgot-link"><a href="#">Forgot password?</a></div>')

                with gr.Column(visible=True) as citizen_login_panel:
                    citizen_signin_btn = gr.Button("Sign In", elem_classes=["primary-btn"])

                with gr.Column(visible=False) as admin_login_panel:
                    admin_otp_input = gr.Textbox(label="Admin OTP", placeholder="Enter 6-digit code from terminal...", max_lines=1)
                    with gr.Row(equal_height=True):
                        get_otp_btn      = gr.Button("Get OTP",  elem_classes=["secondary-btn"])
                        admin_signin_btn = gr.Button("Sign In",  elem_classes=["primary-btn"])

                gr.HTML('<div class="auth-divider">or</div><div style="text-align:center;font-size:13px;color:#6B7E96;">New user?</div>')
                goto_signup_btn = gr.Button("Create Account →", elem_classes=["secondary-btn"])

            with gr.Column(visible=False) as signup_form:
                gr.HTML("""
                <div style="text-align:center;margin-bottom:20px;">
                    <div style="font-size:18px;font-weight:700;color:#1A2B42;">Create Account</div>
                    <div style="font-size:13px;color:#6B7E96;margin-top:4px;">Join CivicAI and start reporting issues</div>
                </div>""")
                with gr.Row(equal_height=True):
                    signup_citizen_btn = gr.Button("👤  Citizen", elem_classes=["role-btn"])
                    signup_admin_btn   = gr.Button("🛡️  Admin",   elem_classes=["role-btn"])
                signup_role_display = gr.HTML(_role_selector_html("citizen"))
                signup_email    = gr.Textbox(label="Email Address", placeholder="your.email@example.com")
                signup_password = gr.Textbox(label="Password", type="password", placeholder="Create a password")
                signup_btn      = gr.Button("Create Account ✓", elem_classes=["primary-btn"])
                gr.HTML('<div class="auth-divider">or</div>')
                goto_login_btn  = gr.Button("← Back to Sign In", elem_classes=["secondary-btn"])

            auth_status = gr.HTML()

    # ══════════════════════════════════════════════════════════
    # TAB 2 — Citizen Dashboard
    # ══════════════════════════════════════════════════════════
    with gr.Tab("👥 Citizen Dashboard", visible=False) as citizen_tab:

        citizen_stats = gr.HTML()

        # Notification bell
        with gr.Row():
            with gr.Column(scale=1, min_width=60):
                notif_bell_html = gr.HTML('<div style="text-align:right;">🔔</div>', elem_id="notif-bell-area")
                bell_btn        = gr.Button("🔔 Notifications", elem_classes=["secondary-btn"], size="sm")
        notif_panel_html = gr.HTML("", visible=False, elem_id="notif-panel")

        with gr.Row():
            # ── Left column: upload + location + controls ──────────────────
            with gr.Column(scale=1):
                image_in = gr.Image(type="filepath", label="📷 Upload Issue Image")

                # ── Location capture ──
                gr.HTML("""
                <div style="font-size:13px;font-weight:700;color:#1A2B42;margin:12px 0 6px;">
                    📍 Capture Your Location
                </div>""")

                geo_btn = gr.Button("📍 Use My Location", elem_classes=["location-btn"])

                # Hidden inputs populated by JS
                lat_hidden = gr.Textbox(value="", visible=False, elem_id="lat-hidden")
                lon_hidden = gr.Textbox(value="", visible=False, elem_id="lon-hidden")

                # Visible display of captured address/district
                location_display_html = gr.HTML(
                    '<div style="color:#6B7E96;font-size:12px;margin-bottom:4px;">Location not captured yet.</div>'
                )
                address_box  = gr.Textbox(label="Address",  placeholder="Auto-filled or enter manually", lines=2)
                district_box = gr.Textbox(label="District", placeholder="Auto-filled or enter manually")

                user_msg = gr.Textbox(
                    label="Additional Notes (Optional)",
                    placeholder="Any extra details about the issue…",
                    lines=3,
                )

                analyse_btn = gr.Button("🤖 Analyze Image", elem_classes=["analyse-btn"])

            # ── Right column: editable AI output + history ─────────────────
            with gr.Column(scale=1):
                gr.HTML('<div style="font-size:14px;font-weight:700;color:#1A2B42;margin-bottom:8px;">AI Analysis Result</div>')

                ai_status_html = gr.HTML("""
                <div style="background:#F0F4F8;border:2px dashed #D8E3EE;border-radius:12px;
                     padding:24px;text-align:center;color:#6B7E96;font-size:13px;">
                    Upload an image, then click <b>🤖 Analyze Image</b>.
                </div>""")

                # Editable AI fields
                ai_title_box = gr.Textbox(label="📌 Title (editable)", placeholder="AI will fill this…")
                ai_category_dd = gr.Dropdown(
                    label="🏷️ Category (editable)",
                    choices=CATEGORY_CHOICES,
                    value="Other",
                )
                ai_dept_dd = gr.Dropdown(
                    label="🏢 Department (editable)",
                    choices=DEPARTMENT_CHOICES,
                    value="Other",
                )
                ai_desc_box = gr.Textbox(
                    label="📝 Description (editable)",
                    placeholder="AI will fill this…",
                    lines=4,
                )

                submission_result_html = gr.HTML("")

                gr.HTML('<div class="section-title">📋 My Complaints History</div>')
                citizen_history = gr.HTML(
                    '<div style="text-align:center;padding:30px;color:#6B7E96;">Your submitted complaints will appear here.</div>'
                )

        with gr.Row():
            with gr.Column():
                gr.HTML('<div style="height:16px;"></div>')
                submit_btn = gr.Button("📤 Submit Complaint", elem_classes=["success-btn"])

        with gr.Row():
            with gr.Column():
                citizen_signout_btn = gr.Button("Sign Out", elem_classes=["signout-btn"])

    # ══════════════════════════════════════════════════════════
    # TAB 3 — Admin Dashboard
    # ══════════════════════════════════════════════════════════
    with gr.Tab("🛡️ Admin Dashboard", visible=False) as admin_tab:

        gr.HTML("""
        <div style="display:flex;justify-content:space-between;align-items:center;
             margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #D8E3EE;">
            <div>
                <div style="font-size:18px;font-weight:700;color:#1A2B42;letter-spacing:-0.3px;">All Complaints</div>
                <div style="font-size:13px;color:#6B7E96;margin-top:2px;">
                    Review, manage, and filter complaints geographically
                </div>
            </div>
        </div>""")

        # ── District filter + refresh ──
        with gr.Row(equal_height=True):
            with gr.Column(scale=2):
                district_filter_dd = gr.Dropdown(
                    label="🏙️ Filter by Chennai District",
                    choices=["All Cities"] + CHENNAI_DISTRICT_NAMES,
                    value="All Cities",
                    interactive=True,
                )
            with gr.Column(scale=1):
                admin_view_btn = gr.Button("🔄 Refresh Complaints", elem_classes=["primary-btn"])

        admin_container = gr.HTML("""
        <div style="background:#F0F4F8;border:2px dashed #D8E3EE;border-radius:12px;
             padding:40px;text-align:center;color:#6B7E96;font-size:14px;">
            Click <b>Refresh Complaints</b> to load data.
        </div>""")

        # ── Status Update Panel ──
        gr.HTML("""
        <div style="margin-top:28px;padding:14px 18px;
             background:linear-gradient(135deg,#0D7A6F,#12A99A);
             border-radius:12px;color:white;font-weight:700;font-size:14px;">
             🔧 Update Complaint Status
        </div>""")

        with gr.Row(equal_height=True):
            with gr.Column(scale=3):
                status_complaint_id = gr.Textbox(
                    label="Complaint ID",
                    placeholder="Paste the complaint ID from above…",
                    elem_id="status-complaint-id",
                )
            with gr.Column(scale=2):
                status_new_value = gr.Dropdown(
                    label="New Status",
                    choices=[("🔴 Pending","pending"), ("🟡 In Progress","in_progress"), ("✅ Resolved","resolved"), ("❌ Rejected","rejected")],
                    value="in_progress",
                    elem_classes=["status-select"],
                )
            with gr.Column(scale=1):
                status_update_btn = gr.Button("Update →", elem_classes=["update-btn"])

        status_update_result = gr.HTML("")

        gr.HTML("""
        <div style="margin-top:28px;padding:14px 18px;
             background:linear-gradient(135deg,#0B1F3A,#1A3F6F);
             border-radius:12px;color:white;font-weight:700;font-size:14px;">
             Complaint Images Gallery
        </div>""")

        admin_gallery = gr.Gallery(
            label="All Complaint Images",
            show_label=False,
            columns=3, rows=3,
            height="auto",
            object_fit="cover",
            preview=False,
            elem_id="admin-gallery",
            elem_classes=["fixed-gallery"],
        )

        with gr.Row():
            with gr.Column():
                gr.HTML('<div style="height:16px;"></div>')
                admin_signout_btn = gr.Button("Sign Out", elem_classes=["signout-btn"])

    # ══════════════════════════════════════════════════════════
    # WIRING
    # ══════════════════════════════════════════════════════════

    # Role selection
    citizen_btn.click(select_citizen_role, [], [selected_role_state, role_display, citizen_login_panel, admin_login_panel])
    admin_btn.click(  select_admin_role,   [], [selected_role_state, role_display, citizen_login_panel, admin_login_panel])
    signup_citizen_btn.click(lambda: ("citizen", _role_selector_html("citizen")), [], [selected_role_state, signup_role_display])
    signup_admin_btn.click(  lambda: ("admin",   _role_selector_html("admin")),   [], [selected_role_state, signup_role_display])

    # Toggle forms
    goto_signup_btn.click(show_signup, [], [login_form, signup_form])
    goto_login_btn.click( show_login,  [], [login_form, signup_form])

    # Login outputs helper
    _login_outputs = [
        auth_status, current_user_state, header_display, auth_content,
        citizen_tab, admin_tab, admin_container, admin_gallery,
        citizen_stats, citizen_history, notif_bell_html,
    ]

    citizen_signin_btn.click(
        login,
        [login_email, login_password, selected_role_state, current_user_state, admin_otp_input],
        _login_outputs,
    )
    get_otp_btn.click(request_admin_otp, [login_email, login_password], [auth_status])
    admin_signin_btn.click(
        login,
        [login_email, login_password, selected_role_state, current_user_state, admin_otp_input],
        _login_outputs,
    )

    signup_btn.click(
        signup,
        [signup_email, signup_password, selected_role_state, current_user_state],
        [auth_status, current_user_state, signup_form, login_form],
    )

    # Sign-out
    _signout_outputs = [auth_status, current_user_state, header_display, auth_content, citizen_tab, admin_tab]
    admin_signout_btn.click(signout,   [current_user_state], _signout_outputs)
    citizen_signout_btn.click(signout, [current_user_state], _signout_outputs)

    # ── Geolocation: JS fires, then Python reverse-geocodes ──────────────────
    geo_btn.click(
        fn=None,   # JS side: populate hidden textboxes
        inputs=[], outputs=[lat_hidden, lon_hidden],
        js=_GEOLOCATION_JS,
    )
    # After hidden boxes are updated, Python side reverse-geocodes
    lat_hidden.change(
        handle_location_capture,
        [lat_hidden, lon_hidden],
        [address_box, district_box, location_display_html],
    )

    # ── Analyze (Step 1) ──────────────────────────────────────────────────────
    analyse_btn.click(
        analyze_image_only,
        [image_in, user_msg, current_user_state],
        [ai_status_html, ai_title_box, ai_category_dd, ai_dept_dd, ai_desc_box],
    )

    # ── Submit (Step 2) ───────────────────────────────────────────────────────
    submit_btn.click(
        submit_complaint_final,
        [
            image_in, user_msg,
            ai_title_box, ai_category_dd, ai_dept_dd, ai_desc_box,
            lat_hidden, lon_hidden, address_box, district_box,
            current_user_state,
        ],
        [submission_result_html, citizen_stats],
    )

    # ── Admin refresh + district filter ──────────────────────────────────────

    def refresh_and_populate_districts(state):
        """Refresh complaints AND populate dropdown with all Chennai districts."""
        # Always show all 15 GCC zones — independent of what's in the DB
        cities = ["All Cities"] + CHENNAI_DISTRICT_NAMES
        html, imgs = get_admin_complaints_html(state, "All Cities")
        return html, imgs, gr.update(choices=cities, value="All Cities")

    admin_view_btn.click(
        refresh_and_populate_districts,
        [current_user_state],
        [admin_container, admin_gallery, district_filter_dd],
    )

    district_filter_dd.change(
        get_admin_complaints_filtered,
        [district_filter_dd, current_user_state],
        [admin_container, admin_gallery],
    )

    # ── Admin status update ───────────────────────────────────────────────────
    status_update_btn.click(
        handle_status_update,
        [status_complaint_id, status_new_value, current_user_state],
        [status_update_result],
    )

    # ── Notification bell ─────────────────────────────────────────────────────
    bell_btn.click(handle_bell_click, [current_user_state], [notif_panel_html, notif_bell_html])
    bell_btn.click(lambda: gr.update(visible=True), [], [notif_panel_html])


demo.launch(debug=True, favicon_path=None, share=False, css=custom_css, theme=gr.themes.Soft())