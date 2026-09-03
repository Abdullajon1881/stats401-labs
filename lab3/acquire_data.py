"""Lab 3 data acquisition.

Source: GBIF Occurrence Search API
Docs:   https://techdocs.gbif.org/en/openapi/v1/occurrence

GBIF publishes an open, read-only REST API. Search requests need no
authentication or API key, and https://api.gbif.org/robots.txt only
disallows /v1/image/unsafe, so this endpoint is open to automated clients.
GBIF asks callers to send a User-Agent so they can make contact if a script
misbehaves, and to keep the request rate modest.

This script pages through bird (class Aves) occurrence records and writes
them to data/lab3_data.csv.
"""

from pathlib import Path
import time

import pandas as pd
import requests

API_URL = "https://api.gbif.org/v1/occurrence/search"
TAXON_KEY = 212  # class Aves (birds)
PAGE_SIZE = 200
TARGET_RECORDS = 1200
MIN_RECORDS = 1000
MAX_PAGES = 20
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

    for page in range(MAX_PAGES):
        if page > 0:
            time.sleep(DELAY_SECONDS)

        offset = page * PAGE_SIZE
        params = {
            "taxonKey": TAXON_KEY,
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
            print(f"Request failed at offset {offset}: {error}")
            continue

        requests_made += 1

        try:
            payload = response.json()
        except ValueError as error:
            print(f"Could not read JSON at offset {offset}: {error}")
            continue

        results = payload.get("results", [])
        if not results:
            print(f"No results returned at offset {offset}; stopping.")
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

        print(f"Collected {len(records)} records after {requests_made} request(s)")

        if len(records) >= TARGET_RECORDS:
            break
        if payload.get("endOfRecords"):
            print("API reported the end of the result set; stopping.")
            break

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
