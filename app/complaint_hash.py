"""
complaint_hash.py
-----------------
Custom complaint-integrity hashing algorithm for CivicAI.

YOUR OWN ALGORITHM — "CivicHash-512"
======================================
Upgraded from CivicHash-256. This algorithm combines THREE independent
cryptographic primitives — AES-256-GCM, HMAC-SHA256, and SHA-512 —
making it impossible to reproduce without knowing both secret keys.

  STEP 1 — Field Normalisation
        Strip, lowercase, and sort all complaint fields alphabetically.
        Produces a canonical JSON byte string — field order never matters.

  STEP 2 — AES-256-GCM Encryption of normalised data  ← NEW
        The normalised bytes are encrypted using the SAME AES-256 key
        as image_encryption.py (loaded from keys/aes_image_key.bin).
        This produces:
            • ciphertext  — encrypted form of the complaint data
            • auth_tag    — 16-byte GCM authentication tag (tamper proof)
        WHY: Binds the hash cryptographically to the AES key. An attacker
        cannot reproduce the hash without the key file, even knowing the
        algorithm and all complaint fields.

  STEP 3 — HMAC-SHA256 over ciphertext using pepper  ← NEW
        HMAC-SHA256( key=_PEPPER_KEY, msg=ciphertext )
        WHY: Adds a second, completely independent secret layer on top of
        AES. Breaking the hash requires compromising BOTH the AES key AND
        the pepper — two unrelated secrets.

  STEP 4 — Triple-round SHA-512 with salt interleaving  ← UPGRADED
        Round A = SHA-512( auth_tag  +  hmac_digest  +  salt_bytes )
        Round B = SHA-512( Round_A   +  pepper_key   +  ciphertext[:32] )
        Round C = SHA-512( Round_B   +  Round_A      +  salt_bytes )
        Final   = hex( Round_C )  →  128 hex characters = 512-bit digest

  WHY THIS IS "YOUR" ALGORITHM:
        • No standard library implements this exact combination.
        • The AES-GCM → HMAC → triple-SHA-512 chaining is invented here.
        • Three separate secrets protect three separate layers:
            Layer 1  →  AES key   (keys/aes_image_key.bin)
            Layer 2  →  Pepper    (_PEPPER_KEY constant)
            Layer 3  →  Salt      (per-complaint UUID from DB)
        • Compromising one layer does NOT break the others.

COMPARISON — old vs new
========================
  Property          CivicHash-256 (old)     CivicHash-512 (new)
  ─────────────────────────────────────────────────────────────
  Output size       256 bits (64 hex)       512 bits (128 hex)
  Hash rounds       2 × SHA-256             3 × SHA-512
  Secrets used      1 (pepper only)         2 (AES key + pepper)
  Crypto primitives XOR + SHA-256           AES-GCM + HMAC + SHA-512
  Auth tag          ✗                       ✓ (GCM tag)
  Key binding       ✗                       ✓ (AES key file)
  Attack resistance Moderate                Very High

INSTALL:
    pip install cryptography   (already needed for image_encryption.py)
"""

import hashlib
import hmac
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ── Secret pepper — Layer 2 independent secret ───────────────────────────────
# In production store in an environment variable, not in source code.
_PEPPER_KEY = b"CivicAI-Pepper-v2-\x3f\x7a\x11\xde\xab\x52\xc9\x8e\x01\xf4"

# ── AES key path — shared with image_encryption.py ───────────────────────────
# ── Key file path ────────────────────────────────────────────────────────────
_KEY_DIR  = Path("keys")
_KEY_FILE = _KEY_DIR / "aes_image_key.bin"   # 32 raw bytes  = 256-bit key


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_aes_key() -> bytes:
    """
    Load the 256-bit AES key from disk.
    This is the SAME key used by image_encryption.py — intentional.
    Binding the complaint hash to the image encryption key means both
    systems break together if the key is changed, preventing partial attacks.
    """
    if not os.path.exists(_KEY_FILE):
        raise FileNotFoundError(
            f"AES key not found at {_KEY_FILE}. "
            "Run image_encryption.py once first to generate it."
        )
    key = open(_KEY_FILE, "rb").read()
    if len(key) != 32:
        raise ValueError(f"AES key must be 32 bytes, got {len(key)}")
    return key


def _normalise_complaint(fields: dict) -> bytes:
    """
    Produce a stable, canonical byte representation of complaint fields.
    Sorting keys means field order never affects the hash.
    Stripping and lowercasing means whitespace/case differences are ignored.
    """
    canonical = {k: str(v).strip().lower() for k, v in sorted(fields.items())}
    return json.dumps(canonical, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _aes_encrypt_fields(normalised: bytes, aes_key: bytes, nonce: bytes) -> tuple[bytes, bytes]:
    """
    STEP 2 — Encrypt normalised complaint data with AES-256-GCM.

    Returns
    -------
    ciphertext : bytes   — encrypted data (same length as input)
    auth_tag   : bytes   — 16-byte GCM authentication tag

    The nonce is derived deterministically from the salt so the same
    complaint always produces the same ciphertext (needed for hash stability).
    The cryptography library appends the tag to ciphertext; we split them.
    """
    aesgcm = AESGCM(aes_key)
    # encrypt() returns ciphertext + 16-byte tag concatenated
    ct_and_tag = aesgcm.encrypt(nonce, normalised, associated_data=_PEPPER_KEY)
    ciphertext = ct_and_tag[:-16]
    auth_tag   = ct_and_tag[-16:]
    return ciphertext, auth_tag


def _hmac_layer(ciphertext: bytes) -> bytes:
    """
    STEP 3 — HMAC-SHA256 of ciphertext using the pepper as the HMAC key.
    Completely independent from the AES key — a second secret layer.
    """
    return hmac.new(_PEPPER_KEY, ciphertext, hashlib.sha256).digest()


def _triple_sha512(auth_tag: bytes, hmac_digest: bytes,
                   salt_bytes: bytes, ciphertext: bytes) -> str:
    """
    STEP 4 — Three rounds of SHA-512 with material from every previous step.

    Round A mixes the AES auth tag + HMAC result + salt.
    Round B mixes Round A + pepper + first 32 bytes of ciphertext.
    Round C mixes Round B + Round A + salt again (avalanche amplification).
    Final output is 128 hex characters = 512 bits.
    """
    round_a = hashlib.sha512(auth_tag   + hmac_digest + salt_bytes).digest()
    round_b = hashlib.sha512(round_a    + _PEPPER_KEY + ciphertext[:32]).digest()
    round_c = hashlib.sha512(round_b    + round_a     + salt_bytes).digest()
    return round_c.hex()


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def civic_hash(complaint_fields: dict, salt: str = "") -> str:
    """
    CivicHash-512 — the upgraded custom integrity hash for CivicAI.

    Combines AES-256-GCM + HMAC-SHA256 + triple-round SHA-512.
    Requires both the AES key file AND the pepper to reproduce.

    Parameters
    ----------
    complaint_fields : dict
        Any combination of: title, category, department, description,
                            user_id, timestamp, status
    salt : str
        Per-complaint salt — use the complaint's UUID from the database.
        Ensures two identical complaints never share a hash.

    Returns
    -------
    str  —  128-character lowercase hex string (512-bit digest)

    Example
    -------
        h = civic_hash({"title": "Pothole", "department": "Roads"}, salt="abc123")
        # → "3f8a2c9d..." (128 chars)
    """
    salt_bytes = salt.encode("utf-8")

    # Step 1 — normalise fields into canonical bytes
    normalised = _normalise_complaint(complaint_fields)

    # Step 2 — AES-256-GCM encryption
    # Nonce: first 12 bytes of SHA-256(salt + pepper) — deterministic but unique per complaint
    aes_key   = _load_aes_key()
    nonce_src = hashlib.sha256(salt_bytes + _PEPPER_KEY).digest()
    nonce     = nonce_src[:12]   # AES-GCM requires exactly 12 bytes
    ciphertext, auth_tag = _aes_encrypt_fields(normalised, aes_key, nonce)

    # Step 3 — HMAC-SHA256 of ciphertext using pepper
    hmac_digest = _hmac_layer(ciphertext)

    # Step 4 — Triple-round SHA-512
    return _triple_sha512(auth_tag, hmac_digest, salt_bytes, ciphertext)


def verify_complaint_integrity(complaint_fields: dict, salt: str, stored_hash: str) -> bool:
    """
    Re-compute CivicHash-512 and compare to the stored value.
    Returns True  → data is intact, no tampering detected.
    Returns False → hash mismatch, complaint data was altered.

    Uses hmac.compare_digest to prevent timing-based attacks.
    """
    computed = civic_hash(complaint_fields, salt)
    return hmac.compare_digest(computed, stored_hash)


# ─────────────────────────────────────────────────────────────────────────────
# WHERE TO CALL THESE IN YOUR PROJECT
# ─────────────────────────────────────────────────────────────────────────────
#
#  In db_utils.py → save_complaint():
#      from .complaint_hash import civic_hash
#      fields = {"title": title, "category": category,
#                "department": department, "description": description,
#                "user_id": user_id, "timestamp": timestamp.isoformat(),
#                "status": status}
#      integrity_hash = civic_hash(fields, salt=complaint_id)
#      # Store integrity_hash in DB alongside the complaint
#
#  In db_utils.py → when loading complaints for admin:
#      from .complaint_hash import verify_complaint_integrity
#      ok = verify_complaint_integrity(fields, salt=str(c["_id"]), stored_hash=c["integrity_hash"])
#      if not ok:
#          print(f"WARNING: complaint {c['_id']} has been tampered with!")
#
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# DEMO  —  run:  python complaint_hash.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 72)
    print("  CivicHash-512  —  AES-256-GCM + HMAC-SHA256 + Triple SHA-512")
    print("=" * 72)

    complaint = {
        "title":       "Large pothole on main street",
        "category":    "Road Damage",
        "department":  "Roads",
        "description": "Deep pothole causing vehicle damage",
        "user_id":     "user_042",
        "timestamp":   "2025-03-07T10:00:00Z",
        "status":      "pending",
    }
    salt = "complaint_uuid_abc123"

    print("\n  ── STEP BY STEP ──────────────────────────────────────────────")

    # Reproduce internals for demo
    salt_bytes = salt.encode()
    normalised = _normalise_complaint(complaint)
    print(f"\n  Step 1  Normalised JSON:\n          {normalised.decode()}")

    aes_key   = _load_aes_key()
    nonce_src = hashlib.sha256(salt_bytes + _PEPPER_KEY).digest()
    nonce     = nonce_src[:12]
    ciphertext, auth_tag = _aes_encrypt_fields(normalised, aes_key, nonce)
    print(f"\n  Step 2  AES-256-GCM:")
    print(f"          Nonce     : {nonce.hex()}")
    print(f"          Auth tag  : {auth_tag.hex()}  ← tamper-evident")
    print(f"          Ciphertext: {ciphertext[:16].hex()}...  ({len(ciphertext)} bytes)")

    hmac_digest = _hmac_layer(ciphertext)
    print(f"\n  Step 3  HMAC-SHA256 of ciphertext:")
    print(f"          {hmac_digest.hex()}")

    final = _triple_sha512(auth_tag, hmac_digest, salt_bytes, ciphertext)
    print(f"\n  Step 4  Triple SHA-512 final hash (512 bits = 128 hex chars):")
    print(f"          {final[:64]}")
    print(f"          {final[64:]}")

    print("\n  ── INTEGRITY TESTS ───────────────────────────────────────────")

    h = civic_hash(complaint, salt)
    ok = verify_complaint_integrity(complaint, salt, h)
    print(f"\n  Integrity check (unmodified) : {ok}")          # True

    tampered = dict(complaint)
    tampered["status"] = "resolved"
    ok_tampered = verify_complaint_integrity(tampered, salt, h)
    print(f"  Integrity check (tampered)   : {ok_tampered}")   # False

    reordered = {
        "status": "pending", "title": "Large pothole on main street",
        "user_id": "user_042", "timestamp": "2025-03-07T10:00:00Z",
        "description": "Deep pothole causing vehicle damage",
        "department": "Roads", "category": "Road Damage"
    }
    h2 = civic_hash(reordered, salt)
    print(f"  Field order invariant         : {h == h2}")       # True

    print("\n  ── ALGORITHM SUMMARY ─────────────────────────────────────────")
    print("  Step 1  Normalise     → canonical JSON bytes")
    print("  Step 2  AES-256-GCM   → ciphertext + 16-byte auth tag")
    print("          (key: keys/aes_image_key.bin — same as image encryption)")
    print("  Step 3  HMAC-SHA256   → 32-byte digest  (key: pepper constant)")
    print("  Step 4  SHA-512 ×3    → 512-bit final hash  (128 hex chars)")
    print("\n  Secrets required to reproduce:")
    print("    [1] keys/aes_image_key.bin  (AES key — Layer 2)")
    print("    [2] _PEPPER_KEY constant    (HMAC key — Layer 3)")
    print("    [3] complaint UUID salt     (per-record — Layer 4)")
    print("=" * 72)