"""Lab 3 data acquisition.

Source: GBIF Occurrence Search API
Docs:   https://techdocs.gbif.org/en/openapi/v1/occurrence

GBIF publishes an open, read-only REST API. Search requests need no
authentication or API key, and https://api.gbif.org/robots.txt only
disallows /v1/image/unsafe, so this endpoint is open to automated clients.
GBIF asks callers to send a User-Agent so they can make contact if a script
misbehaves, and to keep the request rate modest.

This script walks bird (class Aves) occurrence records month by month and
writes them to data/lab3_data.csv. Querying each year/month slice keeps the
sample spread across seasons instead of returning only the newest records,
which is what a single unfiltered query gives back.
"""

from pathlib import Path
import time

import pandas as pd
import requests

API_URL = "https://api.gbif.org/v1/occurrence/search"
TAXON_KEY = 212  # class Aves (birds)
YEARS = (2022, 2023, 2024)
MONTHS = range(1, 13)
PAGE_SIZE = 34
RECORDS_PER_SLICE = 34
TARGET_RECORDS = 1200
MIN_RECORDS = 1000
MAX_PAGES_PER_SLICE = 5
DELAY_SECONDS = 1.0
REQUEST_TIMEOUT = 20

HEADERS = {"User-Agent": "STATS401-Lab3-ClassExercise/1.0 (nuuz2820@gmail.com)"}

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "lab3_data.csv"

COLUMNS = [
    "key",
    "scientific_name",
    "species",
    "family",
    "country",
    "year",
    "month",
    "basis_of_record",
]


def extract_record(item):
    """Turn one raw API result into a flat row, blanking anything missing."""
    return {
        "key": item.get("key", ""),
        "scientific_name": item.get("scientificName", ""),
        "species": item.get("species", ""),
        "family": item.get("family", ""),
        "country": item.get("country", ""),
        "year": item.get("year", ""),
        "month": item.get("month", ""),
        "basis_of_record": item.get("basisOfRecord", ""),
    }


def collect_records():
    records = []
    seen_keys = set()
    requests_made = 0

    # months outer, years inner, so every month and year is reached before
    # the target count is met
    for month in MONTHS:
        for year in YEARS:
            collected_here = 0

            for page in range(MAX_PAGES_PER_SLICE):
                if requests_made > 0:
                    time.sleep(DELAY_SECONDS)

                offset = page * PAGE_SIZE
                params = {
                    "taxonKey": TAXON_KEY,
                    "year": year,
                    "month": month,
                    "limit": PAGE_SIZE,
                    "offset": offset,
                }

                try:
                    response = requests.get(
                        API_URL,
                        params=params,
                        headers=HEADERS,
                        timeout=REQUEST_TIMEOUT,
                    )
                    response.raise_for_status()
                except requests.RequestException as error:
                    print(f"Request failed for {year}-{month:02d} at offset {offset}: {error}")
                    continue

                requests_made += 1

                try:
                    payload = response.json()
                except ValueError as error:
                    print(f"Could not read JSON for {year}-{month:02d}: {error}")
                    continue

                results = payload.get("results", [])
                if not results:
                    break

                for item in results:
                    record = extract_record(item)
                    # skip duplicates and rows with no identifier or no name
                    if not record["key"] or record["key"] in seen_keys:
                        continue
                    if not record["scientific_name"]:
                        continue
                    seen_keys.add(record["key"])
                    records.append(record)
                    collected_here += 1

                if collected_here >= RECORDS_PER_SLICE:
                    break
                if payload.get("endOfRecords"):
                    break

            print(f"{year}-{month:02d}: {len(records)} records after {requests_made} request(s)")

            if len(records) >= TARGET_RECORDS:
                return records, requests_made

    return records, requests_made


def main():
    records, requests_made = collect_records()

    if len(records) < MIN_RECORDS:
        raise SystemExit(
            f"Only collected {len(records)} records, need at least {MIN_RECORDS}."
        )

    frame = pd.DataFrame(records, columns=COLUMNS)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")

    print(f"Made {requests_made} request(s) to {API_URL}")
    print(f"Wrote {len(frame)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
