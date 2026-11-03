"""Schedule beats tuning: find a window where a long dump can actually finish.

A parallel PostgreSQL dump (pg_dump -F d -j N) takes shared locks on every table it
exports. If any other session asks for an EXCLUSIVE lock on one of those tables
while the dump runs (a batch job truncating a staging table, a partition being
attached), a parallel worker can't get its lock and pg_dump aborts. The
PostgreSQL docs explain why: it is the only way to avoid a deadlock.

So the question isn't only "how fast is the dump?" but "when does it run without
meeting a job that takes exclusive locks?" This script answers it for one week
of a made-up batch schedule and two dump strategies.

Python standard library only, made-up schedule, no installs.
"""

from datetime import datetime, timedelta

WEEK_START = datetime(2026, 11, 2)  # a Monday
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# (name, days it runs, start "HH:MM", hours, takes exclusive locks?)
BATCH_JOBS = [
    ("nightly load",          DAYS,          "01:00", 2.5, True),
    ("hourly partition sync", DAYS[:5],      "06:30", 17.0, True),   # every hour 06:30-23:30 on weekdays
    ("weekly purge",          ["Sun"],       "22:00", 3.0, True),
    ("reporting extracts",    DAYS[:5],      "05:00", 1.5, False),   # reads only: no conflict
]

# (hours, what happens if an exclusive-lock job runs during the dump)
STRATEGIES = {
    "single archive, one process (-F c)": (40.0, "the dump holds its locks, so the batch job waits behind it"),
    "directory format, 8 workers (-F d -j 8)": (4.0, "a worker can't get its lock, so pg_dump aborts"),
}
SAFETY_MARGIN = timedelta(minutes=30)
STEP = timedelta(minutes=30)


def busy_windows() -> list[tuple[datetime, datetime, str]]:
    windows = []
    for name, days, start, hours, exclusive in BATCH_JOBS:
        if not exclusive:
            continue
        hh, mm = map(int, start.split(":"))
        for offset, day in enumerate(DAYS):
            if day in days:
                begin = WEEK_START + timedelta(days=offset, hours=hh, minutes=mm)
                windows.append((begin - SAFETY_MARGIN, begin + timedelta(hours=hours) + SAFETY_MARGIN, name))
    return windows


def first_clashes(start: datetime, end: datetime, busy) -> str | None:
    for b_start, b_end, name in sorted(busy):
        if start < b_end and b_start < end:
            return f"{name} at {b_start + SAFETY_MARGIN:%a %H:%M}"
    return None


def main() -> None:
    busy = busy_windows()
    print("Jobs that take exclusive locks (with a 30-minute margin either side):")
    for name, days, start, hours, exclusive in BATCH_JOBS:
        print(f"   {'X' if exclusive else ' '} {name:<22} {','.join(days) if len(days) < 7 else 'every day':<20}"
              f" {start} for {hours:g} h")
    print()
    week_end = WEEK_START + timedelta(days=7)
    for strategy, (hours, on_clash) in STRATEGIES.items():
        duration = timedelta(hours=hours)
        slots, t = [], WEEK_START
        while t + duration <= week_end:
            if not first_clashes(t, t + duration, busy):
                slots.append(t)
            t += STEP
        print(f"{strategy}: ~{hours:g} h")
        if slots:
            first = slots[0]
            print(f"   {len(slots)} safe start times this week. First: {first:%a %H:%M} -> done {first + duration:%a %H:%M}")
        else:
            clash = first_clashes(WEEK_START, WEEK_START + duration, busy)
            print(f"   no safe start time this week. Starting Monday 00:00, it meets: {clash}")
            print(f"   and then {on_clash}.")
        print()
    print("Parallel workers made the dump 10x faster. The schedule decided whether it could finish at all.")


if __name__ == "__main__":
    main()
