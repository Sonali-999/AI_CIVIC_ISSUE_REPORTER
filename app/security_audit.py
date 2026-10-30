"""
security_audit.py
-----------------
Tamper-evident security audit log.

Every security-relevant event is written to two independent sinks - the
filesystem and MongoDB - so compromising one storage layer does not erase the
trail.

HASH CHAINING (Eq. 21)
======================
Each entry is bound to its predecessor:

    h_i = SHA-256( h_{i-1} || event_i || timestamp_i || details_i )

Because every entry's hash feeds the next one, deleting, reordering or editing
any historical entry invalidates every hash after it. An attacker who edits one
line must recompute the entire remainder of the chain - and a verifier who kept
a copy of the current head hash will still detect it.

Log line format:

    <timestamp> | <event> | <details> | <hash>

verify_chain() recomputes the whole file and reports the first entry that does
not match. Entries written before chaining was introduced have no hash field;
they are reported as legacy rather than as tampering.
"""

from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "security.log")

os.makedirs(LOG_DIR, exist_ok=True)

# Chain anchor. The first hashed entry is bound to this constant, so an
# attacker cannot simply truncate the log and start a fresh valid chain
# without the difference being visible.
GENESIS_HASH = hashlib.sha256(b"CIVICAI-AUDIT-GENESIS-v1").hexdigest()

# Serialises read-modify-write of the chain head across Gradio's worker threads;
# two concurrent events must not compute their hash from the same predecessor.
_chain_lock = threading.Lock()


def _entry_hash(prev_hash: str, event: str, timestamp: str, details: str) -> str:
    """Eq. 21 - bind this entry to its predecessor."""
    payload = f"{prev_hash}|{event}|{timestamp}|{details}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parse_line(line: str) -> tuple[str, str, str, str] | None:
    """Split a log line into (timestamp, event, details, hash). Hash may be ''."""
    parts = [p.strip() for p in line.rstrip("\n").split("|")]
    if len(parts) == 4:
        return parts[0], parts[1], parts[2], parts[3]
    if len(parts) == 3:                    # legacy entry, written before chaining
        return parts[0], parts[1], parts[2], ""
    return None


def _current_head() -> str:
    """The hash of the most recent chained entry, or the genesis anchor."""
    if not os.path.exists(LOG_FILE):
        return GENESIS_HASH

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in reversed(lines):
        parsed = _parse_line(line)
        if parsed and parsed[3]:
            return parsed[3]

    return GENESIS_HASH


def log_security_event(event: str, details: str = "") -> str:
    """
    Record one security event to both sinks and return its chain hash.

    Never raises - a logging failure must not take down complaint submission -
    but a failure to write the file is reported on stdout because a silent
    audit-log outage would defeat the point of having one.
    """
    timestamp = datetime.utcnow().isoformat()
    # Pipes would corrupt the field separator when the chain is re-parsed.
    details = str(details).replace("|", "/")

    with _chain_lock:
        prev_hash = _current_head()
        entry_hash = _entry_hash(prev_hash, event, timestamp, details)

        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} | {event} | {details} | {entry_hash}\n")
        except OSError as exc:
            print(f"[security_audit] FILE WRITE FAILED for {event}: {exc}")

    # Lazy import breaks the circular dependency: db_utils imports this module.
    try:
        from .db_utils import insert_security_log
        insert_security_log(event, details, entry_hash=entry_hash, prev_hash=prev_hash)
    except Exception as exc:
        print(f"[security_audit] DB write failed: {exc}")

    return entry_hash


def verify_chain() -> dict:
    """
    Recompute the whole chain and report the first break.

    Returns
    -------
    dict with: valid, total_entries, chained_entries, legacy_entries,
               first_invalid_line, head_hash, message
    """
    if not os.path.exists(LOG_FILE):
        return {
            "valid": True, "total_entries": 0, "chained_entries": 0,
            "legacy_entries": 0, "first_invalid_line": None,
            "head_hash": GENESIS_HASH, "message": "No audit log yet",
        }

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    prev_hash = GENESIS_HASH
    total = chained = legacy = 0
    first_invalid = None

    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        parsed = _parse_line(line)
        if not parsed:
            continue

        total += 1
        timestamp, event, details, stored_hash = parsed

        if not stored_hash:
            legacy += 1
            continue

        expected = _entry_hash(prev_hash, event, timestamp, details)
        if expected != stored_hash and first_invalid is None:
            first_invalid = line_no

        chained += 1
        # Continue from the stored hash so one bad entry does not cascade into
        # reporting every subsequent line as broken too.
        prev_hash = stored_hash

    valid = first_invalid is None
    if valid:
        message = f"Chain intact across {chained} entries"
        if legacy:
            message += f" ({legacy} legacy entries predate chaining)"
    else:
        message = f"CHAIN BROKEN - entry on line {first_invalid} was altered or removed"

    return {
        "valid": valid,
        "total_entries": total,
        "chained_entries": chained,
        "legacy_entries": legacy,
        "first_invalid_line": first_invalid,
        "head_hash": prev_hash,
        "message": message,
    }


# ── DEMO ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 68)
    print("  Tamper-Evident Audit Log  -  hash chaining (Eq. 21)")
    print("=" * 68)

    h1 = log_security_event("DEMO_EVENT", "first entry")
    h2 = log_security_event("DEMO_EVENT", "second entry")
    print(f"\n  Entry 1 hash: {h1[:48]}...")
    print(f"  Entry 2 hash: {h2[:48]}...")
    print("  (entry 2's hash is computed over entry 1's hash)")

    result = verify_chain()
    print(f"\n  Verification: {result['message']}")
    print(f"  Entries      : {result['total_entries']} "
          f"({result['chained_entries']} chained, {result['legacy_entries']} legacy)")
    print(f"  Head hash    : {result['head_hash'][:48]}...")
    print("\n  Try editing any line in logs/security.log, then re-run this")
    print("  script - verification will name the line that changed.")
    print("=" * 68)
