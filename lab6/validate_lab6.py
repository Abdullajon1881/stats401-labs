"""Validate the Lab 6 CSV-to-JSON conversion and print derived facts."""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parent
DATA_DIR = LAB_DIR.parent / "data"
CSV_PATH = DATA_DIR / "lab6_assignment_gdp.csv"
JSON_PATH = DATA_DIR / "lab6_assignment_gdp.json"
REQUIRED_COLUMNS = {
    "continent",
    "area",
    "country",
    "gdp_billion_usd",
    "gdp_status",
}
EXPECTED_STATUSES = {"Increase", "Unchanged", "Decrease"}


def fail(message: str) -> None:
    raise ValueError(message)


def read_csv() -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
    if not CSV_PATH.is_file():
        fail(f"CSV does not exist: {CSV_PATH}")

    with CSV_PATH.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if set(reader.fieldnames or []) != REQUIRED_COLUMNS:
            fail(f"Unexpected CSV columns: {reader.fieldnames}")
        rows = list(reader)

    if len(rows) != 27:
        fail(f"Expected 27 CSV rows, found {len(rows)}")

    countries = [row["country"].strip() for row in rows]
    if any(not country for country in countries):
        fail("Every CSV country name must be non-empty")
    duplicates = [name for name, count in Counter(countries).items() if count > 1]
    if duplicates:
        fail(f"Duplicate CSV countries: {duplicates}")

    by_country: dict[str, dict[str, object]] = {}
    for row in rows:
        try:
            gdp = float(row["gdp_billion_usd"])
        except ValueError as error:
            fail(f"Invalid GDP for {row['country']}: {error}")
        if not math.isfinite(gdp) or gdp <= 0:
            fail(f"GDP must be positive for {row['country']}")
        by_country[row["country"]] = {
            "continent": row["continent"],
            "area": row["area"],
            "gdp": gdp,
            "status": row["gdp_status"],
        }

    statuses = {row["gdp_status"] for row in rows}
    if statuses != EXPECTED_STATUSES:
        fail(f"Unexpected CSV status set: {statuses}")
    return rows, by_country


def read_and_check_json(csv_by_country: dict[str, dict[str, object]]) -> dict[str, object]:
    if not JSON_PATH.is_file():
        fail(f"JSON does not exist: {JSON_PATH}")
    with JSON_PATH.open(encoding="utf-8") as json_file:
        hierarchy = json.load(json_file)
    if hierarchy.get("name") != "World":
        fail(f"Expected JSON root World, found {hierarchy.get('name')!r}")

    json_by_country: dict[str, list[dict[str, object]]] = {}
    for continent_node in hierarchy.get("children", []):
        continent = continent_node.get("name")
        for area_node in continent_node.get("children", []):
            area = area_node.get("name")
            for leaf in area_node.get("children", []):
                if set(leaf) != {"name", "gdp", "status"}:
                    fail(f"Unexpected leaf fields for {leaf.get('name')!r}: {set(leaf)}")
                entry = {
                    "continent": continent,
                    "area": area,
                    "gdp": float(leaf["gdp"]),
                    "status": leaf["status"],
                }
                json_by_country.setdefault(str(leaf.get("name")), []).append(entry)

    duplicate_leaves = [name for name, entries in json_by_country.items() if len(entries) != 1]
    if duplicate_leaves:
        fail(f"Duplicate JSON country leaves: {duplicate_leaves}")
    if set(json_by_country) != set(csv_by_country):
        fail(
            "CSV/JSON country mismatch: "
            f"missing={sorted(set(csv_by_country) - set(json_by_country))}, "
            f"extra={sorted(set(json_by_country) - set(csv_by_country))}"
        )

    for country, csv_values in csv_by_country.items():
        json_values = json_by_country[country][0]
        if json_values != csv_values:
            fail(f"CSV/JSON mismatch for {country}: {csv_values} != {json_values}")

    csv_total = sum(float(values["gdp"]) for values in csv_by_country.values())
    json_total = sum(entries[0]["gdp"] for entries in json_by_country.values())
    if not math.isclose(csv_total, json_total):
        fail(f"CSV/JSON GDP total mismatch: {csv_total} != {json_total}")
    return hierarchy


def main() -> None:
    try:
        rows, csv_by_country = read_csv()
        hierarchy = read_and_check_json(csv_by_country)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    continents = {row["continent"] for row in rows}
    areas = {(row["continent"], row["area"]) for row in rows}
    statuses = Counter(row["gdp_status"] for row in rows)
    total = sum(float(row["gdp_billion_usd"]) for row in rows)
    print("Lab 6 data validation passed")
    print(f"JSON root: {hierarchy['name']}")
    print(f"Countries: {len(rows)}")
    print(f"Continents: {len(continents)}")
    print(f"Areas: {len(areas)}")
    print(
        "Status counts: "
        + ", ".join(f"{status}={statuses[status]}" for status in sorted(statuses))
    )
    print(f"Total GDP: {total:,.0f} billion USD")
    print("Every JSON leaf matches its CSV continent, area, GDP, and status.")


if __name__ == "__main__":
    main()
