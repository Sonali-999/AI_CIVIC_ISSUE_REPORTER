"""
jwt_tokens.py
-------------
JWT (JSON Web Token) based session management for CivicAI.

HOW IT WORKS:
  A JWT has three parts, separated by dots:
      <Header>.<Payload>.<Signature>

  Header   — algorithm name (HS256) encoded in base64
  Payload  — the claims: user_id, email, role, expiry — encoded in base64
  Signature — HMAC-SHA256(header + "." + payload, SECRET_KEY)

  The server NEVER stores the token.
  On every request the server re-verifies the signature.
  If anyone changes the payload (e.g. changes role to "admin"),
  the signature won't match → request rejected.

INSTALL:   pip install PyJWT
"""

import hmac
import hashlib
import base64
import json
import time
import os
import secrets


# ── Secret key — load from environment or generate a strong random one ───────
# In production, set  JWT_SECRET  as an environment variable.
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_hex(32)
JWT_ALGORITHM = "HS256"

# Token expiry: citizens 2 hours, admins/officers 8 hours
EXPIRY_CITIZEN = 2 * 3600
EXPIRY_OFFICER = 8 * 3600


# ════════════════════════════════════════════════════════════════════════════
# PURE-PYTHON JWT implementation (no external library needed for demo)
# In your real app replace with:  import jwt; jwt.encode(...); jwt.decode(...)
# ════════════════════════════════════════════════════════════════════════════

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (padding % 4))

def _hmac_sha256(key: str, message: str) -> bytes:
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).digest()


def create_token(user_id: str, email: str, role: str) -> str:
    """
    Issue a signed JWT for the given user.

    The token encodes:
      - sub      : user_id
      - email    : user's email
      - role     : "citizen" | "admin" | "officer"
      - iat      : issued-at timestamp
      - exp      : expiry timestamp

    Returns a dot-separated JWT string safe to store in client state.
    """
    expiry = EXPIRY_OFFICER if role in ("admin", "officer") else EXPIRY_CITIZEN
    now    = int(time.time())

    header  = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub":   user_id,
        "email": email,
        "role":  role,
        "iat":   now,
        "exp":   now + expiry,
    }

    h = _b64url_encode(json.dumps(header,  separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64url_encode(_hmac_sha256(JWT_SECRET, f"{h}.{p}"))

    return f"{h}.{p}.{sig}"


def verify_token(token: str) -> dict:
    """
    Verify a JWT and return its payload dict if valid.

    Raises:
      ValueError  — if the token is malformed, signature is wrong,
                    or the token has expired.
    """
    try:
        h, p, sig = token.split(".")
    except ValueError:
        raise ValueError("Malformed token — expected 3 parts separated by '.'")

    # Re-compute signature
    expected_sig = _b64url_encode(_hmac_sha256(JWT_SECRET, f"{h}.{p}"))
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid token — signature does not match (tampered?)")

    payload = json.loads(_b64url_decode(p))

    if int(time.time()) > payload["exp"]:
        raise ValueError("Token has expired — please log in again")

    return payload


def token_required(token: str, required_role: str = None) -> dict:
    """
    Convenience guard for route handlers.
    Verifies token and optionally checks role.

    Returns payload dict on success.
    Raises ValueError on failure (caller should return 401/403).
    """
    payload = verify_token(token)
    if required_role and payload.get("role") != required_role:
        raise ValueError(
            f"Access denied — requires role '{required_role}', got '{payload['role']}'"
        )
    return payload


# ── WHERE TO CALL THESE IN YOUR PROJECT ─────────────────────────────────────
#
#  In gradio_app.py → login():
#      from .jwt_tokens import create_token
#      token = create_token(user_id, email, role)
#      state["token"] = token    # replace the plain dict with the JWT
#
#  In gradio_app.py → process_complaint() / get_admin_complaints_html():
#      from .jwt_tokens import token_required
#      try:
#          payload = token_required(state.get("token"), required_role="citizen")
#      except ValueError as e:
#          return f'<div class="status-error">❌ {e}</div>'
#      uid = payload["sub"]
#
#  In gradio_app.py → handle_status_update() (admin only):
#      payload = token_required(state.get("token"), required_role="admin")
#
# ────────────────────────────────────────────────────────────────────────────


# ── DEMO ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  JWT Token Demo — Citizen & Admin/Officer Access")
    print("=" * 60)

    # Issue tokens
    citizen_token = create_token("uid_001", "user@civic.com",  "citizen")
    admin_token   = create_token("uid_002", "admin@civic.com", "admin")

    print(f"\n  Citizen JWT:\n  {citizen_token[:60]}...")
    print(f"\n  Admin JWT:\n  {admin_token[:60]}...")

    # Decode parts visually
    parts = admin_token.split(".")
    header_str  = json.loads(_b64url_decode(parts[0]))
    payload_str = json.loads(_b64url_decode(parts[1]))
    print(f"\n  Decoded header  : {header_str}")
    print(f"  Decoded payload : {payload_str}")
    print(f"  Signature (b64) : {parts[2][:30]}...")

    # Verify
    p = verify_token(admin_token)
    print(f"\n  verify_token(admin_token)  → {p}")

    # Role guard
    try:
        token_required(citizen_token, required_role="admin")
    except ValueError as e:
        print(f"\n  token_required (citizen accessing admin) → ❌ {e}")

    # Tamper test — change role in payload to "admin"
    h, p_raw, s = citizen_token.split(".")
    payload_data = json.loads(_b64url_decode(p_raw))
    payload_data["role"] = "admin"           # attacker tries to escalate role!
    tampered_p = _b64url_encode(json.dumps(payload_data, separators=(",",":")).encode())
    tampered_token = f"{h}.{tampered_p}.{s}" # keep original signature

    try:
        verify_token(tampered_token)
    except ValueError as e:
        print(f"\n  Tampered token (role changed to admin) → ❌ {e}")

    print("\n  JWT_SECRET (first 16 chars): " + JWT_SECRET[:16] + "...")
    print("  Store this in your .env file as JWT_SECRET=<value>")
    print("=" * 60)
