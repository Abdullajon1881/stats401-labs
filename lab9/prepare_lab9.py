"""Fetch and freeze the two source artifacts used by STATS 401 Lab 9.

The 110m Natural Earth file was tested first, but it lacks HKG and SGP.  This
script therefore uses the matching pinned 10m ISO country file.  It retains
only ISO-3, name, and country geometry so the committed browser artifact is
compact relative to its source and has a stable byte representation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GDP_PATH = DATA / "lab9_gdp_2025_top50.csv"
WORLD_PATH = DATA / "lab9_world.geojson"

GDP_URL = "https://raw.githubusercontent.com/hiilab/stats-401/main/data/lab9_gdp_2025_top50.csv"
UPSTREAM_GDP_RAW_SHA256 = "c50617431a3d4bb4e0a1943fa714e43c922019ad07f4cc5d639470d5e3009f92"
NATURAL_EARTH_COMMIT = "ca96624a56bd078437bca8184e78163e5039ad19"
NATURAL_EARTH_FILE = "geojson/ne_10m_admin_0_countries_iso.geojson"
WORLD_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    f"{NATURAL_EARTH_COMMIT}/{NATURAL_EARTH_FILE}"
)
ISO_RE = re.compile(r"^[A-Z]{3}$")
REQUIRED_COLUMNS = ["iso3", "country", "gdp_2025_billion_usd", "rank"]


def fetch(url: str) -> bytes:
    """Download a source file or fail loudly with the URL in the exception."""
    request = urllib.request.Request(url, headers={"User-Agent": "stats401-lab9-prep"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"Could not fetch {url}: HTTP {response.status}")
        return response.read()


def normalize_newlines(raw: bytes) -> bytes:
    """Normalize only record separators for a deterministic committed CSV."""
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def validate_gdp(raw: bytes) -> set[str]:
    text = raw.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or list(rows[0]) != REQUIRED_COLUMNS or len(rows) != 50:
        raise ValueError("Instructor GDP CSV has unexpected schema or row count")
    ids = {row["iso3"] for row in rows}
    if len(ids) != 50 or any(not ISO_RE.fullmatch(code) for code in ids):
        raise ValueError("Instructor GDP CSV has invalid or duplicate ISO-3 values")
    for row in rows:
        if not row["country"].strip() or not math.isfinite(float(row["gdp_2025_billion_usd"])):
            raise ValueError("Instructor GDP CSV has invalid country or GDP")
    return ids


def feature_iso(properties: dict) -> str | None:
    """Natural Earth ISO_A3 is preferred; ADM0_A3 repairs known -99 values."""
    for key in ("ISO_A3", "ADM0_A3"):
        value = str(properties.get(key, "")).strip().upper()
        if ISO_RE.fullmatch(value) and value != "-99":
            return value
    return None


def compact_world(raw: bytes, gdp_isos: set[str]) -> dict:
    source = json.loads(raw.decode("utf-8"))
    if source.get("type") != "FeatureCollection":
        raise ValueError("Natural Earth source is not a FeatureCollection")
    features = []
    seen = set()
    for feature in source.get("features", []):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue
        properties = feature.get("properties") or {}
        iso3 = feature_iso(properties)
        if not iso3:
            continue
        if iso3 in seen:
            raise ValueError(f"Duplicate usable ISO-3 in Natural Earth: {iso3}")
        seen.add(iso3)
        name = str(properties.get("NAME_EN") or properties.get("NAME") or iso3).strip()
        if not name:
            raise ValueError(f"Missing name for {iso3}")
        features.append({
            "type": "Feature",
            "properties": {"iso3": iso3, "name": name},
            "geometry": geometry,
        })
    missing = sorted(gdp_isos - seen)
    if missing:
        raise ValueError("GDP ISO-3 values missing from Natural Earth: " + ", ".join(missing))
    for code in ("HKG", "TWN", "SGP"):
        if code not in seen:
            raise ValueError(f"Required economy missing from Natural Earth: {code}")
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    gdp_raw = fetch(GDP_URL)
    if hashlib.sha256(gdp_raw).hexdigest() != UPSTREAM_GDP_RAW_SHA256:
        raise ValueError("Downloaded instructor GDP CSV does not match the pinned raw SHA256")
    gdp_isos = validate_gdp(gdp_raw)
    world = compact_world(fetch(WORLD_URL), gdp_isos)
    # The instructor CSV content is preserved at record level; only line endings
    # are normalized to LF for a deterministic committed artifact.
    GDP_PATH.write_bytes(normalize_newlines(gdp_raw))
    WORLD_PATH.write_text(
        json.dumps(world, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {GDP_PATH.relative_to(ROOT)} (50 GDP rows)")
    print(f"Wrote {WORLD_PATH.relative_to(ROOT)} ({len(world['features'])} country features)")
    print("Natural Earth fallback: 110m lacks HKG and SGP; pinned 10m ISO file used.")


if __name__ == "__main__":
    main()
