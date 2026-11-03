"""Tests as controls: prove each one can fail, and make "no data" a failure.

Three controls, each a query that returns violations (zero rows = pass),
which is exactly how a dbt test works. They run against four datasets:

  clean       the normal day
  empty       the load failed and wrote nothing
  planted     one known fault per control, planted on purpose
  holiday     every site drops at once: a negative control that must stay quiet

The point: a control that passes on an empty table, or never fires on its own
planted fault, is reporting success it hasn't earned.

Python standard library only (sqlite3), made-up data, no installs.
"""

import sqlite3

SITES = ("North", "South", "East", "West")

CONTROLS = {
    # name: (query returning violations, the fault planted to prove it)
    "duplicate_billing": (
        "SELECT record_id FROM billed GROUP BY record_id HAVING COUNT(*) > 1",
        "bill one record twice"),
    "unbilled_site_day": (
        """SELECT u.site FROM (SELECT site, SUM(amount) a FROM usage GROUP BY site) u
           LEFT JOIN (SELECT site, SUM(amount) a FROM billed GROUP BY site) b ON b.site = u.site
           WHERE COALESCE(b.a, 0) < 0.90 * u.a""",
        "drop 85% of one site's billing"),
    "negative_charge": (
        # bug on purpose: ABS() makes the condition impossible, so this control can never fire
        "SELECT record_id FROM billed WHERE ABS(amount) < 0",
        "a negative charge"),
}

LOADED = "SELECT 'nothing loaded' WHERE NOT EXISTS (SELECT 1 FROM usage)"


def dataset(kind: str) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE usage (record_id INTEGER, site TEXT, amount REAL)")
    db.execute("CREATE TABLE billed (record_id INTEGER, site TEXT, amount REAL)")
    if kind == "empty":
        return db
    rid = 0
    for site in SITES:
        for _ in range(100):
            rid += 1
            amount = 3.0 if kind == "holiday" else 10.0    # holiday: every site down 70% together
            db.execute("INSERT INTO usage VALUES (?, ?, ?)", (rid, site, amount))
            if kind == "planted" and site == "South" and rid % 100 < 85:
                continue                                   # fault: South mostly unbilled
            db.execute("INSERT INTO billed VALUES (?, ?, ?)", (rid, site, amount))
    if kind == "planted":
        db.execute("INSERT INTO billed SELECT * FROM billed WHERE record_id = 1")   # fault: billed twice
        db.execute("INSERT INTO billed VALUES (9999, 'North', -10.0)")             # fault: negative charge
    return db


def run(kind: str, with_precondition: bool) -> dict:
    db = dataset(kind)
    results = {}
    for name, (sql, _) in CONTROLS.items():
        violations = len(db.execute(sql).fetchall())
        if with_precondition and db.execute(LOADED).fetchone():
            violations = max(violations, 1)
        results[name] = violations
    return results


if __name__ == "__main__":
    for precondition in (False, True):
        label = "with a 'something was loaded' precondition" if precondition else "as written"
        print(f"Controls {label}  (PASS = zero violations)")
        print(f"   {'dataset':10}" + "".join(f"{n:>20}" for n in CONTROLS))
        for kind in ("clean", "empty", "planted", "holiday"):
            res = run(kind, precondition)
            print(f"   {kind:10}" + "".join(f"{('PASS' if v == 0 else f'FAIL ({v})'):>20}" for v in res.values()))
        print()
    planted = run("planted", True)
    never = [n for n, v in planted.items() if v == 0]
    print("Planted-fault check: every control must FAIL on the 'planted' row.")
    print("   controls that never fired on their own fault:", ", ".join(never) or "none")
    print("   -> that control is broken, however green it has been in production.")
