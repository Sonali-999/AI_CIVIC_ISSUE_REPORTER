import bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime
import uuid

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "ai_civic")

admin_email = "admin@gmail.com"
admin_password = "admin123"

pw_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_col = db["users"]

existing = users_col.find_one({"email": admin_email})

if existing:
    users_col.update_one(
        {"email": admin_email},
        {
            "$set": {
                "password_hash": pw_hash,
                "role": "admin",
                "updated_at": datetime.utcnow()
            }
        }
    )
    print("✅ Admin updated.")
else:
    users_col.insert_one({
        "_id": str(uuid.uuid4()),
        "email": admin_email,
        "password_hash": pw_hash,
        "role": "admin",
        "created_at": datetime.utcnow()
    })
    print("✅ Admin created.")