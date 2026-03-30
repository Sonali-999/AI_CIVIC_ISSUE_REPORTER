"""
kyc.py
------
KYC (Know Your Citizen) verification module for CivicAI.

FLOW
====
  1. Citizen fills KYC form: full name, phone, Aadhaar last-4, uploads ID image.
  2. Data is saved to MongoDB `kyc_col` with status = "pending".
  3. Admin reviews from the Admin Dashboard and approves / rejects.
  4. On complaint submission, `require_kyc_verified()` checks the citizen's
     KYC status and blocks submission if not yet verified.

KYC STATUSES
============
  unverified  — citizen has never submitted KYC (default)
  pending     — submitted but admin has not acted yet
  verified    — admin approved; citizen may submit complaints
  rejected    — admin rejected; citizen must re-submit
"""

import re
import uuid
import hashlib
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Field validation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _validate_phone(phone: str) -> bool:
    """Accept 10-digit Indian mobile numbers (optionally prefixed with +91 or 0)."""
    cleaned = re.sub(r"[\s\-()]", "", phone)
    return bool(re.fullmatch(r"(?:\+91|0)?[6-9]\d{9}", cleaned))


def _validate_aadhaar_last4(value: str) -> bool:
    """Accept exactly 4 digits."""
    return bool(re.fullmatch(r"\d{4}", value.strip()))


def _validate_full_name(name: str) -> bool:
    """At least two words, letters only (allows spaces, hyphens, apostrophes)."""
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z\s'\-]{1,60}", name.strip()))


def validate_kyc_fields(full_name: str, phone: str, aadhaar_last4: str) -> dict:
    """
    Validate all KYC text fields.

    Returns
    -------
    {"valid": True}  on success
    {"valid": False, "error": "<human-readable message>"}  on failure
    """
    if not full_name or not full_name.strip():
        return {"valid": False, "error": "Full name is required."}
    if not _validate_full_name(full_name):
        return {"valid": False, "error": "Full name must contain only letters and be at least two words."}

    if not phone or not phone.strip():
        return {"valid": False, "error": "Phone number is required."}
    if not _validate_phone(phone):
        return {"valid": False, "error": "Enter a valid 10-digit Indian mobile number."}

    if not aadhaar_last4 or not aadhaar_last4.strip():
        return {"valid": False, "error": "Last 4 digits of Aadhaar are required."}
    if not _validate_aadhaar_last4(aadhaar_last4):
        return {"valid": False, "error": "Aadhaar last-4 must be exactly 4 digits."}

    return {"valid": True}


# ─────────────────────────────────────────────────────────────────────────────
# KYC hash — one-way fingerprint for the submission (not stored in plaintext)
# ─────────────────────────────────────────────────────────────────────────────

def _kyc_fingerprint(user_id: str, phone: str, aadhaar_last4: str) -> str:
    """
    SHA-256 fingerprint of (user_id + phone + aadhaar_last4).
    Stored alongside the KYC record so duplicate submissions can be detected
    without storing sensitive data in plaintext.
    """
    raw = f"{user_id}|{phone.strip()}|{aadhaar_last4.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Submission builder  (called by db_utils.submit_kyc)
# ─────────────────────────────────────────────────────────────────────────────

def build_kyc_document(user_id: str, full_name: str,
                        phone: str, aadhaar_last4: str,
                        id_image_path: str) -> dict:
    """
    Build the MongoDB document for a new KYC submission.

    Parameters
    ----------
    user_id       : str   — UUID of the citizen
    full_name     : str   — citizen's full name
    phone         : str   — mobile number
    aadhaar_last4 : str   — last 4 digits of Aadhaar card
    id_image_path : str   — path to the uploaded ID / selfie image

    Returns
    -------
    dict ready to be inserted into `kyc_col`
    """
    return {
        "_id":            str(uuid.uuid4()),
        "user_id":        user_id,
        "full_name":      full_name.strip(),
        "phone":          phone.strip(),
        "aadhaar_last4":  aadhaar_last4.strip(),   # only 4 digits — not sensitive
        "id_image_path":  id_image_path,
        "fingerprint":    _kyc_fingerprint(user_id, phone, aadhaar_last4),
        "status":         "pending",
        "submitted_at":   datetime.utcnow(),
        "reviewed_at":    None,
        "reviewed_by":    None,     # admin user_id who acted
        "rejection_note": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Guard — call this before allowing a complaint submission
# ─────────────────────────────────────────────────────────────────────────────

KYC_BLOCK_MESSAGES = {
    "unverified": (
        "⚠️ KYC Required — Please complete identity verification before submitting a complaint. "
        "Go to the <b>KYC Verification</b> tab to submit your details."
    ),
    "pending": (
        "⏳ KYC Pending — Your identity verification is under review. "
        "You will be able to submit complaints once an admin approves your KYC."
    ),
    "rejected": (
        "❌ KYC Rejected — Your previous KYC submission was rejected. "
        "Please re-submit with correct details in the <b>KYC Verification</b> tab."
    ),
}


def require_kyc_verified(kyc_status: str) -> dict:
    """
    Check whether a citizen's KYC status allows complaint submission.

    Parameters
    ----------
    kyc_status : str  — one of "unverified", "pending", "verified", "rejected"

    Returns
    -------
    {"allowed": True}                         if verified
    {"allowed": False, "message": "<html>"}   otherwise
    """
    if kyc_status == "verified":
        return {"allowed": True}

    msg = KYC_BLOCK_MESSAGES.get(
        kyc_status,
        "⚠️ KYC status unknown. Please contact support."
    )
    return {"allowed": False, "message": msg}


# ─────────────────────────────────────────────────────────────────────────────
# Status badge HTML helper  (used in Gradio UI)
# ─────────────────────────────────────────────────────────────────────────────

_STATUS_STYLES = {
    "verified":   ("✅ Verified",   "#10B981", "#ECFDF5"),
    "pending":    ("⏳ Pending",    "#F59E0B", "#FFFBEB"),
    "rejected":   ("❌ Rejected",   "#EF4444", "#FEF2F2"),
    "unverified": ("🔘 Unverified", "#6B7E96", "#F0F4F8"),
}


def kyc_status_badge(status: str) -> str:
    """Return an HTML badge string for the given KYC status."""
    label, color, bg = _STATUS_STYLES.get(status, _STATUS_STYLES["unverified"])
    return (
        f'<span style="display:inline-block;padding:4px 12px;border-radius:20px;'
        f'background:{bg};color:{color};font-weight:700;font-size:12px;">'
        f'{label}</span>'
    )