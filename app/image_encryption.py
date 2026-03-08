"""
image_encryption.py
--------------------
AES-256-GCM encryption for complaint images in CivicAI.

HOW IT WORKS:
  - AES-256 = Advanced Encryption Standard with a 256-bit key.
  - GCM (Galois/Counter Mode) adds authentication — it detects if the
    ciphertext was tampered with (integrity + confidentiality in one).
  - A new random 12-byte nonce is generated for EVERY encryption.
  - The encrypted file layout on disk:
        [ 12 bytes nonce ][ 16 bytes auth-tag ][ N bytes ciphertext ]
  - The AES key is stored separately in  keys/aes_image_key.bin
    (show this file to your teacher as the "encryption key").

INSTALL:   pip install cryptography
"""

import os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .security_audit import log_security_event
# ── Key file path ────────────────────────────────────────────────────────────
KEY_DIR  = Path("keys")
KEY_FILE = KEY_DIR / "aes_image_key.bin"   # 32 raw bytes  = 256-bit key


def _load_or_create_key() -> bytes:
    """
    Load the AES-256 key from disk, or generate + save a new one.
    In production you would load this from a secure vault / env variable.
    """
    KEY_DIR.mkdir(exist_ok=True)
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = AESGCM.generate_key(bit_length=256)   # 32 random bytes
    KEY_FILE.write_bytes(key)
    print(f"[image_encryption] New AES-256 key saved → {KEY_FILE}")
    return key


def encrypt_image(image_path: str) -> str:
    """
    Encrypt the image at `image_path` and save an encrypted version
    alongside it with the extension .enc

    Example:
        encrypt_image("uploads/pothole.jpg")
        → writes  "uploads/pothole.jpg.enc"
        → returns "uploads/pothole.jpg.enc"
    """
    key   = _load_or_create_key()
    aesgcm = AESGCM(key)

    plaintext = Path(image_path).read_bytes()
    nonce     = os.urandom(12)                      # unique per-file nonce
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)  # includes 16-byte tag

    enc_path = image_path + ".enc"
    with open(enc_path, "wb") as f:
        f.write(nonce + ciphertext)                 # [ nonce | tag | ciphertext ]

    print(f"[image_encryption] Encrypted  {image_path} → {enc_path}")
    log_security_event(
        "IMAGE_ENCRYPTED",
        f"original={image_path}, encrypted={enc_path}"
    )
    return enc_path


def decrypt_image(enc_path: str) -> bytes:
    """
    Decrypt an encrypted image file.
    Returns the original raw image bytes (PNG/JPG).

    Example:
        raw = decrypt_image("uploads/pothole.jpg.enc")
    """
    key   = _load_or_create_key()
    aesgcm = AESGCM(key)

    data  = Path(enc_path).read_bytes()
    nonce = data[:12]
    ciphertext = data[12:]                          # tag is embedded in ciphertext

    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    print(f"[image_encryption] Decrypted  {enc_path}")
    log_security_event(
        "IMAGE_DECRYPTED",
        f"path={enc_path}"
    )
    return plaintext


# ── WHERE TO CALL THESE IN YOUR PROJECT ─────────────────────────────────────
#
#  In gradio_app.py → process_complaint():
#      from .image_encryption import encrypt_image
#      enc_path = encrypt_image(image_path)
#      save_complaint(..., image_path=enc_path)   # store encrypted path in DB
#
#  In db_utils.py → when serving images to admin gallery:
#      from .image_encryption import decrypt_image
#      raw_bytes = decrypt_image(enc_path)
#      # write to a temp file or serve as base64
#
# ────────────────────────────────────────────────────────────────────────────


# ── DEMO ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import tempfile, hashlib

    print("=" * 60)
    print("  AES-256-GCM Image Encryption Demo")
    print("=" * 60)

    # Create a fake "image" file
    sample = b"\x89PNG\r\n\x1a\n" + b"FAKE IMAGE DATA " * 100
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(sample)
        tmp = f.name

    print(f"\n  Original file  : {tmp}")
    print(f"  Original size  : {len(sample)} bytes")
    print(f"  SHA256 (before): {hashlib.sha256(sample).hexdigest()[:32]}...")

    enc = encrypt_image(tmp)
    enc_bytes = Path(enc).read_bytes()
    print(f"\n  Encrypted file : {enc}")
    print(f"  Encrypted size : {len(enc_bytes)} bytes  (nonce + tag + ciphertext)")
    print(f"  First 24 bytes (hex): {enc_bytes[:24].hex()}  ← looks like noise")

    recovered = decrypt_image(enc)
    print(f"\n  Decrypted SHA256: {hashlib.sha256(recovered).hexdigest()[:32]}...")
    print(f"  Data intact?     {recovered == sample}")
    print(f"\n  AES key stored in: {KEY_FILE}  ← show this to your teacher")
    print("=" * 60)

    os.unlink(tmp)
    os.unlink(enc)
