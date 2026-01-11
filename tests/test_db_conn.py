# tests/test_db_conn.py
import os
from dotenv import load_dotenv
load_dotenv()  # <-- fix: call the function

from app.db_utils import register_user, login_user, save_complaint, get_complaints_by_department

# 1) register
res = register_user("tester@example.com", "test_password")
print("register:", res)

# 2) login
res2 = login_user("tester@example.com", "test_password")
print("login:", res2)

user_id = res2.get("user_id") if res2.get("status")=="success" else None
if user_id:
    # 3) save complaint
    r = save_complaint(
        user_id,
        "Garbage heap near bus stop",
        "Garbage",
        "Sanitation",
        "Large pile of wet garbage causing smell and attracting flies",
        "test.jpg"  # placeholder path
    )
    print("save complaint:", r)
    
    # 4) fetch complaints by department
    rows = get_complaints_by_department("Sanitation")
    print("complaints:", rows[:3])
else:
    print("⚠️ Login failed, skipping complaint save and fetch.")
