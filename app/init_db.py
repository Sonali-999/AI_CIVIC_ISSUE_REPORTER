# init_db.py
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# ---------------- Load environment ----------------
load_dotenv()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "ai_civic_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Sonali@2005")
DB_NAME = os.getenv("DB_NAME", "ai_civic")

# ---------------- Initialize DB ----------------
def init_db():
    try:
        # Connect to MySQL server (without specifying DB)
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()

        # 1️ Create database if not exists
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        cursor.execute(f"USE {DB_NAME}")

        # 2️ Create users table if not exists
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(36) PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role ENUM('citizen','admin') DEFAULT 'citizen',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 3️ Create complaints table if not exists
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            title VARCHAR(255) NOT NULL,
            category VARCHAR(100) NOT NULL,
            department VARCHAR(100) NOT NULL,
            description TEXT NOT NULL,
            image_path VARCHAR(255),
            status ENUM('pending','in_progress','resolved') DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        conn.commit()
        print("✅ Database and tables initialized successfully!")

    except Error as e:
        print("❌ Error initializing DB:", e)

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    init_db()
