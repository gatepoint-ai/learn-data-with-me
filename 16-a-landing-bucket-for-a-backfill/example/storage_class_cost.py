"""A landing bucket for a backfill: when does a colder storage class pay?

Colder classes cost less to keep and more to read, and they charge a minimum
storage duration: delete or rewrite an object early and you pay for the rest
of that period anyway. A backfill bucket is read hard at the start, re-read
whenever a load is replayed, then mostly left alone.

Prices are relative units, roughly the ratios of Google Cloud Storage list
prices when this was written (Standard storage = 1.0 per GB-month). Check
current pricing before you decide anything with real money.

Python standard library only, no installs.
"""

CLASSES = {
    # class: (storage per GB-month, retrieval per GB, minimum days)
    "STANDARD": (1.00, 0.00, 0),
    "NEARLINE": (0.50, 0.50, 30),
    "COLDLINE": (0.20, 1.00, 90),
    "ARCHIVE":  (0.06, 2.50, 365),
}
GB = 10_000


def cost(cls: str, months: int, full_reads: int, delete_after_days: int | None = None) -> float:
    storage, retrieval, min_days = CLASSES[cls]
    kept_days = delete_after_days if delete_after_days is not None else months * 30
    billed_days = max(kept_days, min_days)
    return GB * (storage * billed_days / 30 + retrieval * full_reads)


def scenario(title: str, months: int, reads: int, delete_after: int | None = None) -> None:
    print(title)
    results = {c: cost(c, months, reads, delete_after) for c in CLASSES}
    best = min(results, key=results.get)
    for c, v in results.items():
        print(f"   {c:9} {v:>10,.0f}{'   <- cheapest' if c == best else ''}")
    print()


if __name__ == "__main__":
    print(f"{GB:,} GB of historical files, cost in relative units\n")
    scenario("A) Kept 3 years, read twice (initial load + one replay)", months=36, reads=2)
    scenario("B) Kept 3 years, read 12 times (replayed every quarter)", months=36, reads=12)
    scenario("C) Loaded, then deleted after 20 days", months=1, reads=1, delete_after=20)
    print("No class wins every case. Keep files where they're cheap to read while loads are")
    print("still being replayed, and let a lifecycle rule move them colder once that stops.")
