"""
password_utils.py
-----------------
bcrypt-based password hashing for CivicAI.

HOW IT WORKS:
  - bcrypt generates a unique random salt every time a password is hashed.
  - The salt is embedded inside the hash string itself (no need to store separately).
  - Even if two users have the SAME password, their stored hashes look completely different.
  - The hash cannot be reversed — there is no "decrypt" operation.

INSTALL:   pip install bcrypt
"""

import bcrypt


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using bcrypt (cost factor 12).

    Returns a string like:
        $2b$12$eImiTXuWVxfM37uY4JANjQ...
        ^^^^  ^^  ^^^^^^^^^^^^^^^^^^^
        alg  cost    salt + hash (60 chars total)

    The returned string is safe to store directly in your database.
    """
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)          # higher rounds = slower brute-force
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")             # store as a plain string in DB


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """
    Check whether a plain-text password matches the stored bcrypt hash.
    Returns True if correct, False otherwise.
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        stored_hash.encode("utf-8")
    )


# ── WHERE TO CALL THESE IN YOUR PROJECT ─────────────────────────────────────
#
#  In auth.py → register_user_wrapper():
#      from .password_utils import hash_password
#      hashed = hash_password(password)
#      # store `hashed` in the DB instead of `password`
#
#  In auth.py → login_user_wrapper():
#      from .password_utils import verify_password
#      if not verify_password(plain_password, row["password_hash"]):
#          return {"status": "error", "message": "Invalid credentials"}
#
# ────────────────────────────────────────────────────────────────────────────


# ── DEMO (run this file directly to see it in action) ───────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  bcrypt Password Hashing Demo")
    print("=" * 60)

    password = "MySecret@123"
    print(f"\n  Plain-text password : {password}")

    h1 = hash_password(password)
    h2 = hash_password(password)          # same password, different salt each time

    print(f"\n  Hash #1 (stored in DB) :\n  {h1}")
    print(f"\n  Hash #2 (same password):\n  {h2}")
    print(f"\n  Are hashes identical?  {h1 == h2}")   # False — different salts!

    print(f"\n  Verify correct password : {verify_password(password, h1)}")
    print(f"  Verify wrong  password  : {verify_password('WrongPass!', h1)}")
    print("\n" + "=" * 60)
