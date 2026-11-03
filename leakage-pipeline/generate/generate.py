#!/usr/bin/env python3
"""Generate synthetic telecom usage and billing data, with revenue leaks planted on purpose.

The pipeline's job is to find money that was earned and not billed. A generator
that produced clean data would prove only that the pipeline runs: "no leaks found"
and "reconciliation broken" look identical. So this script plants known faults and
writes a manifest, faults.json, that the acceptance check reads.

Files written to --out (default: ../data):
  customers.csv   one row per customer          customer_id, segment, home_site
  products.csv    one row per product           product_code, description, unit, rate
  usage.csv       one row per usage record      record_id, customer_id, product_code, site,
                                                event_ts, received_ts, units
  billed.csv      one row per bill line         bill_line_id, record_id, customer_id,
                                                product_code, bill_date, billed_amount
  faults.json     what was planted, and what the reconciliation must (or must not) flag

Planted faults (must be flagged)
  unbilled_site      one site, one day: ~85% of its billable records never reach billing
  misrating          one product billed at 80% of its rate for three days
  duplicate_billing  one customer, one day: every record billed twice

Controls (must NOT be flagged)
  late_arrival       one site, one day: usage arrives two days late, and is still billed in full
  systemic_dip       every site loses ~70% of its volume on one day, like a holiday:
                     usage and billing drop together, so nothing is unbilled
  zero_rated         a free product is never billed, by design, on every day

Deterministic: the same --seed and --days always produce the same files.

Usage:
    python generate.py                       # 30 days, seed 7, writes ../data
    python generate.py --days 60 --seed 11 --out /tmp/leakage
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

SITES = ["North", "South", "East", "West", "Harbor", "Airport", "Downtown", "Valley", "Ridge", "Lakeside"]
SEGMENTS = [("consumer", 0.75), ("business", 0.25)]
PRODUCTS = [  # code, description, unit, rate per unit
    ("VOICE", "Voice calls", "minute", 0.08),
    ("DATA", "Mobile data", "MB", 0.002),
    ("SMS", "Text messages", "message", 0.05),
    ("ROAM", "Roaming voice", "minute", 0.45),
    ("PROMO", "Promotional messages (free)", "message", 0.0),
]
PRODUCT_MIX = [("VOICE", 0.38), ("DATA", 0.37), ("SMS", 0.12), ("ROAM", 0.05), ("PROMO", 0.08)]
UNITS = {"VOICE": (1, 25), "DATA": (5, 900), "SMS": (1, 6), "ROAM": (1, 15), "PROMO": (1, 3)}
CUSTOMERS = 400
RECORDS_PER_SITE_DAY = 120
START = date(2026, 10, 1)


def pick(rng: random.Random, weighted: list[tuple[str, float]]) -> str:
    return rng.choices([k for k, _ in weighted], weights=[w for _, w in weighted])[0]


def plan_faults(days: list[date], rng: random.Random) -> dict:
    """Choose where each fault lands. Faults never share a day, so each one is unambiguous."""
    pool = days[3:-3]  # keep the edges clean so late arrivals stay inside the window
    chosen = rng.sample(pool, 6)
    sites = rng.sample(SITES, 3)
    misrating_start = chosen[1]
    return {
        "unbilled_site": {"site": sites[0], "date": chosen[0], "billed_share": 0.15},
        "misrating": {"product_code": "ROAM", "dates": [misrating_start + timedelta(days=i) for i in range(3)],
                      "rate_factor": 0.8},
        "duplicate_billing": {"date": chosen[2]},          # customer chosen once customers exist
        "late_arrival": {"site": sites[1], "date": chosen[3], "delay_days": 2},
        "systemic_dip": {"date": chosen[4], "volume_factor": 0.3},
    }


def build(days_count: int, seed: int) -> tuple[list, list, list, list, dict]:
    rng = random.Random(seed)
    days = [START + timedelta(days=i) for i in range(days_count)]
    faults = plan_faults(days, rng)
    # the misrating window must not overlap other faults' days
    taken = {faults["unbilled_site"]["date"], faults["duplicate_billing"]["date"],
             faults["late_arrival"]["date"], faults["systemic_dip"]["date"]}
    faults["misrating"]["dates"] = [d for d in faults["misrating"]["dates"] if d not in taken and d in days]

    customers = [(f"C{n:04d}", pick(rng, SEGMENTS), rng.choice(SITES)) for n in range(1, CUSTOMERS + 1)]
    faults["duplicate_billing"]["customer_id"] = rng.choice([c[0] for c in customers if c[1] == "business"])
    rates = {code: rate for code, _, _, rate in PRODUCTS}
    by_site = {s: [c[0] for c in customers if c[2] == s] for s in SITES}

    usage, billed = [], []
    record_id = bill_line = 0
    dup = faults["duplicate_billing"]
    dup_site = next(c[2] for c in customers if c[0] == dup["customer_id"])
    for day in days:
        volume = faults["systemic_dip"]["volume_factor"] if day == faults["systemic_dip"]["date"] else 1.0
        for site in SITES:
            n = int(RECORDS_PER_SITE_DAY * volume * rng.uniform(0.9, 1.1))
            dup_here = day == dup["date"] and site == dup_site
            if dup_here:
                n += 15  # give the duplicated customer 15 records that day
            for i in range(n):
                record_id += 1
                customer = dup["customer_id"] if dup_here and i < 15 else rng.choice(by_site[site])
                product = pick(rng, PRODUCT_MIX)
                units = rng.randint(*UNITS[product])
                event_ts = datetime.combine(day, datetime.min.time()) + timedelta(seconds=rng.randint(0, 86_399))
                late = faults["late_arrival"]
                delay = timedelta(days=late["delay_days"]) if (day == late["date"] and site == late["site"]) else timedelta(0)
                received_ts = event_ts + timedelta(minutes=rng.randint(1, 90)) + delay
                usage.append((f"U{record_id:07d}", customer, product, site,
                              event_ts.isoformat(sep=" "), received_ts.isoformat(sep=" "), units))

                if rates[product] == 0:
                    continue  # zero-rated: never billed, by design
                ub = faults["unbilled_site"]
                if day == ub["date"] and site == ub["site"] and rng.random() > ub["billed_share"]:
                    continue  # the leak: earned, never billed, no error anywhere
                rate = rates[product]
                if product == faults["misrating"]["product_code"] and day in faults["misrating"]["dates"]:
                    rate *= faults["misrating"]["rate_factor"]
                bill_date = (received_ts + timedelta(days=1)).date()  # billed the day after it arrives
                copies = 2 if (day == dup["date"] and customer == dup["customer_id"]) else 1
                for _ in range(copies):
                    bill_line += 1
                    billed.append((f"B{bill_line:07d}", f"U{record_id:07d}", customer, product,
                                   bill_date.isoformat(), round(units * rate, 4)))

    manifest = {
        "seed": seed, "days": days_count, "first_date": days[0].isoformat(), "last_date": days[-1].isoformat(),
        "faults": [
            {"id": "unbilled_site", "expect": "flagged", "mart": "mart_unbilled_usage",
             "site": faults["unbilled_site"]["site"], "usage_date": faults["unbilled_site"]["date"].isoformat(),
             "detail": "about 85% of the site's billable records that day were never billed"},
            {"id": "misrating", "expect": "flagged", "mart": "mart_rating_variance",
             "product_code": faults["misrating"]["product_code"],
             "usage_dates": [d.isoformat() for d in faults["misrating"]["dates"]],
             "detail": "billed at 80% of the product rate"},
            {"id": "duplicate_billing", "expect": "flagged", "mart": "mart_duplicate_billing",
             "customer_id": dup["customer_id"], "usage_date": dup["date"].isoformat(),
             "detail": "every billable record of this customer that day was billed twice"},
        ],
        "controls": [
            {"id": "late_arrival", "expect": "not_flagged", "mart": "mart_unbilled_usage",
             "site": faults["late_arrival"]["site"], "usage_date": faults["late_arrival"]["date"].isoformat(),
             "detail": "usage received two days late and billed in full; reconcile by event date, not received date"},
            {"id": "systemic_dip", "expect": "not_flagged", "mart": "mart_unbilled_usage",
             "usage_date": faults["systemic_dip"]["date"].isoformat(),
             "detail": "every site's volume fell ~70%, and billing fell with it; low volume is not a leak"},
            {"id": "zero_rated", "expect": "not_flagged", "mart": "mart_unbilled_usage",
             "product_code": "PROMO", "detail": "free product, never billed by design; expected billing is zero"},
        ],
    }
    products = [(code, desc, unit, rate) for code, desc, unit, rate in PRODUCTS]
    return customers, products, usage, billed, manifest


def write_csv(path: Path, header: list[str], rows: list[tuple]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    a = ap.parse_args(argv)
    if a.days < 14:
        ap.error("--days must be at least 14, so every fault fits with clean days around it")

    customers, products, usage, billed, manifest = build(a.days, a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    write_csv(a.out / "customers.csv", ["customer_id", "segment", "home_site"], customers)
    write_csv(a.out / "products.csv", ["product_code", "description", "unit", "rate"], products)
    write_csv(a.out / "usage.csv", ["record_id", "customer_id", "product_code", "site",
                                    "event_ts", "received_ts", "units"], usage)
    write_csv(a.out / "billed.csv", ["bill_line_id", "record_id", "customer_id", "product_code",
                                     "bill_date", "billed_amount"], billed)
    (a.out / "faults.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {a.out}: {len(customers)} customers, {len(products)} products, "
          f"{len(usage):,} usage records, {len(billed):,} bill lines ({a.days} days, seed {a.seed})")
    for f in manifest["faults"]:
        where = f.get("site") or f.get("product_code") or f.get("customer_id")
        when = f.get("usage_date") or ", ".join(f.get("usage_dates", []))
        print(f"   fault    {f['id']:<18} {where:<9} {when}")
    for c in manifest["controls"]:
        where = c.get("site") or c.get("product_code") or "all sites"
        print(f"   control  {c['id']:<18} {where:<9} {c.get('usage_date', 'every day')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
