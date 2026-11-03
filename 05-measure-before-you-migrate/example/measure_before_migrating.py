"""Measure before you migrate: let the counters decide what's in scope.

Architecture diagrams describe what was intended. Traffic counters describe what
is actually used. Before migrating integrations, read the counters for a
representative period and sort every item into:

  live         traffic flowing            -> migrate, test, plan the cutover
  dormant      configured, zero traffic   -> confirm with the owner, then drop
  never wired  an object exists, nothing  -> drop
               is attached to it

The inventory below is made up. The same sort works for site-to-site links,
scheduled jobs, API consumers or tables (with read and write counters).

Python standard library only, no installs.
"""

import csv
import io

# 30 days of counters, as exported from the source cloud
INVENTORY = """name,kind,status,gb_in,gb_out,has_connection
Head office network,site-to-site,Connected,41.3,5.2,yes
Monitoring network,site-to-site,NotConnected,0,0,yes
Backup network,site-to-site,NotConnected,0,0,yes
Partner gateway,site-to-site,,0,0,no
Nightly export to finance,scheduled job,Enabled,0.0,12.4,yes
Legacy fax gateway feed,scheduled job,Enabled,0,0,yes
"""

# Each live item that moves costs work on both sides
WORK_PER_LIVE_ITEM = ["change request on the client side", "a team to coordinate", "a cutover test"]


def classify(row: dict) -> str:
    traffic = float(row["gb_in"] or 0) + float(row["gb_out"] or 0)
    if row["has_connection"] == "no":
        return "never wired"
    if traffic == 0:
        return "dormant"
    return "live"


def main() -> None:
    rows = list(csv.DictReader(io.StringIO(INVENTORY)))
    print(f"{'item':<27}{'kind':<15}{'status':<14}{'GB in':>7}{'GB out':>8}   verdict")
    verdicts = {}
    for row in rows:
        verdict = classify(row)
        verdicts.setdefault(verdict, []).append(row["name"])
        print(f"{row['name']:<27}{row['kind']:<15}{row['status'] or '-':<14}"
              f"{float(row['gb_in'] or 0):>7.1f}{float(row['gb_out'] or 0):>8.1f}   {verdict}")

    live = verdicts.get("live", [])
    out = verdicts.get("dormant", []) + verdicts.get("never wired", [])
    print(f"\nIn scope: {len(live)} of {len(rows)}  ->  {', '.join(live)}")
    print(f"Out of scope after the owner confirms: {len(out)}  ->  {', '.join(out)}")
    print(f"Work avoided: {len(out)} x ({', '.join(WORK_PER_LIVE_ITEM)})")
    print("\nNote: 'Enabled' with zero bytes is still dormant. Status says what is configured;")
    print("only the counters say what is used.")


if __name__ == "__main__":
    main()
