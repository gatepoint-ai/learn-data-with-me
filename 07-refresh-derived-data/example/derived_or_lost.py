"""Derived data: refresh it, don't migrate it.

Two dumps of the same database, taken months apart. The newer one is smaller
but has more objects. Is data missing?

The script compares the two object inventories and sorts every difference:
  base table missing        -> real data loss, stop
  new partition             -> expected growth
  materialized view data    -> derived: rebuilt with REFRESH after the restore

Then it shows why derived data doesn't need migrating: an aggregate rebuilt
from the base table matches the copied one exactly.

Python standard library only (sqlite3), made-up data, no installs.
"""

import random
import sqlite3

# object -> (kind, size in MB). Made-up inventories.
VALIDATION_DUMP = {
    "billing.invoices":            ("table", 52_000),
    "billing.usage_2026_05":       ("partition", 9_800),
    "billing.usage_2026_06":       ("partition", 10_100),
    "reporting.daily_revenue_mv":  ("matview_data", 4_000),
    "reporting.monthly_usage_mv":  ("matview_data", 9_000),
    "reporting.legacy_kpis_mv":    ("matview_data", 14_000),
}
CUTOVER_DUMP = {
    "billing.invoices":            ("table", 52_400),
    "billing.usage_2026_05":       ("partition", 9_800),
    "billing.usage_2026_06":       ("partition", 10_100),
    "billing.usage_2026_07":       ("partition", 5_000),
    "billing.usage_2026_08":       ("partition", 4_800),
    "billing.usage_2026_09":       ("partition", 2_000),
    "reporting.daily_revenue_mv":  ("matview_data", 4_100),
}
# what the owners did between the two dumps (from their change log, not a guess)
HOUSEKEEPING = {"reporting.monthly_usage_mv", "reporting.legacy_kpis_mv"}


def compare() -> None:
    old_size = sum(s for _, s in VALIDATION_DUMP.values())
    new_size = sum(s for _, s in CUTOVER_DUMP.values())
    print(f"Validation dump: {len(VALIDATION_DUMP)} objects, {old_size / 1000:6.1f} GB")
    print(f"Cutover dump:    {len(CUTOVER_DUMP)} objects, {new_size / 1000:6.1f} GB"
          f"   <- {len(CUTOVER_DUMP) - len(VALIDATION_DUMP):+d} objects, {(new_size - old_size) / 1000:+.1f} GB\n")

    stop = False
    for name in sorted(VALIDATION_DUMP.keys() - CUTOVER_DUMP.keys()):
        kind = VALIDATION_DUMP[name][0]
        if kind == "matview_data":
            why = "dropped by housekeeping" if name in HOUSEKEEPING else "UNEXPLAINED, ask the owner"
            print(f"   gone   {name:28} {kind:13} derived: {why}")
        else:
            stop = True
            print(f"   gone   {name:28} {kind:13} BASE DATA MISSING, stop the cutover")
    for name in sorted(CUTOVER_DUMP.keys() - VALIDATION_DUMP.keys()):
        kind = CUTOVER_DUMP[name][0]
        print(f"   new    {name:28} {kind:13} {'expected: a new month' if kind == 'partition' else 'check it'}")

    base_old = {n: s for n, (k, s) in VALIDATION_DUMP.items() if k != "matview_data"}
    base_new = {n: s for n, (k, s) in CUTOVER_DUMP.items() if k != "matview_data"}
    shrunk = [n for n in base_old if n in base_new and base_new[n] < base_old[n]]
    print(f"\n   Base tables missing: {0 if not stop else 'SOME'}   base tables that shrank: {len(shrunk)}")
    print("   Verdict:", "STOP" if stop or shrunk else "no base data lost. The smaller dump is derived data that was dropped.")


def rebuild_matches_copy() -> None:
    db = sqlite3.connect(":memory:")
    rng = random.Random(7)
    db.execute("CREATE TABLE usage (day TEXT, site TEXT, amount REAL)")
    db.executemany("INSERT INTO usage VALUES (?, ?, ?)",
                   [(f"2026-10-{d:02}", s, round(rng.uniform(1, 9), 2))
                    for d in range(1, 31) for s in ("North", "South", "East") for _ in range(20)])
    aggregate = "SELECT day, site, ROUND(SUM(amount), 2) FROM usage GROUP BY day, site ORDER BY day, site"
    copied = db.execute(aggregate).fetchall()      # what a migration would have dumped and moved
    db.execute("CREATE TABLE daily_revenue AS " + aggregate.replace("ROUND(SUM(amount), 2)", "ROUND(SUM(amount), 2) AS revenue"))
    rebuilt = db.execute("SELECT * FROM daily_revenue ORDER BY day, site").fetchall()  # rebuilt on the target
    print(f"\nAggregate copied: {len(copied)} rows. Aggregate rebuilt from the base table: {len(rebuilt)} rows.")
    print("   identical:", copied == rebuilt)


if __name__ == "__main__":
    compare()
    rebuild_matches_copy()
    print("\nMigrate the base tables and the definitions. Rebuild the rest on the target.")
