from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "ai_civic")

def init_db():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # Just test connection instead of creating collections
    client.admin.command("ping")

    print("✅ MongoDB connected successfully!")

if __name__ == "__main__":
    init_db()