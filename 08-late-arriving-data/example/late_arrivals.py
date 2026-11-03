"""Late-arriving data: count by event date, re-process a window, close days late.

Three sites, ten days of usage. One site's feed for days 4 and 5 arrives two
days late. Nothing is lost: every record does arrive, eventually.

Three ways to build the daily table:
  1) by arrival date         -> a false gap, then a false surplus
  2) by event date, but the incremental load only takes days after the
     high-water mark         -> the late rows are skipped for good
  3) by event date, re-processing a window behind the high-water mark
                             -> correct, once the window has passed

Python standard library only (sqlite3), made-up data, no installs.
"""

import sqlite3

SITES = ("North", "South", "East")
DAYS = range(1, 11)
LATE = {("South", 4): 2, ("South", 5): 2}  # (site, event day) -> days late
LOOKBACK_DAYS = 3


def build_source(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE raw_usage (record_id INTEGER, site TEXT, event_day INTEGER, arrival_day INTEGER, amount REAL)")
    rid = 0
    for day in DAYS:
        for site in SITES:
            for _ in range(10):
                rid += 1
                db.execute("INSERT INTO raw_usage VALUES (?, ?, ?, ?, 10.0)",
                           (rid, site, day, day + LATE.get((site, day), 0)))


def by_arrival(db: sqlite3.Connection) -> dict:
    return dict(db.execute("SELECT arrival_day, SUM(amount) FROM raw_usage WHERE arrival_day <= 10 GROUP BY 1").fetchall())


def incremental(db: sqlite3.Connection, lookback: int) -> dict:
    """Run the daily job on days 1..10. Each run sees only what has arrived by then."""
    db.execute("DROP TABLE IF EXISTS fct_usage")
    db.execute("CREATE TABLE fct_usage (record_id INTEGER PRIMARY KEY, event_day INTEGER, amount REAL)")
    for run_day in DAYS:
        high_water = db.execute("SELECT COALESCE(MAX(event_day), 0) FROM fct_usage").fetchone()[0]
        start = high_water - lookback + 1 if lookback else high_water + 1
        with db:
            db.execute("DELETE FROM fct_usage WHERE event_day >= ?", (start,))
            db.execute("""INSERT INTO fct_usage
                          SELECT record_id, event_day, amount FROM raw_usage
                          WHERE event_day >= ? AND arrival_day <= ?""", (start, run_day))
    return dict(db.execute("SELECT event_day, SUM(amount) FROM fct_usage GROUP BY 1").fetchall())


def show(title: str, totals: dict) -> None:
    expected = 10 * 10.0 * len(SITES)
    cells = []
    for d in DAYS:
        v = totals.get(d, 0.0)
        mark = "" if v == expected else ("-" if v < expected else "+")
        cells.append(f"{d}:{v:.0f}{mark}")
    wrong = sum(1 for d in DAYS if totals.get(d, 0.0) != expected)
    print(f"{title}\n   {'  '.join(cells)}\n   days wrong: {wrong}\n")


if __name__ == "__main__":
    db = sqlite3.connect(":memory:")
    build_source(db)
    print("Every day should total 300. '-' is short, '+' is over.\n")
    show("1) Counted by arrival date", by_arrival(db))
    show("2) By event date, incremental from the high-water mark", incremental(db, lookback=0))
    show(f"3) By event date, re-processing the last {LOOKBACK_DAYS} days on every run", incremental(db, lookback=LOOKBACK_DAYS))
    print("The late rows were never missing. Version 2 just stopped looking for them.")
