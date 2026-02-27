# set_admin_password.py (MongoDB version)

import bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "ai_civic")

admin_email = "admin@gmail.com"
admin_password = "admin123"  # Choose your password

# Hash password
pw_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_col = db["users"]

# Update admin user
result = users_col.update_one(
    {"email": admin_email},
    {
        "$set": {
            "password_hash": pw_hash,
            "role": "admin",
            "updated_at": datetime.utcnow()
        }
    }
)

if result.matched_count == 0:
    print("❌ Admin email not found in database.")
else:
    print(f"✅ Admin password set for {admin_email}")