from datetime import datetime
import os

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "security.log")

os.makedirs(LOG_DIR, exist_ok=True)


def log_security_event(event, details=""):

    timestamp = datetime.utcnow().isoformat()

    log_line = f"{timestamp} | {event} | {details}\n"

    # Write to file
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line)

    # Lazy import to avoid circular dependency
    try:
        from .db_utils import insert_security_log
        insert_security_log(event, details)
    except Exception as e:
        print("Security log DB write failed:", e)