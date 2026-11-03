"""Missing data raises no error: reconcile usage against billing, at the right level.

Ten sites send usage records (what the network carried) and billing records (what
we charged). A small share of usage is never billed on purpose (free calls, test
traffic), so billed / usage normally sits around 97%.

On one day, one site's billing feed delivers only 15% of its records. Nothing
fails: the loader loads what arrived, every query runs, every total adds up.

The script runs the same reconciliation twice:
  1. network-wide, for the whole week   -> looks fine
  2. per site, per day                  -> finds the gap and prices it

Python standard library only (sqlite3), made-up data, no installs.
"""

import random
import sqlite3

SITES = ["North", "South", "East", "West", "Harbor", "Airport", "Downtown", "Valley", "Ridge", "Lakeside"]
DAYS = 7
RECORDS_PER_SITE_DAY = 200
FREE_SHARE = 0.03          # usage that is never billed, by design
NETWORK_TOLERANCE = 0.95   # alert if billed / usage falls below this, network-wide
SITE_DAY_TOLERANCE = 0.90  # wider: one site-day is a small sample, so it is noisier
FAULT = {"site": "East", "day": 5, "delivered": 0.15}   # the feed that half-arrived


def build(db: sqlite3.Connection, rng: random.Random) -> None:
    db.execute("CREATE TABLE usage  (record_id INTEGER, site TEXT, day INTEGER, amount REAL)")
    db.execute("CREATE TABLE billed (record_id INTEGER, site TEXT, day INTEGER, amount REAL)")
    record_id = 0
    for day in range(1, DAYS + 1):
        for site in SITES:
            for _ in range(RECORDS_PER_SITE_DAY):
                record_id += 1
                amount = round(rng.uniform(0.20, 3.00), 2)
                db.execute("INSERT INTO usage VALUES (?, ?, ?, ?)", (record_id, site, day, amount))
                if rng.random() < FREE_SHARE:
                    continue  # free or test traffic: never billed, and that's correct
                faulty = site == FAULT["site"] and day == FAULT["day"]
                if faulty and rng.random() > FAULT["delivered"]:
                    continue  # the billing feed lost this record; nothing reports it
                db.execute("INSERT INTO billed VALUES (?, ?, ?, ?)", (record_id, site, day, amount))


def network_check(db: sqlite3.Connection) -> None:
    usage, billed = db.execute(
        "SELECT (SELECT SUM(amount) FROM usage), (SELECT SUM(amount) FROM billed)").fetchone()
    ratio = billed / usage
    status = "PASS" if ratio >= NETWORK_TOLERANCE else "ALERT"
    print(f"1) Network-wide, whole week (tolerance {NETWORK_TOLERANCE:.0%})")
    print(f"   usage {usage:>10,.2f}   billed {billed:>10,.2f}   billed/usage {ratio:.1%}   -> {status}")
    print("   Every total adds up and the ratio is inside tolerance. Nothing looks wrong.\n")


def per_site_check(db: sqlite3.Connection) -> None:
    rows = db.execute("""
        SELECT u.site, u.day, u.total AS usage, COALESCE(b.total, 0) AS billed
        FROM (SELECT site, day, SUM(amount) AS total FROM usage  GROUP BY site, day) u
        LEFT JOIN (SELECT site, day, SUM(amount) AS total FROM billed GROUP BY site, day) b
          ON b.site = u.site AND b.day = u.day
        ORDER BY u.day, u.site
    """).fetchall()
    print(f"2) Per site, per day ({len(rows)} site-days, tolerance {SITE_DAY_TOLERANCE:.0%})")
    flagged = [(site, day, usage, billed) for site, day, usage, billed in rows if billed / usage < SITE_DAY_TOLERANCE]
    for site, day, usage, billed in flagged:
        expected = usage * (1 - FREE_SHARE)
        print(f"   ALERT  {site:<9} day {day}   usage {usage:>7,.2f}   billed {billed:>7,.2f}"
              f"   billed/usage {billed / usage:.1%}   unbilled ~{expected - billed:,.2f}")
    if not flagged:
        print("   all site-days inside tolerance")
    print(f"   {len(rows) - len(flagged)} site-days pass, {len(flagged)} flagged.\n")


def main() -> None:
    db = sqlite3.connect(":memory:")
    build(db, random.Random(42))
    print("Usage vs billing, 10 sites x 7 days. One billing feed delivered 15% of a day.\n")
    network_check(db)
    per_site_check(db)
    print("Same data, same rule. The level you reconcile at decides whether the gap exists.")


if __name__ == "__main__":
    main()
