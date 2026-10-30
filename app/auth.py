# auth.py
# Wrappers to adapt db_utils for Gradio
from .password_utils import hash_password, verify_password
from .db_utils import register_user, login_user  # <-- relative import
from .admin_signature import (
    generate_admin_keypair,
    create_login_challenge,
    sign_challenge,
    verify_admin_signature,
)


def register_user_wrapper(email, password, role):         
    result = register_user(email, password, role)  # bcrypt hash

    # ── NEW: if admin, generate digital signature keypair ──
    if result.get("status") == "success" and role == "admin":
        paths = generate_admin_keypair(email)
        # Store the public key path in DB so login can find it
        from .db_utils import update_user_public_key
        update_user_public_key(email, paths["public_key_path"])
        print(f'Admin keypair created. Private key: {paths["private_key_path"]}')
    # ───────────────────────────────────────────────────────

    return result

def login_user_wrapper(email, password):
    # Step A — verify password via db_utils (bcrypt check happens inside)
    result = login_user(email, password)

    if result.get("status") != "success":
        return result  # wrong email or bad password — return early

    # ── NEW: Step B — digital signature check for admins ──
    if result.get("role") == "admin":
        from .db_utils import get_user_public_key_path
        pub_key_path = get_user_public_key_path(email)
        if pub_key_path:
            challenge = create_login_challenge(email)
            # For demo: auto-sign using the private key stored on same machine
            safe = email.replace("@", "_at_").replace(".", "_")
            priv_path = f"keys/admin_{safe}_private.pem"
            sig = sign_challenge(challenge, priv_path)
            ok = verify_admin_signature(challenge, sig, pub_key_path)
            if not ok:
                return {"status": "error", "error": "Signature verification failed"}
            print(f"Admin {email} authenticated via digital signature ✅")
    # ──────────────────────────────────────────────────────

    return result
