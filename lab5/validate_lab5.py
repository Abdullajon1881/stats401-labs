"""Check the Lab 5 transit network data and print the structural facts the
findings on the page rely on.

Run from the repository root:

    python lab5/validate_lab5.py

Exits with status 1 if any integrity check fails.
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATIONS_CSV = DATA_DIR / "lab5_assignment_stations.csv"
ROUTES_CSV = DATA_DIR / "lab5_assignment_routes.csv"

EXPECTED_STATIONS = 50
EXPECTED_ROUTES = 50
DISTRICTS = ["Central", "North", "South", "East", "West"]
STATION_TYPES = ["Local", "Transfer", "Terminal"]
ROUTE_TYPES = ["Metro", "Express", "Shuttle"]


def load(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def station_number(station_id):
    return int(station_id[1:])


def check(condition, message, failures):
    status = "ok  " if condition else "FAIL"
    print(f"[{status}] {message}")
    if not condition:
        failures.append(message)


def integrity_checks(stations, routes):
    failures = []
    ids = [s["id"] for s in stations]
    id_set = set(ids)

    check(len(stations) == EXPECTED_STATIONS, f"{len(stations)} station rows (expected {EXPECTED_STATIONS})", failures)
    check(len(routes) == EXPECTED_ROUTES, f"{len(routes)} route rows (expected {EXPECTED_ROUTES})", failures)
    check(len(id_set) == len(ids), "station ids are unique", failures)
    check(all(r["source"] in id_set and r["target"] in id_set for r in routes), "every route endpoint is a known station", failures)
    check(all(r["source"] != r["target"] for r in routes), "no self-loops", failures)
    pairs = [frozenset((r["source"], r["target"])) for r in routes]
    check(len(set(pairs)) == len(pairs), "no duplicate undirected pairs", failures)

    try:
        passengers = [int(s["daily_passengers"]) for s in stations]
        times = [int(r["travel_time_min"]) for r in routes]
        numeric_ok = all(p > 0 for p in passengers) and all(t > 0 for t in times)
    except ValueError:
        numeric_ok = False
    check(numeric_ok, "daily_passengers and travel_time_min parse as positive integers", failures)

    check(set(s["district"] for s in stations) == set(DISTRICTS), "all five districts present, nothing else", failures)
    check(set(s["station_type"] for s in stations) == set(STATION_TYPES), "all three station types present, nothing else", failures)
    check(set(r["route_type"] for r in routes) == set(ROUTE_TYPES), "all three route types present, nothing else", failures)
    return failures


def structural_summary(stations, routes):
    by_id = {s["id"]: s for s in stations}
    ids = sorted(by_id, key=station_number)
    neighbours = defaultdict(set)
    for r in routes:
        neighbours[r["source"]].add(r["target"])
        neighbours[r["target"]].add(r["source"])
    degree = {i: len(neighbours[i]) for i in ids}

    print("\nDegree distribution:", dict(sorted(Counter(degree.values()).items())))
    top = max(degree.values())
    print(f"Maximum degree {top}, held by {sum(1 for d in degree.values() if d == top)} stations:",
          ", ".join(i for i in ids if degree[i] == top))
    print("Isolated stations:", ", ".join(i for i in ids if degree[i] == 0) or "none")

    seen, components = set(), []
    for start in ids:
        if start in seen:
            continue
        stack, component = [start], set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(neighbours[current] - component)
        seen |= component
        components.append(component)
    print("Connected components:", sorted((len(c) for c in components), reverse=True))

    pair_counts = Counter()
    for r in routes:
        a, b = by_id[r["source"]]["district"], by_id[r["target"]]["district"]
        pair_counts[tuple(sorted((a, b)))] += 1
    print("\nDistrict pair edge counts:")
    for (a, b), n in sorted(pair_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {a:8} - {b:8} {n}")
    print("Within-district edges:", sum(n for (a, b), n in pair_counts.items() if a == b))

    print("\nLongest direct travel times:")
    for r in sorted(routes, key=lambda r: -int(r["travel_time_min"]))[:5]:
        print(f"  {r['source']}-{r['target']:4} {r['travel_time_min']:>2} min {r['route_type']}")

    print("\nHighest daily passengers:")
    for s in sorted(stations, key=lambda s: -int(s["daily_passengers"]))[:8]:
        print(f"  {s['id']:4} {s['daily_passengers']:>5} {s['district']:8} {s['station_type']:9} degree {degree[s['id']]}")

    print("\nStation type by degree:")
    for station_type in STATION_TYPES:
        counts = Counter(degree[i] for i in ids if by_id[i]["station_type"] == station_type)
        print(f"  {station_type:9}", dict(sorted(counts.items())))

    print("\nRoute types:", dict(Counter(r["route_type"] for r in routes)))
    print("Route type by district pair kind:")
    for route_type in ROUTE_TYPES:
        kinds = Counter(
            "within" if by_id[r["source"]]["district"] == by_id[r["target"]]["district"] else "between"
            for r in routes if r["route_type"] == route_type
        )
        print(f"  {route_type:8}", dict(kinds))


def main():
    stations = load(STATIONS_CSV)
    routes = load(ROUTES_CSV)
    failures = integrity_checks(stations, routes)
    structural_summary(stations, routes)
    if failures:
        print(f"\n{len(failures)} check(s) failed")
        sys.exit(1)
    print("\nAll integrity checks passed")


if __name__ == "__main__":
    main()
