# set_admin_password.py (simplified)
import bcrypt
import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

admin_email = "admin@gmail.com"
admin_password = "admin123"  # Choose your password

# Hash the password
pw_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()

conn = mysql.connector.connect(
    host=DB_HOST,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME
)
cur = conn.cursor()
cur.execute(
    "UPDATE users SET password_hash=%s, role='admin' WHERE email=%s",
    (pw_hash, admin_email)
)
conn.commit()
conn.close()
print(f"✅ Admin password set for {admin_email}")
