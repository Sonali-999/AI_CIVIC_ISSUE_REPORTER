"""
DB helpers for users and complaints using MongoDB.
"""
import os
from dotenv import load_dotenv
from pymongo import MongoClient
import bcrypt
import uuid
from datetime import datetime
from bson import ObjectId
from .image_encryption import decrypt_image
import tempfile
from .complaint_hash import civic_hash, verify_complaint_integrity
from datetime import datetime
from .admin_signature import (
    generate_admin_keypair,
    create_login_challenge,
    sign_challenge,
    verify_admin_signature,
)
from .security_audit import log_security_event
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "ai_civic")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

users_col         = db["users"]
complaints_col    = db["complaints"]
notifications_col = db["notifications"]
security_logs_col = db["security_logs"]
# ---------------- Users ----------------

def register_user(email, password, role="citizen"):
    if users_col.find_one({"email": email}):
        return {"status": "error", "error": "Email already exists"}

    user_id = str(uuid.uuid4())
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    users_col.insert_one({
        "_id": user_id,
        "email": email,
        "password_hash": pw_hash,
        "role": role,
        "created_at": datetime.utcnow()
    })

    return {"status": "success", "user_id": user_id}


def login_user(email, password):
    user = users_col.find_one({"email": email})

    if not user:
        return {"status": "error", "error": "not_found"}

    if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return {
            "status": "success",
            "user_id": user["_id"],
            "role": user.get("role", "citizen")
        }

    return {"status": "error", "error": "bad_credentials"}

def update_user_public_key(email: str, public_key_path: str):
    """Store the admin's public key path in their user document."""
    users_col.update_one(
        {"email": email},
        {"$set": {"public_key_path": public_key_path}}
    )

def get_user_public_key_path(email: str):
    """Retrieve the stored public key path for an admin user."""
    user = users_col.find_one({"email": email})
    if user:
        return user.get("public_key_path")
    return None

# ---------------- Complaints ----------------

from .complaint_hash import civic_hash   # add this at the top of db_utils.py

def save_complaint(user_id, title, category, department, description, image_path, status="pending"):
    department = department.strip().title()
    timestamp  = datetime.utcnow().isoformat()
    result = complaints_col.insert_one({
        "user_id":    user_id,
        "title":      title,
        "category":   category,
        "department": department,
        "description": description,
        "image_path": image_path,
        "status":     status,
        "created_at": timestamp,
    })

    # ── Compute and store integrity hash ──────────────────────────
    complaint_id = str(result.inserted_id)
    fields = {
        "title":       title,
        "category":    category,
        "department":  department,
        "description": description,
        "user_id":     user_id,
        "timestamp":   timestamp,
        "status":      status,
    }
    try:
        integrity_hash = civic_hash(fields, salt=complaint_id)
        update_result = complaints_col.update_one(
            {"_id": result.inserted_id},
            {"$set": {"integrity_hash": integrity_hash}}
        )
    except Exception as e:
        print(f"[DEBUG] civic_hash FAILED: {e}")      
    return complaint_id



def get_complaint_image_for_display(enc_path: str) -> str:
    """Decrypt an encrypted complaint image and return a temp path for Gradio to display."""
    if not enc_path:
        return None
    if not enc_path.endswith(".enc"):
        return enc_path
    raw_bytes = decrypt_image(enc_path)
    suffix = ".jpg" if ".jpg" in enc_path else ".png"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(raw_bytes)
    tmp.close()
    return tmp.name


def get_complaints_by_department(dept):
    dept = dept.strip().title()
    complaints = list(
        complaints_col.find({"department": dept})
        .sort("created_at", -1)
    )

    # ── ADD integrity check ──────────────────────────────────────────
    for c in complaints:
        stored_hash = c.get("integrity_hash")
        if stored_hash:
            fields = {
                "title":       c.get("title", ""),
                "category":    c.get("category", ""),
                "department":  c.get("department", ""),
                "description": c.get("description", ""),
                "user_id":     c.get("user_id", ""),
                "timestamp":   c.get("created_at", ""),
                "status":      c.get("status", "pending"),
            }
            ok = verify_complaint_integrity(
                fields,
                salt=str(c["_id"]),
                stored_hash=stored_hash
            )
            c["tampered"] = not ok
            if not ok:
                print(f"WARNING: Complaint {c['_id']} may have been tampered with!")
        else:
            c["tampered"] = False
    # ─────────────────────────────────────────────────────────────────

    return complaints



def get_all_complaints():
    """Return all complaints sorted newest first, with decrypted images and integrity check."""
    complaints = list(complaints_col.find().sort("created_at", -1))
    result = []

    for c in complaints:
        # ── NEW: verify integrity hash ─────────────────────────────────
        stored_hash = c.get("integrity_hash")
        if stored_hash:
            fields = {
                "title":       c.get("title", ""),
                "category":    c.get("category", ""),
                "department":  c.get("department", ""),
                "description": c.get("description", ""),
                "user_id":     c.get("user_id", ""),
                "timestamp":   c.get("created_at", ""),
                "status":      c.get("status", "pending"),
            }
            ok = verify_complaint_integrity(
                fields,
                salt=str(c["_id"]),
                stored_hash=stored_hash
            )
            c["tampered"] = not ok
            if not ok:
                print(f"WARNING: Complaint {c['_id']} may have been tampered with!")
        else:
            # Older complaints submitted before integrity hashing was added
            c["tampered"] = False
        # ──────────────────────────────────────────────────────────────

        # Decrypt image for display
        if c.get("image_path"):
            c["image_path"] = get_complaint_image_for_display(c["image_path"])

        result.append(c)

    return result


def update_complaint_status(complaint_id: str, new_status: str) -> dict:
    """
    Update a complaint's status in MongoDB and create a notification
    for the owning citizen.

    Returns {"status": "success"} or {"status": "error", "error": "..."}.
    """
    valid_statuses = {"pending", "in_progress", "resolved"}
    if new_status not in valid_statuses:
        return {"status": "error", "error": f"Invalid status '{new_status}'"}

    # Support both ObjectId and plain-string _id values
    try:
        oid = ObjectId(complaint_id)
        query = {"_id": oid}
    except Exception:
        query = {"_id": complaint_id}

    complaint = complaints_col.find_one(query)
    if not complaint:
        # Fallback: try string _id
        complaint = complaints_col.find_one({"_id": complaint_id})
        if not complaint:
            return {"status": "error", "error": "Complaint not found"}
        query = {"_id": complaint_id}

    old_status = complaint.get("status", "pending")
    if old_status == new_status:
        return {"status": "success", "message": "Status unchanged"}

    # ── NEW: recompute integrity hash with the new status ────────────
    fields = {
        "title":       complaint.get("title", ""),
        "category":    complaint.get("category", ""),
        "department":  complaint.get("department", ""),
        "description": complaint.get("description", ""),
        "user_id":     complaint.get("user_id", ""),
        "timestamp":   complaint.get("created_at", ""),
        "status":      new_status,                       # ← new status, not old
    }
    new_hash = civic_hash(fields, salt=complaint_id)
    # ─────────────────────────────────────────────────────────────────

    complaints_col.update_one(query, {"$set": {
        "status":         new_status,
        "updated_at":     datetime.utcnow(),
        "integrity_hash": new_hash,              # ← update hash alongside status
    }})

    # ── SECURITY AUDIT LOG ──
    log_security_event(
        "STATUS_UPDATED",
        f"complaint_id={complaint_id}, old={old_status}, new={new_status}"
    )

    # Create an in-app notification for the citizen
    _create_status_notification(
        user_id      = complaint["user_id"],
        complaint_id = complaint_id,
        title        = complaint.get("title", "Your complaint"),
        old_status   = old_status,
        new_status   = new_status,
    )

    return {"status": "success"}
# ---------------- get stat of Complaints ----------------
def get_user_complaint_stats(user_id):

    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }
        }
    ]

    result = list(complaints_col.aggregate(pipeline))

    stats = {
        "total": 0,
        "resolved": 0,
        "in_progress": 0,
        "pending": 0
    }

    for row in result:
        status = row["_id"]
        count = row["count"]

        stats["total"] += count

        if status in stats:
            stats[status] = count

    return stats

def get_complaints_by_user(user_id):

    complaints = list(
        complaints_col.find({"user_id": user_id})
        .sort("created_at", -1)
    )

    return complaints


def get_all_departments():
    """Return all unique department names from the complaints collection."""
    return sorted(complaints_col.distinct("department"))
# ---------------- Notifications ----------------

STATUS_LABELS = {
    "pending":     "🔴 Pending",
    "in_progress": "🟡 In Progress",
    "resolved":    "✅ Resolved",
    "rejected":    "❌ Rejected",
}

def _create_status_notification(user_id, complaint_id, title, old_status, new_status):
    """Insert a notification document for a citizen."""
    notifications_col.insert_one({
        "_id":          str(uuid.uuid4()),
        "user_id":      user_id,
        "complaint_id": str(complaint_id),
        "title":        title,
        "old_status":   old_status,
        "new_status":   new_status,
        "read":         False,
        "created_at":   datetime.utcnow(),
    })


def get_notifications(user_id: str) -> list:
    """Return all notifications for a user, newest first."""
    return list(
        notifications_col.find({"user_id": user_id})
        .sort("created_at", -1)
    )


def get_unread_count(user_id: str) -> int:
    """Return count of unread notifications."""
    return notifications_col.count_documents({"user_id": user_id, "read": False})


def mark_all_notifications_read(user_id: str):
    """Mark every notification for this user as read."""
    notifications_col.update_many(
        {"user_id": user_id, "read": False},
        {"$set": {"read": True}}
    )

# ---------------- Security Audit Logs ----------------

def insert_security_log(event: str, details: str = ""):
    """Insert a security audit log entry into MongoDB."""
    security_logs_col.insert_one({
        "_id": str(uuid.uuid4()),
        "event": event,
        "details": details,
        "timestamp": datetime.utcnow()
    })