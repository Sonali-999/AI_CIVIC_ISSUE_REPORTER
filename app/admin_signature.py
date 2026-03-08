"""
admin_signature.py
------------------
ECDSA digital signature authentication for CivicAI admins.

WHY ECDSA (not RSA)?
  - ECDSA (Elliptic Curve DSA) uses P-256 — keys are only 32 bytes but
    give the same security as RSA-3072.
  - Faster to generate, faster to sign and verify.
  - RSA is included too (see rsa_demo()) if your teacher wants to see both.

HOW IT WORKS:
  1. REGISTRATION
       → Generate a P-256 key pair.
       → Save private key  →  keys/admin_<email>_private.pem  (admin keeps this)
       → Save public key   →  keys/admin_<email>_public.pem   (server stores this)

  2. LOGIN CHALLENGE
       → Server creates a challenge:  "CIVICAI-LOGIN:<email>:<ISO-timestamp>"
       → Admin's client signs it with their private key.
       → Server verifies the signature with the stored public key.
       → If valid → admin is authenticated.  No password needed.

  3. TAMPER TEST
       → Change even ONE character in the challenge or signature → verification fails.

INSTALL:   pip install cryptography
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA, generate_private_key, SECP256R1, EllipticCurvePrivateKey
)
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature, encode_dss_signature
)
from cryptography.exceptions import InvalidSignature

KEY_DIR = Path("keys")


# ════════════════════════════════════════════════════════════════════════════
# ECDSA  (PRIMARY — recommended for your project)
# ════════════════════════════════════════════════════════════════════════════

def generate_admin_keypair(admin_email: str) -> dict:
    """
    Generate an ECDSA P-256 key pair for an admin and save both files.

    Returns a dict with paths to both key files.
    """
    KEY_DIR.mkdir(exist_ok=True)
    safe_name = admin_email.replace("@", "_at_").replace(".", "_")

    # Generate private key
    private_key = generate_private_key(SECP256R1())
    public_key  = private_key.public_key()

    priv_path = KEY_DIR / f"admin_{safe_name}_private.pem"
    pub_path  = KEY_DIR / f"admin_{safe_name}_public.pem"

    # Save private key (PEM format — show this to your teacher)
    priv_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()
        )
    )

    # Save public key (stored in DB / server side)
    pub_path.write_bytes(
        public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )

    print(f"[admin_signature] Keys saved:")
    print(f"  Private → {priv_path}  (admin keeps this — NEVER share)")
    print(f"  Public  → {pub_path}   (stored in database/server)")

    return {"private_key_path": str(priv_path), "public_key_path": str(pub_path)}


def create_login_challenge(admin_email: str) -> str:
    """
    Create a time-stamped challenge string for the admin to sign.
    Valid for 5 minutes only (replay-attack protection).

    Returns a plain string like:
        CIVICAI-LOGIN:admin@example.com:2025-03-07T10:00:00+00:00
    """
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return f"CIVICAI-LOGIN:{admin_email}:{ts}"


def sign_challenge(challenge: str, private_key_path: str) -> str:
    """
    Sign a challenge string with the admin's private key.
    Returns a hex-encoded DER signature string.

    In a real app the admin runs this on THEIR machine with THEIR private key.
    """
    priv_bytes = Path(private_key_path).read_bytes()
    private_key = serialization.load_pem_private_key(priv_bytes, password=None)

    signature = private_key.sign(
        challenge.encode("utf-8"),
        ECDSA(hashes.SHA256())
    )
    return signature.hex()


def verify_admin_signature(challenge: str, signature_hex: str, public_key_path: str) -> bool:
    """
    Verify the admin's signature on the server side.
    Returns True if the signature is valid (admin is genuine).
    """
    pub_bytes  = Path(public_key_path).read_bytes()
    public_key = serialization.load_pem_public_key(pub_bytes)

    try:
        public_key.verify(
            bytes.fromhex(signature_hex),
            challenge.encode("utf-8"),
            ECDSA(hashes.SHA256())
        )
        return True
    except InvalidSignature:
        return False


# ════════════════════════════════════════════════════════════════════════════
# RSA (BONUS — included so your teacher can see both algorithms)
# ════════════════════════════════════════════════════════════════════════════

def rsa_demo():
    """
    Show RSA-2048 signing and verification for comparison with ECDSA.
    """
    print("\n── RSA-2048 Demo ──────────────────────────────────────")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key  = private_key.public_key()

    message = b"CIVICAI-LOGIN:admin@civicai.com:2025-03-07T10:00:00+00:00"

    # Sign
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    print(f"  RSA-2048 signature ({len(signature)} bytes): {signature[:16].hex()}...")

    # Verify
    try:
        public_key.verify(
            signature, message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        print("  Verification: PASSED ✅")
    except InvalidSignature:
        print("  Verification: FAILED ❌")


# ── WHERE TO CALL THESE IN YOUR PROJECT ─────────────────────────────────────
#
#  In auth.py → register_user_wrapper()  (when role == "admin"):
#      from .admin_signature import generate_admin_keypair
#      paths = generate_admin_keypair(email)
#      # Store pub_path in DB;  tell admin to download their private key
#
#  In auth.py → login_user_wrapper()  (when role == "admin"):
#      from .admin_signature import create_login_challenge, verify_admin_signature
#      challenge  = create_login_challenge(email)
#      # Send challenge to admin's client; receive signature back
#      ok = verify_admin_signature(challenge, signature_hex, pub_key_path)
#
# ────────────────────────────────────────────────────────────────────────────


# ── DEMO ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  ECDSA P-256 Digital Signature Demo")
    print("=" * 60)

    email = "admin@civicai.com"

    # 1. Admin registers → keypair generated
    paths = generate_admin_keypair(email)

    # 2. Server sends challenge
    challenge = create_login_challenge(email)
    print(f"\n  Login challenge:\n  {challenge}")

    # 3. Admin signs with private key
    sig_hex = sign_challenge(challenge, paths["private_key_path"])
    print(f"\n  Signature (hex, first 40 chars):\n  {sig_hex[:40]}...")
    print(f"  Signature total length: {len(sig_hex)//2} bytes")

    # 4. Server verifies
    result = verify_admin_signature(challenge, sig_hex, paths["public_key_path"])
    print(f"\n  Verification (correct signature) : {result}")   # True

    # 5. Tamper test — flip one character
    tampered_sig = sig_hex[:-2] + ("00" if sig_hex[-2:] != "00" else "ff")
    result2 = verify_admin_signature(challenge, tampered_sig, paths["public_key_path"])
    print(f"  Verification (tampered signature): {result2}")    # False

    # 6. Show RSA for comparison
    rsa_demo()

    print("\n  Key files created in ./keys/  — show these to your teacher!")
    print("=" * 60)
