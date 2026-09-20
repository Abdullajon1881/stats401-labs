"""Check the Lab 7 temporal commercial network: the supplied data, the page
markup, the visualization script, the stylesheet, and the evidence behind the
five written answers.

Run from the repository root:

    python lab7/validate_lab7.py

Exits with status 1 if any check fails.
"""

import csv
import datetime
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
ROOT = LAB_DIR.parent
DATA_DIR = ROOT / "data"

COMPANIES_CSV = DATA_DIR / "lab7_assignment_companies.csv"
TRANSACTIONS_CSV = DATA_DIR / "lab7_assignment_transactions_60days.csv"
HTML_PATH = LAB_DIR / "index.html"
JS_PATH = LAB_DIR / "lab7.js"
CSS_PATH = LAB_DIR / "lab7.css"

EXPECTED_COMPANIES = 12
EXPECTED_TRANSACTIONS = 367
FIRST_DAY = 1
LAST_DAY = 60
FIRST_DATE = "2026-01-01"
LAST_DATE = "2026-03-01"
COMPANY_COLUMNS = ["id", "company_name", "sector", "region"]
TRANSACTION_COLUMNS = [
    "date",
    "day",
    "source",
    "target",
    "amount_usd",
    "transaction_type",
    "transaction_count",
]
EXPECTED_TYPES = {"goods", "shipping", "components", "materials", "services"}
EXPECTED_REGIONS = {"Asia", "Europe", "North America"}

PERIODS = [("Days 1-20", 1, 20), ("Days 21-40", 21, 40), ("Days 41-60", 41, 60)]

failures = []


def check(condition, message):
    print(f"[{'ok  ' if condition else 'FAIL'}] {message}")
    if not condition:
        failures.append(message)
    return bool(condition)


def section(title):
    print()
    print(title)
    print("-" * len(title))


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def pair_key(source, target):
    return tuple(sorted((source, target)))


# ---------------------------------------------------------------------------
# source data
# ---------------------------------------------------------------------------


def check_source_data():
    section("SOURCE DATA")

    if not check(COMPANIES_CSV.is_file(), f"{COMPANIES_CSV.name} exists"):
        return None, None
    if not check(TRANSACTIONS_CSV.is_file(), f"{TRANSACTIONS_CSV.name} exists"):
        return None, None

    companies, company_columns = read_csv(COMPANIES_CSV)
    transactions, transaction_columns = read_csv(TRANSACTIONS_CSV)

    check(company_columns == COMPANY_COLUMNS, f"company columns are {COMPANY_COLUMNS}")
    check(
        transaction_columns == TRANSACTION_COLUMNS,
        f"transaction columns are {TRANSACTION_COLUMNS}",
    )
    check(
        len(companies) == EXPECTED_COMPANIES,
        f"{EXPECTED_COMPANIES} companies (found {len(companies)})",
    )
    check(
        len(transactions) == EXPECTED_TRANSACTIONS,
        f"{EXPECTED_TRANSACTIONS} transaction rows (found {len(transactions)})",
    )

    ids = [row["id"] for row in companies]
    check(len(set(ids)) == len(ids), "company ids are unique")
    check(
        ids == [f"c{n:02d}" for n in range(1, EXPECTED_COMPANIES + 1)],
        "company ids run c01 through c12",
    )
    check(
        all(row["company_name"].strip() for row in companies),
        "every company has a non-empty name",
    )
    regions = {row["region"] for row in companies}
    check(regions == EXPECTED_REGIONS, f"regions are {sorted(EXPECTED_REGIONS)}")
    sectors = {row["sector"] for row in companies}
    check(len(sectors) >= 2, f"at least two sectors (found {len(sectors)})")

    known = set(ids)
    bad_endpoints = [
        row for row in transactions
        if row["source"] not in known or row["target"] not in known
    ]
    check(not bad_endpoints, "every source and target is a known company")

    self_links = [row for row in transactions if row["source"] == row["target"]]
    check(not self_links, "no self-links")

    days = []
    day_errors = 0
    for row in transactions:
        try:
            days.append(int(row["day"]))
        except ValueError:
            day_errors += 1
    check(not day_errors, "every day value is an integer")
    check(
        days and min(days) == FIRST_DAY and max(days) == LAST_DAY,
        f"day values run {FIRST_DAY} to {LAST_DAY}",
    )
    check(
        set(days) == set(range(FIRST_DAY, LAST_DAY + 1)),
        "all 60 days are represented",
    )

    dates = []
    date_errors = []
    for row in transactions:
        try:
            dates.append(datetime.datetime.strptime(row["date"], "%Y-%m-%d").date())
        except ValueError:
            date_errors.append(row["date"])
    check(not date_errors, "every date parses as %Y-%m-%d")
    if dates:
        check(
            min(dates).isoformat() == FIRST_DATE and max(dates).isoformat() == LAST_DATE,
            f"date range is {FIRST_DATE} to {LAST_DATE}",
        )
        base = datetime.date(2026, 1, 1)
        mismatched = [
            row for row in transactions
            if base + datetime.timedelta(days=int(row["day"]) - 1)
            != datetime.datetime.strptime(row["date"], "%Y-%m-%d").date()
        ]
        check(not mismatched, "each date matches its day number")

    amounts = []
    amount_errors = 0
    for row in transactions:
        try:
            amounts.append(float(row["amount_usd"]))
        except ValueError:
            amount_errors += 1
    check(not amount_errors, "every amount_usd is numeric")
    check(all(amount > 0 for amount in amounts), "every amount_usd is positive")

    counts_ok = all(
        row["transaction_count"].isdigit() and int(row["transaction_count"]) > 0
        for row in transactions
    )
    check(counts_ok, "every transaction_count is a positive integer")

    types = {row["transaction_type"] for row in transactions}
    check(types == EXPECTED_TYPES, f"transaction types are {sorted(EXPECTED_TYPES)}")

    duplicates = Counter(
        (int(row["day"]), pair_key(row["source"], row["target"])) for row in transactions
    )
    check(
        not [key for key, count in duplicates.items() if count > 1],
        "no company pair is recorded twice on the same day",
    )

    return companies, transactions


# ---------------------------------------------------------------------------
# page files
# ---------------------------------------------------------------------------


def check_html():
    section("HTML")
    if not check(HTML_PATH.is_file(), "lab7/index.html exists"):
        return
    html = HTML_PATH.read_text(encoding="utf-8")

    required = [
        ("page title names Lab 7", r"<title>[^<]*Lab 7[^<]*</title>"),
        ("lab title heading", r"<h1>\s*Lab 7: Temporal Data Visualization\s*</h1>"),
        ("60-day commercial network subtitle", r"60-Day Commercial Network"),
        ("D3 v7 loaded from the CDN", r"cdn\.jsdelivr\.net/npm/d3@7"),
        ("lab7.css linked", r'href="lab7\.css"'),
        ("global stylesheet linked", r'href="\.\./css/style\.css"'),
        ("lab7.js loaded", r'src="lab7\.js"'),
        ("Play button", r'id="play"[^>]*>\s*Play'),
        ("Pause button", r'id="pause"[^>]*>\s*Pause'),
        ("Reset button", r'id="reset"[^>]*>\s*Reset'),
        ("time slider spanning 60 days", r'id="time-slider"'),
        ("current day/date readout", r'id="day-readout"'),
        ("network container", r'id="network"'),
        ("tooltip container", r'id="tooltip"'),
        ("legend: node fill", r"Node fill"),
        ("legend: node size", r"Node size"),
        ("legend: inactive companies", r"Inactive companies"),
        ("legend: line colour", r"Line colour"),
        ("legend: line width", r"Line width"),
        ("legend: line style", r"Line style"),
        ("mental-map decision documented", r"Mental map"),
        ("back link to the main page", r'href="\.\./index\.html"'),
        ("both data files referenced", r"lab7_assignment_transactions_60days\.csv"),
    ]
    for label, pattern in required:
        check(re.search(pattern, html) is not None, label)

    slider = re.search(r'<input[^>]*id="time-slider"[^>]*>', html)
    if check(slider is not None, "time slider input found"):
        tag = slider.group(0)
        check('min="1"' in tag, "slider min is 1")
        check('max="60"' in tag, "slider max is 60")
        check('step="1"' in tag, "slider step is 1")
        check('type="range"' in tag, "slider is a range input")

    for stat_id in ("stat-companies", "stat-links", "stat-value", "stat-cross"):
        check(f'id="{stat_id}"' in html, f"summary field {stat_id} present")

    answers = re.findall(r'<article class="lab7-answer">\s*<h3>(.*?)</h3>', html, re.S)
    check(len(answers) == 5, f"five question/answer entries (found {len(answers)})")
    for number in range(1, 6):
        check(
            any(heading.strip().startswith(f"{number}.") for heading in answers),
            f"answer {number} present",
        )
    bodies = re.findall(
        r'<article class="lab7-answer">.*?<p>(.*?)</p>', html, re.S
    )
    check(
        all(len(re.sub(r"\s+", " ", body).strip()) > 240 for body in bodies),
        "each answer is a substantive paragraph",
    )


def check_js():
    section("JAVASCRIPT")
    if not check(JS_PATH.is_file(), "lab7/lab7.js exists"):
        return
    js = JS_PATH.read_text(encoding="utf-8")

    required = [
        ("d3.forceSimulation used", r"d3\.forceSimulation\("),
        ("forceLink used for the layout", r"d3\.forceLink\("),
        ("forceManyBody used", r"d3\.forceManyBody\("),
        ("forceCenter used", r"d3\.forceCenter\("),
        ("forceCollide used", r"d3\.forceCollide\("),
        ("layout solved with explicit ticks", r"simulation\.tick\(\)"),
        ("simulation stopped before ticking", r"simulation\.stop\(\)"),
        ("solved positions are pinned", r"company\.fx\s*=|\.fx\s*=\s*"),
        ("aggregate layout links are cloned", r"aggregateLayoutLinks"),
        ("undirected pair key helper", r"function pairKey"),
        ("pair key sorts the two ids", r"sourceId\s*<\s*targetId"),
        ("current day filtering by day", r"d3\.group\(transactions,\s*\(d\)\s*=>\s*d\.day\)"),
        ("keyed link join", r"\.data\(links,\s*\(d\)\s*=>\s*d\.key\)"),
        ("enter selection appends lines", r"\(enter\)\s*=>\s*enter\.append\(\"line\"\)"),
        ("enter transition fades links in", r"attr\(\"opacity\", LINK_OPACITY\)"),
        ("exit selection present", r"\(exit\)\s*=>\s*exit"),
        ("exit transition fades links out", r"\.attr\(\"opacity\", 0\)\s*\n\s*\.remove\(\)"),
        ("dynamic node volume calculation", r"function currentVolume"),
        ("volume uses amount_usd", r"\(d\)\s*=>\s*d\.amount"),
        ("node radius updated per day", r"\.attr\(\"r\", radiusFor\)"),
        ("square-root radius scale", r"d3\.scaleSqrt\(\)[\s\S]{0,200}?range\(\[0, 30\]\)"),
        ("node fill encodes sector", r"sectorColor\(d\.sector\)"),
        ("link colour encodes transaction type", r"typeColor\(d\.type\)"),
        ("link width encodes the amount", r"widthScale\(d\.amount\)"),
        ("cross-region links are dashed", r"crossRegion\s*\?\s*\"7 5\""),
        ("play handler", r'querySelector\("#play"\)|playButton\.addEventListener'),
        ("pause handler", r'querySelector\("#pause"\)\.addEventListener'),
        ("reset handler", r'querySelector\("#reset"\)\.addEventListener'),
        ("slider input handler", r'slider\.addEventListener\("input"'),
        ("slider pauses the animation", r"pause\(\);\s*\n\s*showDay\(\+this\.value\)"),
        ("animation timer", r"d3\.interval\("),
        ("animation stops at the last day", r"if \(next >= LAST_DAY\)"),
        ("current day and date written out", r"#day-readout"),
        ("summary updated from current links", r"function updateSummary"),
        ("cross-region counted for the summary", r"link\.crossRegion"),
        ("node tooltip", r"function nodeTooltip"),
        ("link tooltip", r"function linkTooltip"),
        ("tooltip content built without innerHTML", r"textContent"),
        ("reduced motion respected", r"prefers-reduced-motion"),
        ("nodes are keyboard focusable", r'attr\("tabindex", 0\)'),
        ("nodes carry an aria-label", r'attr\("aria-label"'),
        ("load failure handled", r"function showLoadError"),
        ("all 60 days addressed", r"LAST_DAY = 60"),
    ]
    for label, pattern in required:
        check(re.search(pattern, js) is not None, label)

    check(".innerHTML" not in js, "innerHTML is never assigned or read")

    # the mutation trap: d3.forceLink() rewrites source/target on whatever array
    # it is handed, so the raw transaction rows must never reach it
    force_link = re.search(r"d3\.forceLink\((\w+)\)", js)
    if check(force_link is not None, "forceLink argument identified"):
        argument = force_link.group(1)
        check(
            argument == "layoutLinks",
            f"forceLink receives the cloned layout links (got {argument!r})",
        )
    check(
        re.search(r"d3\.forceLink\(\s*transactions\s*\)", js) is None,
        "raw transaction rows are not passed to forceLink",
    )
    check(
        re.search(r"\bsourceId\b", js) is not None
        and re.search(r"\btargetId\b", js) is not None,
        "transaction endpoints are kept in separate sourceId/targetId fields",
    )


def check_css():
    section("CSS")
    if not check(CSS_PATH.is_file(), "lab7/lab7.css exists"):
        return
    css = CSS_PATH.read_text(encoding="utf-8")

    required = [
        ("responsive media queries", r"@media \(max-width:"),
        ("narrow layout collapses the summary grid", r"grid-template-columns: repeat\(2"),
        ("tooltip styles", r"\.lab7-tooltip\b"),
        ("control styles", r"\.lab7-button\b"),
        ("slider styles", r"\.lab7-slider\b"),
        ("legend styles", r"\.lab7-legend-card\b"),
        ("summary card styles", r"\.lab7-summary\b"),
        ("active node treatment", r"\.lab7-node\.is-active"),
        ("inactive node treatment", r"\.lab7-node\.is-inactive"),
        ("link styles", r"\.lab7-link\b"),
        ("exiting links stop taking pointer events", r"\.lab7-link\.is-exiting"),
        ("regional band labels", r"\.lab7-band-label\b"),
        ("focus-visible outlines", r":focus-visible"),
        ("reduced-motion rule", r"@media \(prefers-reduced-motion: reduce\)"),
        ("network uses a scrollable wrapper", r"\.lab7-network-wrap[\s\S]{0,160}overflow-x: auto"),
    ]
    for label, pattern in required:
        check(re.search(pattern, css) is not None, label)


# ---------------------------------------------------------------------------
# evidence behind the written answers
# ---------------------------------------------------------------------------


def components(pairs, active):
    """Connected components among ACTIVE companies only."""
    neighbours = defaultdict(set)
    for first, second in pairs:
        neighbours[first].add(second)
        neighbours[second].add(first)

    seen = set()
    total = 0
    for start in active:
        if start in seen:
            continue
        total += 1
        stack = [start]
        seen.add(start)
        while stack:
            current = stack.pop()
            for neighbour in neighbours[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
    return total


def close_to(actual, expected, tolerance):
    return abs(actual - expected) <= tolerance


def check_answers(companies, transactions):
    section("QUESTION EVIDENCE")
    if not companies or not transactions:
        check(False, "data available for the answer checks")
        return

    html = HTML_PATH.read_text(encoding="utf-8") if HTML_PATH.is_file() else ""
    region = {row["id"]: row["region"] for row in companies}

    by_day = defaultdict(list)
    for row in transactions:
        by_day[int(row["day"])].append(row)

    # ---- question 1: connectivity by period
    stats = {}
    for label, first, last in PERIODS:
        days = range(first, last + 1)
        links = []
        active_counts = []
        values = []
        cross = 0
        records = 0
        for day in days:
            rows = by_day[day]
            pairs = {pair_key(r["source"], r["target"]) for r in rows}
            active = {r["source"] for r in rows} | {r["target"] for r in rows}
            links.append(len(pairs))
            active_counts.append(len(active))
            values.append(sum(float(r["amount_usd"]) for r in rows))
            records += len(rows)
            cross += sum(
                1 for r in rows if region[r["source"]] != region[r["target"]]
            )
        span = len(links)
        stats[label] = {
            "links": sum(links) / span,
            "companies": sum(active_counts) / span,
            "value": sum(values) / span,
            "cross_pct": 100 * cross / records,
        }
        print(
            f"       {label}: {stats[label]['links']:.2f} links/day, "
            f"{stats[label]['companies']:.2f} companies/day, "
            f"${stats[label]['value']:,.2f}/day, "
            f"{stats[label]['cross_pct']:.2f}% cross-region"
        )

    expected = {
        "Days 1-20": (5.50, 8.55, 77195.57, 63.64),
        "Days 21-40": (5.60, 8.05, 96769.61, 63.39),
        "Days 41-60": (7.25, 9.65, 144325.86, 72.41),
    }
    for label, (links, comps, value, cross) in expected.items():
        check(
            close_to(stats[label]["links"], links, 0.01),
            f"{label} averages {links:.2f} active relationships per day",
        )
        check(
            close_to(stats[label]["companies"], comps, 0.01),
            f"{label} averages {comps:.2f} active companies per day",
        )
        check(
            close_to(stats[label]["value"], value, 1.0),
            f"{label} averages about ${value:,.0f} of transaction value per day",
        )
        check(
            close_to(stats[label]["cross_pct"], cross, 0.01),
            f"{label} is {cross:.2f}% cross-region relationship records",
        )

    check(
        stats["Days 41-60"]["links"] > stats["Days 1-20"]["links"]
        and stats["Days 41-60"]["links"] > stats["Days 21-40"]["links"],
        "the written claim that connectivity rises in days 41-60 holds",
    )
    check(
        stats["Days 41-60"]["cross_pct"] > stats["Days 1-20"]["cross_pct"]
        and stats["Days 41-60"]["cross_pct"] > stats["Days 21-40"]["cross_pct"],
        "the written claim that the network becomes more cross-regional holds",
    )

    # ---- question 2: most active companies
    def period_activity(first, last):
        volume = Counter()
        incident = Counter()
        for day in range(first, last + 1):
            for row in by_day[day]:
                amount = float(row["amount_usd"])
                for endpoint in (row["source"], row["target"]):
                    volume[endpoint] += amount
                    incident[endpoint] += 1
        return volume, incident

    mid_volume, mid_incident = period_activity(21, 40)
    late_volume, late_incident = period_activity(41, 60)

    mid_leader, mid_amount = mid_volume.most_common(1)[0]
    check(mid_leader == "c06", f"days 21-40 leader is Fusion Electronics c06 (got {mid_leader})")
    check(
        close_to(mid_amount, 1053610.40, 1.0),
        f"c06 mid-period incident volume is ${mid_amount:,.2f} (about $1.05 million)",
    )
    check(
        mid_incident["c06"] == 53,
        f"c06 has {mid_incident['c06']} incident daily-link records in days 21-40",
    )

    late_top = [company for company, _ in late_volume.most_common(2)]
    check(
        set(late_top) == {"c09", "c03"},
        f"days 41-60 leaders are Ion Systems c09 and Cedar Retail c03 (got {late_top})",
    )
    check(
        close_to(late_volume["c09"], 1096550.09, 1.0),
        f"c09 late-period incident volume is ${late_volume['c09']:,.2f} (about $1.10 million)",
    )
    check(
        close_to(late_volume["c03"], 901810.16, 1.0),
        f"c03 late-period incident volume is ${late_volume['c03']:,.2f} (about $0.90 million)",
    )

    # ---- question 3: clusters
    component_counts = Counter()
    peak_days = []
    for day in range(FIRST_DAY, LAST_DAY + 1):
        rows = by_day[day]
        pairs = {pair_key(r["source"], r["target"]) for r in rows}
        active = {r["source"] for r in rows} | {r["target"] for r in rows}
        component_counts[components(pairs, active)] += 1
        peak_days.append((len(pairs), len(active), day))
    print(f"       component counts among active companies: {dict(sorted(component_counts.items()))}")
    check(
        component_counts[1] == 0,
        "no single day forms one connected component among its active companies",
    )
    check(
        component_counts[3] == 34 and component_counts[2] == 20 and component_counts[4] == 6,
        "component counts are 2 on 20 days, 3 on 34 days and 4 on 6 days",
    )

    day_one = [entry for entry in peak_days if entry[2] == 1][0]
    check(
        day_one[0] == 3 and day_one[1] == 6,
        f"day 1 has 3 relationships and 6 active companies (got {day_one[0]}, {day_one[1]})",
    )

    busiest = sorted(peak_days, reverse=True)[:3]
    check(
        sorted(entry[2] for entry in busiest) == [45, 51, 57],
        f"the three densest days are 45, 51 and 57 (got {sorted(e[2] for e in busiest)})",
    )
    check(
        all(entry[0] == 10 and entry[1] == 12 for entry in busiest),
        "each of days 45, 51 and 57 has 10 relationships and all 12 companies active",
    )

    # ---- question 4: relationship change
    pair_days = Counter()
    pair_amount = Counter()
    pair_first = {}
    for row in transactions:
        key = pair_key(row["source"], row["target"])
        day = int(row["day"])
        pair_days[key] += 1
        pair_amount[key] += float(row["amount_usd"])
        pair_first[key] = min(pair_first.get(key, day), day)

    check(len(pair_days) == 27, f"27 distinct relationships across the 60 days (got {len(pair_days)})")

    persistent = pair_key("c04", "c06")
    check(
        pair_days[persistent] == 20 and close_to(pair_amount[persistent], 440145.54, 0.5),
        f"c04-c06 is active on {pair_days[persistent]} days for "
        f"${pair_amount[persistent]:,.2f}",
    )

    for first, second, days, amount in [
        ("c06", "c09", 10, 300579.60),
        ("c03", "c11", 10, 282296.34),
        ("c03", "c07", 10, 254351.55),
    ]:
        key = pair_key(first, second)
        check(
            pair_days[key] == days
            and close_to(pair_amount[key], amount, 0.5)
            and pair_first[key] >= 41,
            f"{first}-{second} first appears on day {pair_first[key]}, active on "
            f"{pair_days[key]} days for ${pair_amount[key]:,.2f}",
        )

    def period_pairs(first, last):
        found = set()
        for day in range(first, last + 1):
            found |= {pair_key(r["source"], r["target"]) for r in by_day[day]}
        return found

    early, middle, late = (period_pairs(a, b) for _, a, b in PERIODS)
    check(
        len(early & middle & late) == 9,
        f"9 relationships appear in all three windows (got {len(early & middle & late)})",
    )
    gone_after_20 = early - middle - late
    check(
        pair_key("c03", "c06") in gone_after_20,
        "c03-c06 stops after day 20",
    )
    new_late = late - early - middle
    check(len(new_late) == 8, f"8 relationships are new in days 41-60 (got {len(new_late)})")
    cross_new = sum(1 for a, b in new_late if region[a] != region[b])
    check(
        cross_new == 7,
        f"7 of the 8 late relationships are cross-region (got {cross_new})",
    )

    # ---- the prose must quote the numbers it was written from
    quoted = [
        "5.50", "5.60", "7.25",
        "8.55", "8.05", "9.65",
        "63.64%", "63.39%", "72.41%",
        "$1,053,610", "$1,096,550", "$901,810",
        "$440,146", "$300,580", "$282,296",
    ]
    missing = [value for value in quoted if value not in html]
    check(not missing, f"the written answers quote the computed figures (missing: {missing})")


def main():
    companies, transactions = check_source_data()
    check_html()
    check_js()
    check_css()
    check_answers(companies, transactions)

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        for message in failures:
            print(f"  - {message}")
        sys.exit(1)
    print("Lab 7 validation passed with zero failures.")


if __name__ == "__main__":
    main()
