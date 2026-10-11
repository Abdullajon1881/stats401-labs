"""Offline validation for Lab 9's frozen data artifacts and implementation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html.parser
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NORMALIZED_GDP_SHA256 = "606fae0731ce99defcdac987579569c31076687a9ac423da252d1c0f70039450"
REQUIRED_COLUMNS = ["iso3", "country", "gdp_2025_billion_usd", "rank"]
ISO_RE = re.compile(r"^[A-Z]{3}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def normalize_newlines(raw: bytes) -> bytes:
    """Normalize line endings without changing any CSV record content."""
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def validate_gdp(path: Path, check_hash: bool = True) -> list[dict[str, str]]:
    raw = path.read_bytes()
    normalized = normalize_newlines(raw)
    if check_hash:
        require(
            hashlib.sha256(normalized).hexdigest() == EXPECTED_NORMALIZED_GDP_SHA256,
            "GDP file normalized SHA256 differs from instructor source",
        )
    rows = list(csv.DictReader(normalized.decode("utf-8").splitlines()))
    require(rows and list(rows[0]) == REQUIRED_COLUMNS, "GDP columns are not exact")
    require(len(rows) == 50, "GDP row count must be 50")
    isos = [row["iso3"] for row in rows]
    countries = [row["country"] for row in rows]
    ranks = [int(row["rank"]) for row in rows]
    gdps = [float(row["gdp_2025_billion_usd"]) for row in rows]
    require(len(set(isos)) == 50, "GDP ISO-3 values must be unique")
    require(len(set(countries)) == 50, "GDP country names must be unique")
    require(len(set(ranks)) == 50 and sorted(ranks) == list(range(1, 51)), "GDP ranks must be exactly 1..50")
    require(all(ISO_RE.fullmatch(code or "") for code in isos), "GDP ISO-3 is malformed")
    require(all(name.strip() for name in countries), "GDP country name is blank")
    require(all(math.isfinite(value) and value > 0 for value in gdps), "GDP must be finite and positive")
    ordered = sorted(zip(ranks, gdps))
    require(all(ordered[i][1] > ordered[i + 1][1] for i in range(len(ordered) - 1)), "GDP must strictly decrease with rank")
    expected = {"USA": (1, 30615.743), "CHN": (2, 19398.577), "KAZ": (50, 300.052)}
    by_iso = {row["iso3"]: row for row in rows}
    for code, (rank, value) in expected.items():
        require(code in by_iso and int(by_iso[code]["rank"]) == rank and abs(float(by_iso[code]["gdp_2025_billion_usd"]) - value) < 1e-9, f"GDP anchor mismatch for {code}")
    return rows


def all_coordinates_finite(value: object) -> bool:
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(all_coordinates_finite(item) for item in value)
    return False


def validate_world(path: Path, rows: list[dict[str, str]]) -> None:
    world = json.loads(path.read_text(encoding="utf-8"))
    require(world.get("type") == "FeatureCollection", "World GeoJSON is not a FeatureCollection")
    features = world.get("features")
    require(isinstance(features, list) and features, "World GeoJSON has no features")
    isos = []
    for feature in features:
        require(feature.get("type") == "Feature", "World item is not a Feature")
        properties = feature.get("properties") or {}
        iso3 = properties.get("iso3")
        require(isinstance(iso3, str) and ISO_RE.fullmatch(iso3), "World feature has invalid ISO-3")
        require(bool(str(properties.get("name", "")).strip()), "World feature has blank name")
        geometry = feature.get("geometry") or {}
        require(geometry.get("type") in {"Polygon", "MultiPolygon"}, "World geometry must be Polygon/MultiPolygon")
        require(all_coordinates_finite(geometry.get("coordinates")), "World geometry has non-finite coordinates")
        isos.append(iso3)
    require(len(isos) == len(set(isos)), "World GeoJSON has duplicate ISO-3")
    gdp_isos = {row["iso3"] for row in rows}
    world_isos = set(isos)
    missing = sorted(gdp_isos - world_isos)
    require(not missing, "GDP ISO-3 values missing from world geometry: " + ", ".join(missing))
    for code in ("HKG", "TWN", "SGP"):
        require(code in world_isos, f"Required geographic match missing: {code}")
    require(bool(world_isos - gdp_isos), "World geometry needs no-data country context")


class ComparisonText(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inside = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "div" and dict(attrs).get("id") == "comparison-text":
            self.inside = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self.inside:
            self.inside = False

    def handle_data(self, data: str) -> None:
        if self.inside:
            self.parts.append(data)


def validate_implementation(html_path: Path, js_path: Path) -> int:
    html = html_path.read_text(encoding="utf-8")
    js = js_path.read_text(encoding="utf-8")
    for token in ("d3.v7", "choropleth-map", "cartogram-map", "country-select", "clear-selection", "reset-map", "comparison-text"):
        require(token in html, f"HTML missing required item: {token}")
    for token in ("d3.geoEqualEarth()", "d3.geoPath()", "d3.csv(DATA + \"lab9_gdp_2025_top50.csv\"", "d3.json(DATA + \"lab9_world.geojson\"", "scaleSequentialLog", "d3.zoom()", "hoverIso", "lockedIso", "path.area(feature)", "path.centroid(feature)", "Math.sqrt(targetArea / baseArea)", "cartogramScale"):
        require(token in js, f"JavaScript missing required implementation evidence: {token}")
    require("innerHTML" not in js and "insertAdjacentHTML" not in js and "outerHTML" not in js and "document.write" not in js, "Unsafe data DOM API found in JavaScript")
    parser = ComparisonText()
    parser.feed(html)
    words = re.findall(r"\b[\w’'-]+\b", " ".join(parser.parts))
    require(150 <= len(words) <= 250, f"Comparison prose must have 150..250 words, got {len(words)}")
    return len(words)


def validate_node_helper(js_path: Path) -> None:
    code = (
        "const f=require(process.argv[1]).cartogramScale;"
        "const total=100, budget=1000;"
        "const a=100*f(100,25,total,budget)**2;"
        "const b=100*f(100,50,total,budget)**2;"
        "if(Math.abs(a/b-.5)>1e-12)process.exit(1);"
        "try{f(0,1,1,1);process.exit(1)}catch(e){}"
    )
    result = subprocess.run(["node", "-e", code, str(js_path)], capture_output=True, text=True, check=False)
    require(result.returncode == 0, "Node cartogram proportional-area unit test failed: " + result.stderr)


def expect_rejection(label: str, action) -> None:
    try:
        action()
    except (ValueError, json.JSONDecodeError, csv.Error):
        print(f"Failure check: {label}: rejected")
        return
    raise ValueError(f"Failure check did not reject: {label}")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def run_failure_checks(gdp_path: Path, world_path: Path, html_path: Path, js_path: Path) -> None:
    """Exercise required bad inputs in an isolated temporary directory."""
    good_rows = list(csv.DictReader(gdp_path.read_text(encoding="utf-8").splitlines()))
    good_world = json.loads(world_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="lab9-validation-") as directory:
        temp = Path(directory)
        bad_gdp = temp / "gdp.csv"
        def test_gdp(label: str, mutate) -> None:
            rows = [dict(row) for row in good_rows]
            mutate(rows)
            write_csv(bad_gdp, rows)
            expect_rejection(label, lambda: validate_gdp(bad_gdp, check_hash=False))
        test_gdp("duplicate GDP ISO", lambda rows: rows.__setitem__(1, {**rows[1], "iso3": "USA"}))
        test_gdp("missing rank", lambda rows: rows.__setitem__(0, {**rows[0], "rank": ""}))
        test_gdp("non-positive GDP", lambda rows: rows.__setitem__(0, {**rows[0], "gdp_2025_billion_usd": "0"}))
        test_gdp("rank/GDP order", lambda rows: rows.__setitem__(1, {**rows[1], "gdp_2025_billion_usd": "40000"}))
        test_gdp("malformed ISO", lambda rows: rows.__setitem__(0, {**rows[0], "iso3": "US"}))
        normalized_good = normalize_newlines(gdp_path.read_bytes())
        lf_gdp = temp / "correct-lf.csv"
        crlf_gdp = temp / "correct-crlf.csv"
        lf_gdp.write_bytes(normalized_good)
        crlf_gdp.write_bytes(normalized_good.replace(b"\n", b"\r\n"))
        validate_gdp(lf_gdp)
        print("Portability check: LF checkout validation: passed")
        validate_gdp(crlf_gdp)
        print("Portability check: CRLF checkout validation: passed")
        bad_gdp.write_bytes(normalized_good.replace(b"30615.743", b"30615.744", 1))
        expect_rejection("GDP source content mutation", lambda: validate_gdp(bad_gdp))
        def test_world(label: str, mutate) -> None:
            world = json.loads(json.dumps(good_world))
            mutate(world["features"])
            candidate = temp / "world.geojson"
            candidate.write_text(json.dumps(world), encoding="utf-8")
            expect_rejection(label, lambda: validate_world(candidate, good_rows))
        test_world("missing HKG geometry", lambda features: features.__setitem__(next(i for i, f in enumerate(features) if f["properties"]["iso3"] == "HKG"), {**next(f for f in features if f["properties"]["iso3"] == "HKG"), "properties": {"iso3": "ZZZ", "name": "Test"}}))
        test_world("missing top-50 geometry", lambda features: features.__setitem__(next(i for i, f in enumerate(features) if f["properties"]["iso3"] == "USA"), {**next(f for f in features if f["properties"]["iso3"] == "USA"), "properties": {"iso3": "ZZZ", "name": "Test"}}))
        test_world("duplicate GeoJSON ISO", lambda features: features.__setitem__(1, {**features[1], "properties": {**features[1]["properties"], "iso3": features[0]["properties"]["iso3"]}}))
        candidate_html = temp / "index.html"
        candidate_js = temp / "lab9.js"
        candidate_html.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
        candidate_js.write_text(js_path.read_text(encoding="utf-8"), encoding="utf-8")
        short_html = re.sub(r'(<div id="comparison-text"[^>]*>).*?(</div>)', r'\1<p>Brief.</p>\2', html_path.read_text(encoding="utf-8"), flags=re.DOTALL)
        candidate_html.write_text(short_html, encoding="utf-8")
        expect_rejection("short comparison", lambda: validate_implementation(candidate_html, candidate_js))
        long_html = re.sub(r'(<div id="comparison-text"[^>]*>).*?(</div>)', r'\1<p>' + ("word " * 260) + r'</p>\2', html_path.read_text(encoding="utf-8"), flags=re.DOTALL)
        candidate_html.write_text(long_html, encoding="utf-8")
        expect_rejection("long comparison", lambda: validate_implementation(candidate_html, candidate_js))
        candidate_html.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
        candidate_js.write_text(js_path.read_text(encoding="utf-8") + "\nconst unsafe = document.innerHTML;\n", encoding="utf-8")
        expect_rejection("unsafe DOM API", lambda: validate_implementation(candidate_html, candidate_js))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gdp", type=Path, default=ROOT / "data" / "lab9_gdp_2025_top50.csv")
    parser.add_argument("--world", type=Path, default=ROOT / "data" / "lab9_world.geojson")
    parser.add_argument("--html", type=Path, default=ROOT / "lab9" / "index.html")
    parser.add_argument("--js", type=Path, default=ROOT / "lab9" / "lab9.js")
    parser.add_argument("--failure-checks", action="store_true", help="run isolated negative validation checks")
    args = parser.parse_args()
    rows = validate_gdp(args.gdp)
    validate_world(args.world, rows)
    words = validate_implementation(args.html, args.js)
    validate_node_helper(args.js)
    if args.failure_checks:
        run_failure_checks(args.gdp, args.world, args.html, args.js)
    print("GDP validation: 50 rows, ranks 1..50, normalized instructor SHA256")
    print("Join validation: 50 matched; HKG, TWN, SGP matched; name fallback unused")
    print(f"World GeoJSON validation: {len(json.loads(args.world.read_text(encoding='utf-8'))['features'])} features")
    print("Cartogram Node unit test: proportional area passed")
    print(f"Comparison word count: {words}")
    print("Lab 9 validation: PASS")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError, csv.Error) as error:
        print("Lab 9 validation: FAIL - " + str(error), file=sys.stderr)
        raise SystemExit(1)
