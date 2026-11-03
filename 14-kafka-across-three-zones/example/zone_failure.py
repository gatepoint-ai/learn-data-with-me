"""Kafka across three zones: what survives when a zone goes down?

Producers write with acks=all. A partition accepts writes while at least
min.insync.replicas of its replicas are alive and in sync, and serves reads
while at least one in-sync replica is alive. Spread the replicas over zones,
or a zone outage takes the partition with it.

Four layouts, each hit by the loss of every zone in turn.
The model is simplified on purpose: every live replica is assumed in sync.

Python standard library only, no installs.
"""

from itertools import cycle

LAYOUTS = {
    # name: (broker -> zone, replication factor, min.insync.replicas)
    "3 brokers, one per zone, RF 3, min ISR 2": ({1: "a", 2: "b", 3: "c"}, 3, 2),
    "3 brokers, all in zone a, RF 3, min ISR 2": ({1: "a", 2: "a", 3: "a"}, 3, 2),
    "3 brokers, one per zone, RF 2, min ISR 2": ({1: "a", 2: "b", 3: "c"}, 2, 2),
    "3 brokers, one per zone, RF 3, min ISR 3": ({1: "a", 2: "b", 3: "c"}, 3, 3),
}
PARTITIONS = 6


def assign(brokers: list[int], rf: int) -> list[list[int]]:
    """Round-robin replica placement, like Kafka's default for a new topic."""
    start = cycle(range(len(brokers)))
    return [[brokers[(next(start) + i) % len(brokers)] for i in range(rf)] for _ in range(PARTITIONS)]


def lose_zone(zones: dict, rf: int, min_isr: int, down: str) -> tuple[int, int]:
    parts = assign(sorted(zones), rf)
    alive = [[b for b in p if zones[b] != down] for p in parts]
    writable = sum(len(a) >= min_isr for a in alive)
    readable = sum(len(a) >= 1 for a in alive)
    return writable, readable


if __name__ == "__main__":
    for name, (zones, rf, min_isr) in LAYOUTS.items():
        print(name)
        for down in ("a", "b", "c"):
            w, r = lose_zone(zones, rf, min_isr, down)
            status = "ok" if w == PARTITIONS else ("WRITES BLOCKED" if r == PARTITIONS else "OUTAGE")
            print(f"   zone {down} down: {w}/{PARTITIONS} partitions take writes, {r}/{PARTITIONS} serve reads   {status}")
        print()
    print("Only one layout survives any single zone: a broker per zone, RF 3, min ISR 2.")
