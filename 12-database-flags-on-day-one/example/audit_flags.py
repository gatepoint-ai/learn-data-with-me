"""Database flags on day one: audit an instance's settings against a baseline.

Logging you turn on after an incident can't explain that incident. This
script compares a database's settings with a baseline and says what each
missing setting would have told you.

Feed it the output of this query, saved as CSV (name,setting), or run it with
no arguments to audit a made-up instance that still has the defaults:

    SELECT name, setting FROM pg_settings WHERE name IN (...);

Python standard library only (csv), no installs.
"""

import csv
import sys

# name: (check, what you lose without it)
BASELINE = {
    "log_lock_waits":             (lambda v: v == "on",
                                   "which session blocked which, when a job hangs on a lock"),
    "log_temp_files":             (lambda v: v != "-1" and int(v) >= 0,
                                   "queries spilling sorts and hashes to disk (memory too small)"),
    "log_checkpoints":            (lambda v: v == "on",
                                   "write-ahead log pressure and checkpoint stalls"),
    "log_connections":            (lambda v: v == "on",
                                   "who connected, from where (audit, connection storms)"),
    "log_disconnections":         (lambda v: v == "on",
                                   "session length, and pools that leak connections"),
    "log_min_duration_statement": (lambda v: v != "-1",
                                   "the slow-query log: statements above a threshold, with timing"),
}

# PostgreSQL 16 defaults, as read from pg_settings on a fresh instance
DEFAULTS = {
    "log_lock_waits": "off", "log_temp_files": "-1", "log_checkpoints": "on",
    "log_connections": "off", "log_disconnections": "off", "log_min_duration_statement": "-1",
}


def load(path: str) -> dict:
    with open(path, newline="") as f:
        return {row["name"]: row["setting"] for row in csv.DictReader(f)}


if __name__ == "__main__":
    settings = load(sys.argv[1]) if len(sys.argv) > 1 else DEFAULTS
    print("Setting                      Value   Verdict")
    missing = 0
    for name, (ok, loses) in BASELINE.items():
        value = settings.get(name, "?")
        good = value != "?" and ok(value)
        missing += not good
        print(f"{name:28} {value:>6}   {'ok' if good else 'MISSING: you will not see ' + loses}")
    print(f"\n{missing} of {len(BASELINE)} missing. Set them when the instance is created, in code,"
          " not after the first incident.")
