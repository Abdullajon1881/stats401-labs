"""Prepare the frozen World electricity-mix data used by the redesign.

The script downloads the official Our World in Data grapher CSV configured for
annual generation by source, selects World for 2010--2025, reshapes the nine
source columns to long format, and calculates each source's share of the sum of
those included components. It also checks that the component sum reconciles to
OWID's separate total-electricity series before writing the committed artifact.

The original chart image is downloaded from OWID's PNG export endpoint using
the same entity, period, metric, source, and frequency configuration.
"""

from __future__ import annotations

import csv
import io
import math
import urllib.request
from collections import defaultdict
from pathlib import Path


SOURCE_URL = (
    "https://ourworldindata.org/grapher/electricity-mix.csv?"
    "v=1&csvType=full&useColumnShortNames=false&source=total&"
    "metric=by_source&frequency=annual"
)
TOTAL_URL = (
    "https://ourworldindata.org/grapher/electricity-mix.csv?"
    "v=1&csvType=full&useColumnShortNames=false&source=total&"
    "metric=generation&frequency=annual"
)
ORIGINAL_IMAGE_URL = (
    "https://ourworldindata.org/grapher/electricity-mix.png?"
    "frequency=annual&metric=by_source&source=total&"
    "time=2010..2025&country=~OWID_WRL"
)

START_YEAR = 2010
END_YEAR = 2025
ENTITY = "World"
SOURCES = (
    "Coal",
    "Oil",
    "Gas",
    "Nuclear",
    "Hydropower",
    "Wind",
    "Solar",
    "Bioenergy",
    "Other renewables",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_CSV = PROJECT_ROOT / "data" / "critique_electricity_world_2010_2025.csv"
OUTPUT_IMAGE = Path(__file__).resolve().parent / "original-visualization.png"


def download(url: str) -> bytes:
    """Download an OWID resource with a descriptive user agent."""

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "STATS 401 visualization critique/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return response.read()


def read_csv_bytes(raw: bytes) -> list[dict[str, str]]:
    """Parse UTF-8 CSV bytes as dictionaries."""

    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def world_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Select the requested World period and return it in year order."""

    selected = [
        row
        for row in rows
        if row["Entity"] == ENTITY
        and START_YEAR <= int(row["Year"]) <= END_YEAR
    ]
    return sorted(selected, key=lambda row: int(row["Year"]))


def prepare() -> tuple[int, float]:
    """Download, validate, reshape, and write the submission artifacts."""

    component_rows = world_rows(read_csv_bytes(download(SOURCE_URL)))
    total_rows = world_rows(read_csv_bytes(download(TOTAL_URL)))

    expected_years = list(range(START_YEAR, END_YEAR + 1))
    component_years = [int(row["Year"]) for row in component_rows]
    total_years = [int(row["Year"]) for row in total_rows]
    if component_years != expected_years or total_years != expected_years:
        raise ValueError("OWID data does not contain the complete requested year range")

    total_by_year = {
        int(row["Year"]): float(row["Total electricity"]) for row in total_rows
    }
    output_rows: list[dict[str, str]] = []
    largest_total_difference = 0.0
    share_sums: dict[int, float] = defaultdict(float)

    for row in component_rows:
        year = int(row["Year"])
        values = {source: float(row[source]) for source in SOURCES}
        if not all(math.isfinite(value) and value >= 0 for value in values.values()):
            raise ValueError(f"Non-finite or negative generation found for {year}")

        component_total = sum(values.values())
        largest_total_difference = max(
            largest_total_difference,
            abs(component_total - total_by_year[year]),
        )

        for source in SOURCES:
            share = values[source] / component_total * 100
            share_sums[year] += share
            output_rows.append(
                {
                    "year": str(year),
                    "source": source,
                    "generation_twh": f"{values[source]:.2f}",
                    "share_pct": f"{share:.6f}",
                }
            )

    # OWID exposes total generation as a separate metric. The by-source component
    # sum matches that series within the two-decimal precision of the CSV.
    if largest_total_difference > 0.05:
        raise ValueError(
            "Included component sums do not reconcile with OWID total generation: "
            f"maximum difference {largest_total_difference:.6f} TWh"
        )
    if any(abs(total - 100) > 0.0001 for total in share_sums.values()):
        raise ValueError("Calculated yearly shares do not sum to 100%")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("year", "source", "generation_twh", "share_pct"),
        )
        writer.writeheader()
        writer.writerows(output_rows)

    image = download(ORIGINAL_IMAGE_URL)
    if not image.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("OWID image endpoint did not return a PNG")
    OUTPUT_IMAGE.write_bytes(image)

    return len(output_rows), largest_total_difference


if __name__ == "__main__":
    row_count, max_difference = prepare()
    print(f"Wrote {row_count} rows to {OUTPUT_CSV}")
    print(f"Wrote OWID chart export to {OUTPUT_IMAGE}")
    print(
        "Maximum component-sum difference from OWID total: "
        f"{max_difference:.6f} TWh"
    )
