"""
set_admin_password.py
---------------------
Create or recover an administrator account.

    python set_admin_password.py --email admin@gmail.com
    python set_admin_password.py --email admin@gmail.com --password "admin@123"

Omitting --password generates a strong random one and prints it.

WHAT THIS FIXES
===============
An admin login needs THREE things to line up, and losing any one of them locks
the account out:

  1. a bcrypt password hash in MongoDB
  2. an ECDSA P-256 PRIVATE key at keys/admin_<email>_private.pem
  3. the matching PUBLIC key, with its path recorded on the user document

Point 2 is the one that bites: keys/ is gitignored, so cloning the repo onto a
new machine leaves the database rows intact while the key files vanish. Login
then fails at "Get OTP" - the OTP is derived from a signature made with that
private key - no matter how correct the password is.

This script rebuilds all three together, so they cannot drift apart.

SECURITY NOTE
=============
Regenerating the keypair invalidates the previous one. That is the intended
behaviour for recovery, but it does mean any other copy of the old private key
stops working.
"""

import argparse
import secrets
import string
import sys
from pathlib import Path

# Import as a package so the app's relative imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.admin_signature import (
    create_login_challenge, generate_admin_keypair, sign_challenge,
    verify_admin_signature,
)
from app.db_utils import update_user_public_key, users_col
from app.password_utils import hash_password
from app.security_audit import log_security_event


def generate_password(length: int = 16) -> str:
    """A readable but strong password: no ambiguous characters."""
    alphabet = (string.ascii_lowercase.replace("l", "")
                + string.ascii_uppercase.replace("O", "").replace("I", "")
                + string.digits.replace("0", "").replace("1", "")
                + "@#$%&*")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or recover a CivicAI administrator account."
    )
    parser.add_argument("--email", required=True, help="admin email address")
    parser.add_argument("--password", help="new password (generated if omitted)")
    parser.add_argument("--keep-keys", action="store_true",
                        help="do not regenerate the ECDSA keypair if one exists")
    args = parser.parse_args()

    email = args.email.strip().lower()
    password = args.password or generate_password()
    generated = args.password is None

    print("=" * 68)
    print("  CivicAI — Administrator Account Setup")
    print("=" * 68)

    existing = users_col.find_one({"email": email})

    # ── 1. Password ──────────────────────────────────────────────────────────
    pw_hash = hash_password(password)
    if existing:
        users_col.update_one(
            {"email": email},
            {"$set": {"password_hash": pw_hash, "role": "admin"}},
        )
        print(f"\n  [1/3] Password reset for existing user {email}")
        if existing.get("role") != "admin":
            print(f"        Role promoted: {existing.get('role')} -> admin")
    else:
        import uuid
        from datetime import datetime
        users_col.insert_one({
            "_id": str(uuid.uuid4()),
            "email": email,
            "password_hash": pw_hash,
            "role": "admin",
            "created_at": datetime.utcnow(),
        })
        print(f"\n  [1/3] Created new admin user {email}")

    # ── 2. ECDSA keypair ─────────────────────────────────────────────────────
    safe = email.replace("@", "_at_").replace(".", "_")
    priv_path = Path("keys") / f"admin_{safe}_private.pem"
    pub_path = Path("keys") / f"admin_{safe}_public.pem"

    if args.keep_keys and priv_path.exists() and pub_path.exists():
        print(f"  [2/3] Keeping existing keypair at {priv_path}")
        paths = {"private_key_path": str(priv_path), "public_key_path": str(pub_path)}
    else:
        paths = generate_admin_keypair(email)
        print(f"  [2/3] ECDSA P-256 keypair generated")

    update_user_public_key(email, paths["public_key_path"])
    print(f"  [3/3] Public key path recorded in MongoDB")

    # ── Verify the whole chain works before reporting success ────────────────
    challenge = create_login_challenge(email)
    signature = sign_challenge(challenge, paths["private_key_path"])
    ok = verify_admin_signature(challenge, signature, paths["public_key_path"])

    print("\n  Verification")
    print("  " + "-" * 64)
    print(f"    Signature round-trip : {'PASS' if ok else 'FAIL'}")
    print(f"    Private key          : {paths['private_key_path']}")
    print(f"    Public key           : {paths['public_key_path']}")

    if not ok:
        sys.exit("\n  Signature verification failed — the account is NOT usable.\n")

    log_security_event("ADMIN_CREDENTIALS_RESET", f"email={email}")

    print("\n  " + "=" * 64)
    print("   ADMIN CREDENTIALS")
    print("  " + "=" * 64)
    print(f"    Email    : {email}")
    print(f"    Password : {password}")
    if generated:
        print("\n    ^ This password was generated and is shown ONCE. Save it now.")
    print("  " + "=" * 64)

    print("""
  How to sign in
  --------------
    1. Open the app and click the "Admin" role button
    2. Enter the email and password above
    3. Click "Get OTP"  — a 6-digit code is printed in the TERMINAL
       running the app (not in the browser)
    4. Type that code into the OTP box and click "Sign In"

  The OTP is derived from an ECDSA signature made with the private key
  above, so it cannot be guessed without that file.
""")


if __name__ == "__main__":
    main()
