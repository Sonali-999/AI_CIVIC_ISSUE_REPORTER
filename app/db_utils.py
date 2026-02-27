"""
DB helpers for users and complaints using MongoDB.
"""
import os
from dotenv import load_dotenv
from pymongo import MongoClient
import bcrypt
import uuid
from datetime import datetime

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "ai_civic")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

users_col = db["users"]
complaints_col = db["complaints"]

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

    complaints_col.insert_one({
        "user_id": user_id,
        "title": title,
        "category": category,
        "department": department,
        "description": description,
        "image_path": image_path,
        "status": status,
        "created_at": datetime.utcnow()
    })


def get_complaints_by_department(dept):
    dept = dept.strip().title()

    complaints = list(
        complaints_col.find({"department": dept})
        .sort("created_at", -1)
    )

    return complaints