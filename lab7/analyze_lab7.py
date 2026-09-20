"""Print the Lab 7 temporal-network facts quoted in the findings section.

Run from the repository root:

    python lab7/analyze_lab7.py

This helper is not used by the webpage. It exists so the written answers on
lab7/index.html can be checked against the supplied CSV files.
"""

import csv
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COMPANIES_CSV = DATA_DIR / "lab7_assignment_companies.csv"
TRANSACTIONS_CSV = DATA_DIR / "lab7_assignment_transactions_60days.csv"

PERIODS = [("Days 1-20", 1, 20), ("Days 21-40", 21, 40), ("Days 41-60", 41, 60)]


def load(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def pair_key(source, target):
    return tuple(sorted((source, target)))


def links_by_day(transactions):
    by_day = defaultdict(list)
    for row in transactions:
        by_day[int(row["day"])].append(row)
    return by_day


def components(active_pairs, active_companies):
    """Connected components among ACTIVE companies only."""
    neighbours = defaultdict(set)
    for a, b in active_pairs:
        neighbours[a].add(b)
        neighbours[b].add(a)

    seen = set()
    count = 0
    for start in active_companies:
        if start in seen:
            continue
        count += 1
        stack = [start]
        seen.add(start)
        while stack:
            current = stack.pop()
            for neighbour in neighbours[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
    return count


def main():
    companies = load(COMPANIES_CSV)
    transactions = load(TRANSACTIONS_CSV)
    region_of = {row["id"]: row["region"] for row in companies}
    name_of = {row["id"]: row["company_name"] for row in companies}
    by_day = links_by_day(transactions)

    print(f"companies: {len(companies)}  transactions: {len(transactions)}")
    print(f"days present: {len(by_day)}  min={min(by_day)}  max={max(by_day)}")
    dates = sorted(row["date"] for row in transactions)
    print(f"date range: {dates[0]} .. {dates[-1]}")
    print()

    print("PERIOD SUMMARIES")
    for label, first, last in PERIODS:
        days = range(first, last + 1)
        link_counts = []
        company_counts = []
        values = []
        cross = 0
        records = 0
        for day in days:
            rows = by_day.get(day, [])
            pairs = {pair_key(r["source"], r["target"]) for r in rows}
            active = {r["source"] for r in rows} | {r["target"] for r in rows}
            link_counts.append(len(pairs))
            company_counts.append(len(active))
            values.append(sum(float(r["amount_usd"]) for r in rows))
            for r in rows:
                records += 1
                if region_of[r["source"]] != region_of[r["target"]]:
                    cross += 1
        n = len(link_counts)
        print(
            f"  {label}: links/day={sum(link_counts)/n:.2f}  "
            f"companies/day={sum(company_counts)/n:.2f}  "
            f"value/day=${sum(values)/n:,.2f}  "
            f"cross-region={cross}/{records} = {100*cross/records:.2f}%"
        )
    print()

    print("MOST ACTIVE COMPANIES BY PERIOD (incident volume / incident link records)")
    for label, first, last in PERIODS:
        volume = Counter()
        incident = Counter()
        for day in range(first, last + 1):
            for r in by_day.get(day, []):
                amount = float(r["amount_usd"])
                for endpoint in (r["source"], r["target"]):
                    volume[endpoint] += amount
                    incident[endpoint] += 1
        print(f"  {label}:")
        for company, amount in volume.most_common(4):
            print(
                f"    {company} {name_of[company]:<22} "
                f"${amount:,.2f}  records={incident[company]}"
            )
    print()

    print("RELATIONSHIP PERSISTENCE (active-day records, total amount)")
    pair_days = Counter()
    pair_amount = Counter()
    pair_first = {}
    pair_last = {}
    for row in transactions:
        key = pair_key(row["source"], row["target"])
        day = int(row["day"])
        pair_days[key] += 1
        pair_amount[key] += float(row["amount_usd"])
        pair_first[key] = min(pair_first.get(key, day), day)
        pair_last[key] = max(pair_last.get(key, day), day)
    print(f"  unique relationships over 60 days: {len(pair_days)}")
    for key, count in pair_days.most_common(8):
        a, b = key
        print(
            f"    {name_of[a]} ({a}) - {name_of[b]} ({b}): "
            f"{count} days  ${pair_amount[key]:,.2f}  "
            f"first=day {pair_first[key]}  last=day {pair_last[key]}"
        )
    print()

    print("LATE-EMERGING RELATIONSHIPS (first appearance on day 41 or later)")
    late = [k for k in pair_days if pair_first[k] >= 41]
    for key in sorted(late, key=lambda k: -pair_amount[k])[:8]:
        a, b = key
        print(
            f"    {name_of[a]} ({a}) - {name_of[b]} ({b}): "
            f"{pair_days[key]} days  ${pair_amount[key]:,.2f}  first=day {pair_first[key]}"
        )
    print()

    print("PER-DAY CONNECTIVITY (components counted among ACTIVE companies)")
    peak = []
    for day in range(1, 61):
        rows = by_day.get(day, [])
        pairs = {pair_key(r["source"], r["target"]) for r in rows}
        active = {r["source"] for r in rows} | {r["target"] for r in rows}
        comps = components(pairs, active)
        peak.append((len(pairs), len(active), comps, day))
        if day in (1, 21, 41, 45, 51, 57, 60):
            print(
                f"    day {day:>2}: links={len(pairs)}  active companies={len(active)}  "
                f"components among active={comps}"
            )
    peak.sort(reverse=True)
    print("  busiest days:")
    for links, active, comps, day in peak[:5]:
        print(
            f"    day {day:>2}: links={links}  active={active}  components={comps}"
        )
    single = [d for (l, a, c, d) in peak if c == 1]
    print(f"  days where active companies form a single component: {sorted(single) or 'none'}")
    all_twelve = sorted(d for (l, a, c, d) in peak if a == 12)
    print(f"  days with all 12 companies active: {all_twelve}")


if __name__ == "__main__":
    main()
