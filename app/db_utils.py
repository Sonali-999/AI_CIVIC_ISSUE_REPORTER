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

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "ai_civic")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

users_col         = db["users"]
complaints_col    = db["complaints"]
notifications_col = db["notifications"]

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


# ---------------- Complaints ----------------

def save_complaint(user_id, title, category, department, description, image_path, status="pending"):
    department = department.strip().title()

    result = complaints_col.insert_one({
        "user_id": user_id,
        "title": title,
        "category": category,
        "department": department,
        "description": description,
        "image_path": image_path,
        "status": status,
        "created_at": datetime.utcnow()
    })
    return str(result.inserted_id)


def get_complaints_by_department(dept):
    dept = dept.strip().title()

    complaints = list(
        complaints_col.find({"department": dept})
        .sort("created_at", -1)
    )

    return complaints


def get_all_complaints():
    """Return all complaints sorted newest first."""
    return list(complaints_col.find().sort("created_at", -1))


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

    complaints_col.update_one(query, {"$set": {
        "status": new_status,
        "updated_at": datetime.utcnow()
    }})

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