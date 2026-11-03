"""Re-runnable by design: every step can run twice and leave the same result.

Long pipelines and migrations fail halfway: a dropped connection, a lock, a full
disk. The question is what happens when you run the step again.

Part 1 loads the same daily file twice, two ways:
  append      INSERT the rows               -> the re-run doubles the day
  idempotent  replace the day, keep a ledger -> the re-run changes nothing

Part 2 picks "the latest backup" two ways:
  by name     sort folder names, take the last -> alphabetical, not newest
  by time     sort by creation time            -> newest, and it says which

Python standard library only (sqlite3), made-up data, no installs.
"""

import hashlib
import sqlite3
from datetime import datetime

DAILY_FILE = {"name": "usage_2026-11-02.csv", "day": "2026-11-02",
              "rows": [("r1", 4.10), ("r2", 2.75), ("r3", 9.00)]}


def checksum(f: dict) -> str:
    return hashlib.sha256(repr(f["rows"]).encode()).hexdigest()[:12]


def load_append(db: sqlite3.Connection, f: dict) -> None:
    db.executemany("INSERT INTO usage (day, record_id, amount) VALUES (?, ?, ?)",
                   [(f["day"], rid, amt) for rid, amt in f["rows"]])


def load_idempotent(db: sqlite3.Connection, f: dict) -> str:
    done = db.execute("SELECT 1 FROM load_ledger WHERE file = ? AND checksum = ?",
                      (f["name"], checksum(f))).fetchone()
    if done:
        return "skipped: already loaded with this checksum"
    with db:  # one transaction: the day is replaced completely or not at all
        db.execute("DELETE FROM usage WHERE day = ?", (f["day"],))
        load_append(db, f)
        db.execute("INSERT INTO load_ledger VALUES (?, ?, ?)", (f["name"], checksum(f), datetime.now().isoformat()))
    return "loaded"


def fresh_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE usage (day TEXT, record_id TEXT, amount REAL)")
    db.execute("CREATE TABLE load_ledger (file TEXT, checksum TEXT, loaded_at TEXT)")
    return db


def total(db: sqlite3.Connection) -> str:
    rows, amount = db.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM usage").fetchone()
    return f"{rows} rows, {amount:.2f}"


def part1() -> None:
    print("Part 1: load the same file, then run the step again after a 'failure'")
    db = fresh_db()
    load_append(db, DAILY_FILE)
    load_append(db, DAILY_FILE)
    print(f"   append:      run 1 + run 2 -> {total(db)}   <- the day is counted twice")
    db = fresh_db()
    first = load_idempotent(db, DAILY_FILE)
    second = load_idempotent(db, DAILY_FILE)
    print(f"   idempotent:  run 1 {first}; run 2 {second} -> {total(db)}")


def part2() -> None:
    print("\nPart 2: pick the latest backup folder")
    backups = {  # folder name -> when it was created
        "2026-10-30_cutover": datetime(2026, 10, 30, 6, 2),
        "june-rollback-copy": datetime(2026, 6, 14, 23, 40),
    }
    by_name = sorted(backups)[-1]
    by_time = max(backups, key=backups.get)
    print(f"   by name (ls | tail -1):    {by_name}   created {backups[by_name]:%d %b %Y}   <- the old one")
    print(f"   by time (ls -t | head -1): {by_time}   created {backups[by_time]:%d %b %Y}")
    print("   Digits sort before letters. The script that sorts by name would verify and")
    print("   upload the old backup, and report success.")


if __name__ == "__main__":
    part1()
    part2()
    print("\nBoth bugs finish with exit code 0. Only the design makes a re-run safe.")
