"""Convert the Lab 6 flat GDP CSV into a deterministic hierarchy."""

from __future__ import annotations

import csv
import json
from collections import OrderedDict
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parent
DATA_DIR = LAB_DIR.parent / "data"
CSV_PATH = DATA_DIR / "lab6_assignment_gdp.csv"
JSON_PATH = DATA_DIR / "lab6_assignment_gdp.json"


def parse_gdp(raw_value: str) -> int | float:
    """Return an integer when possible while still accepting decimal GDP values."""
    value = float(raw_value)
    return int(value) if value.is_integer() else value


def build_hierarchy() -> dict[str, object]:
    continents: OrderedDict[str, OrderedDict[str, list[dict[str, object]]]]
    continents = OrderedDict()

    with CSV_PATH.open(encoding="utf-8-sig", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            area_map = continents.setdefault(row["continent"], OrderedDict())
            countries = area_map.setdefault(row["area"], [])
            countries.append(
                {
                    "name": row["country"],
                    "gdp": parse_gdp(row["gdp_billion_usd"]),
                    "status": row["gdp_status"],
                }
            )

    return {
        "name": "World",
        "children": [
            {
                "name": continent,
                "children": [
                    {"name": area, "children": countries}
                    for area, countries in area_map.items()
                ],
            }
            for continent, area_map in continents.items()
        ],
    }


def main() -> None:
    hierarchy = build_hierarchy()
    with JSON_PATH.open("w", encoding="utf-8", newline="\n") as json_file:
        json.dump(hierarchy, json_file, indent=2, ensure_ascii=False)
        json_file.write("\n")
    print(f"Wrote {JSON_PATH}")


if __name__ == "__main__":
    main()
