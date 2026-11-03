"""Grain first: the join that quietly multiplies your revenue.

Two tables, two grains:
  calls     one row per call             (customer, month, call_id, rated_amount)
  invoices  one row per customer-month   (customer, month, invoiced_total)

Revenue assurance asks a simple question per customer-month: did we invoice what
we rated? The tempting query joins the two tables and sums both sides. It runs,
returns plausible numbers, and is wrong: each invoice row is repeated once per
call, so invoiced_total is multiplied by the number of calls.

The fix is to bring both sides to the same grain *before* joining.

Python standard library only (sqlite3), made-up data, no installs.
"""

import random
import sqlite3


def build(db: sqlite3.Connection, rng: random.Random) -> None:
    db.execute("CREATE TABLE calls (call_id INTEGER, customer TEXT, month TEXT, rated_amount REAL)")
    db.execute("CREATE TABLE invoices (customer TEXT, month TEXT, invoiced_total REAL)")
    call_id = 0
    for customer, calls_in_month, under_invoiced in [("C-101", 3, 0.0), ("C-102", 5, 0.0), ("C-103", 4, 6.00)]:
        rated = 0.0
        for _ in range(calls_in_month):
            call_id += 1
            amount = round(rng.uniform(1.0, 9.0), 2)
            rated += amount
            db.execute("INSERT INTO calls VALUES (?, ?, '2026-10', ?)", (call_id, customer, amount))
        # C-103 was invoiced 6.00 less than it was rated: the leak we want to find
        db.execute("INSERT INTO invoices VALUES (?, '2026-10', ?)", (customer, round(rated - under_invoiced, 2)))


def show(title: str, rows: list[tuple]) -> None:
    print(title)
    print(f"   {'customer':<9}{'rated':>9}{'invoiced':>10}{'gap':>9}")
    for customer, rated, invoiced in rows:
        gap = rated - invoiced
        flag = "   <- gap" if abs(gap) > 0.005 else ""
        print(f"   {customer:<9}{rated:>9.2f}{invoiced:>10.2f}{gap:>9.2f}{flag}")
    print()


def main() -> None:
    db = sqlite3.connect(":memory:")
    build(db, random.Random(7))

    wrong = db.execute("""
        SELECT c.customer, SUM(c.rated_amount), SUM(i.invoiced_total)
        FROM calls c
        JOIN invoices i ON i.customer = c.customer AND i.month = c.month
        GROUP BY c.customer ORDER BY c.customer
    """).fetchall()
    show("1) Join first, then sum (call grain meets customer-month grain)", wrong)
    print("   Every customer looks over-invoiced, by a different multiple. The real leak (C-103)")
    print("   is buried: its invoice was counted 4 times, once per call.\n")

    right = db.execute("""
        WITH rated AS (
            SELECT customer, month, SUM(rated_amount) AS rated
            FROM calls GROUP BY customer, month          -- now one row per customer-month
        )
        SELECT r.customer, r.rated, i.invoiced_total
        FROM rated r
        JOIN invoices i ON i.customer = r.customer AND i.month = r.month
        ORDER BY r.customer
    """).fetchall()
    show("2) Sum to the same grain first, then join", right)
    print("   One customer-month per row on both sides. The only gap left is the real one.")

    fanout = db.execute("""
        SELECT COUNT(*) FROM calls c JOIN invoices i ON i.customer = c.customer AND i.month = c.month
    """).fetchone()[0]
    invoices = db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    print(f"\nCheck that would have caught it: invoiced_total was summed over {fanout} rows,")
    print(f"but there are only {invoices} invoices. Decide which grain each sum belongs to, then")
    print("count rows before and after the join to prove it stayed there.")


if __name__ == "__main__":
    main()
