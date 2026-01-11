"""DB helpers for users and complaints using mysql-connector."""
import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import bcrypt
import uuid

# Load .env
load_dotenv()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "ai_civic_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Sonali@2005")
DB_NAME = os.getenv("DB_NAME", "ai_civic")

# ---------------- DB Connection ----------------
def get_conn():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except Error as e:
        print("❌ DB connection failed:", e)
        raise

# ---------------- Initialize DB ----------------
def init_db(sql_file_path):
    sql = open(sql_file_path, "r", encoding="utf-8").read()
    conn = None
    try:
        # connect to server without specifying database to allow CREATE DATABASE
        conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
        cursor = conn.cursor()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                cursor.execute(stmt + ";")
        conn.commit()
    finally:
        if conn:
            conn.close()

# ---------------- Users ----------------
def register_user(email, password, role="citizen"):
    conn = get_conn()
    cur = conn.cursor()
    user_id = str(uuid.uuid4())
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        cur.execute(
            "INSERT INTO users (id, email, password_hash, role) VALUES (%s,%s,%s,%s)",
            (user_id, email, pw_hash, role)
        )
        conn.commit()
        return {"status": "success", "user_id": user_id}
    except Error as e:
        return {"status": "error", "error": str(e)}
    finally:
        cur.close(); conn.close()

def login_user(email, password):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash, role FROM users WHERE email=%s", (email,))
    row = cur.fetchone()
    cur.close(); conn.close()

    if not row:
        return {"status": "error", "error": "not_found"}

    user_id, pw_hash, role = row
    print("DEBUG: role from DB:", role)  # <-- debug print

    if bcrypt.checkpw(password.encode(), pw_hash.encode()):
        return {"status": "success", "user_id": user_id, "role": role}
    else:
        return {"status": "error", "error": "bad_credentials"}

# ---------------- Complaints ----------------
def save_complaint(user_id, title, category, department, description, image_path, status="pending"):
    conn = get_conn()
    cursor = conn.cursor()

    department = department.strip().title()  # Normalize

    sql = """
    INSERT INTO complaints (user_id, title, category, department, description, image_path, status)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(sql, (user_id, title, category, department, description, image_path, status))
    conn.commit()
    cursor.close(); conn.close()


def get_complaints_by_department(dept):
    conn = get_conn()
    cursor = conn.cursor()
    
    dept = dept.strip().title()  # Normalize
    sql = "SELECT * FROM complaints WHERE department=%s ORDER BY created_at DESC"
    cursor.execute(sql, (dept,))
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    print(f"✅ Fetched {len(rows)} complaints for {dept}")
    return rows
