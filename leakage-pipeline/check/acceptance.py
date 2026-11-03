#!/usr/bin/env python3
"""Acceptance check: did the pipeline find every planted leak, and nothing else?

Reads data/faults.json (written by the generator) and the three marts in the
DuckDB file that dbt builds. Passes only if:
  - every fault is flagged where the manifest says,
  - every control stays quiet,
  - no flag exists that the manifest can't explain.

Zero flags is a failure, not a pass: "found nothing" and "broken" look identical.

Needs the duckdb Python package (installed with dbt-duckdb).

Usage:
    python check/acceptance.py
    python check/acceptance.py --db dbt/leakage.duckdb --manifest data/faults.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARTS = ["mart_unbilled_usage", "mart_rating_variance", "mart_duplicate_billing"]


def d(value) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)[:10]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=ROOT / "dbt" / "leakage.duckdb")
    ap.add_argument("--manifest", type=Path, default=ROOT / "data" / "faults.json")
    a = ap.parse_args(argv)

    if not a.manifest.exists():
        print(f"no manifest at {a.manifest}. Run: python generate/generate.py")
        return 2
    try:
        import duckdb
    except ImportError:
        print("the duckdb package is missing. Install dbt-duckdb (it brings duckdb), or: pip install duckdb")
        return 2
    if not a.db.exists():
        print(f"no marts yet: {a.db} doesn't exist. Build them with `dbt build` in dbt/ (see SPEC.md).")
        return 2

    con = duckdb.connect(str(a.db), read_only=True)
    present = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    missing = [m for m in MARTS if m not in present]
    if missing:
        print(f"no marts yet: {', '.join(missing)} not found in {a.db.name} (see SPEC.md for the contract).")
        return 2

    manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
    unbilled = con.execute("SELECT site, usage_date, expected_amount, is_flagged FROM mart_unbilled_usage").fetchall()
    rating = con.execute("SELECT product_code, usage_date, is_flagged FROM mart_rating_variance").fetchall()
    dups = con.execute("SELECT customer_id, usage_date, times_billed FROM mart_duplicate_billing").fetchall()

    flagged_unbilled = {(s, d(day)) for s, day, _, f in unbilled if f}
    flagged_rating = {(p, d(day)) for p, day, f in rating if f}
    flagged_dups = {(c, d(day)) for c, day, n in dups if n >= 2}
    explained: set[tuple[str, str, str]] = set()
    results = []

    for f in manifest["faults"]:
        if f["id"] == "unbilled_site":
            key = (f["site"], f["usage_date"])
            ok = key in flagged_unbilled
            explained.add(("unbilled",) + key)
        elif f["id"] == "misrating":
            keys = [(f["product_code"], day) for day in f["usage_dates"]]
            ok = all(k in flagged_rating for k in keys)
            explained.update(("rating",) + k for k in keys)
        elif f["id"] == "duplicate_billing":
            key = (f["customer_id"], f["usage_date"])
            ok = key in flagged_dups
            explained.add(("dups",) + key)
        else:
            ok = False
        results.append(("fault", f["id"], ok, f["detail"]))

    for c in manifest["controls"]:
        if c["id"] == "late_arrival":
            rows = [r for r in unbilled if r[0] == c["site"] and d(r[1]) == c["usage_date"]]
            site_amounts = sorted(r[2] for r in unbilled if r[0] == c["site"])
            median = site_amounts[len(site_amounts) // 2] if site_amounts else 0
            ok = bool(rows) and not rows[0][3] and rows[0][2] >= 0.5 * median
        elif c["id"] == "systemic_dip":
            ok = not any(day == c["usage_date"] for _, day in flagged_unbilled)
        elif c["id"] == "zero_rated":
            ok = not any(p == c["product_code"] for p, _ in flagged_rating)
        else:
            ok = False
        results.append(("control", c["id"], ok, c["detail"]))

    unexplained = sorted(
        [("unbilled",) + k for k in flagged_unbilled if ("unbilled",) + k not in explained]
        + [("rating",) + k for k in flagged_rating if ("rating",) + k not in explained]
        + [("dups",) + k for k in flagged_dups if ("dups",) + k not in explained])

    for kind, name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {kind:<8} {name:<18} {detail}")
    print(f"{'PASS' if not unexplained else 'FAIL'}  unexplained flags: {len(unexplained)}")
    for u in unexplained[:10]:
        print(f"      {u}")

    passed = all(ok for *_, ok, _ in results) and not unexplained
    print("\nACCEPTANCE: PASS" if passed else "\nACCEPTANCE: FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
