"""Independent validation for the STATS 401 critique and redesign project."""

from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "critique-redesign"
DATA = ROOT / "data" / "critique_electricity_world_2010_2025.csv"
PAGE = PROJECT / "index.html"
SCRIPT = PROJECT / "critique.js"
STYLE = PROJECT / "critique.css"
ROOT_PAGE = ROOT / "index.html"

EXPECTED_COLUMNS = {"year", "source", "generation_twh", "share_pct"}
EXPECTED_SOURCES = {
    "Coal",
    "Oil",
    "Gas",
    "Nuclear",
    "Hydropower",
    "Wind",
    "Solar",
    "Bioenergy",
    "Other renewables",
}
EXPECTED_YEARS = list(range(2010, 2026))


def require(condition: bool, message: str) -> None:
    """Raise a readable validation error when a requirement is not met."""

    if not condition:
        raise AssertionError(message)


class ReportParser(HTMLParser):
    """Collect report paragraph prose and text grouped by report section."""

    def __init__(self) -> None:
        super().__init__()
        self.in_report = False
        self.in_paragraph = False
        self.current_section = ""
        self.paragraph_parts: list[str] = []
        self.paragraphs: list[str] = []
        self.sections: dict[str, list[str]] = defaultdict(list)
        self._tag_stack: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        self._tag_stack.append(tag)
        if tag == "article" and attributes.get("id") == "report-prose":
            self.in_report = True
        if self.in_report and tag == "section":
            self.current_section = attributes.get("aria-labelledby", "") or ""
        if self.in_report and tag == "p":
            self.in_paragraph = True
            self.paragraph_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self.in_report and tag == "p" and self.in_paragraph:
            paragraph = " ".join("".join(self.paragraph_parts).split())
            self.paragraphs.append(paragraph)
            self.sections[self.current_section].append(paragraph)
            self.in_paragraph = False
        if tag == "article" and self.in_report:
            self.in_report = False
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self.in_paragraph:
            self.paragraph_parts.append(data)


def validate_data() -> tuple[int, list[int]]:
    require(DATA.exists(), f"Missing data file: {DATA}")
    with DATA.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(set(reader.fieldnames or []) == EXPECTED_COLUMNS, "Incorrect CSV columns")
        raw_rows = list(reader)

    parsed: list[tuple[int, str, float, float]] = []
    keys: set[tuple[int, str]] = set()
    by_year: dict[int, list[tuple[str, float, float]]] = defaultdict(list)

    for row in raw_rows:
        year = int(row["year"])
        source = row["source"]
        generation = float(row["generation_twh"])
        share = float(row["share_pct"])
        require(math.isfinite(generation) and generation >= 0, "Invalid generation value")
        require(math.isfinite(share) and 0 <= share <= 100, "Invalid share value")
        key = (year, source)
        require(key not in keys, f"Duplicate row: {key}")
        keys.add(key)
        parsed.append((year, source, generation, share))
        by_year[year].append((source, generation, share))

    years = sorted(by_year)
    require(years == EXPECTED_YEARS, "Years must be contiguous from 2010 through 2025")
    require(len(parsed) == len(years) * len(EXPECTED_SOURCES), "Incomplete year-source grid")

    for year, rows in by_year.items():
        sources = {source for source, _, _ in rows}
        require(sources == EXPECTED_SOURCES, f"Incorrect source set in {year}")
        generation_total = sum(generation for _, generation, _ in rows)
        share_total = sum(share for _, _, share in rows)
        require(abs(share_total - 100) <= 0.00001, f"Shares do not sum to 100 in {year}")
        for source, generation, share in rows:
            expected_share = generation / generation_total * 100
            require(
                abs(share - expected_share) <= 0.000001,
                f"Share formula mismatch for {source} in {year}",
            )

    return len(parsed), years


def validate_images_and_page() -> None:
    original = PROJECT / "original-visualization.png"
    redesign = PROJECT / "redesign-visualization.png"
    for image in (original, redesign):
        require(image.exists() and image.stat().st_size > 5_000, f"Missing image: {image}")
        require(image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"Not a PNG: {image}")

    html = PAGE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    css = STYLE.read_text(encoding="utf-8")
    root_html = ROOT_PAGE.read_text(encoding="utf-8")

    require("cdn.jsdelivr.net/npm/d3@7" in html, "D3 v7 is not included")
    require("critique_electricity_world_2010_2025.csv" in script, "Local CSV is not loaded")
    require("d3.csv(DATA_PATH" in script, "D3 must load the external CSV")
    require("d3.line()" in script and "source-panel" in script, "Small multiples are missing")
    require(
        "state.shareMax = Math.ceil(d3.max(data" in script
        and ".domain([0, state.shareMax])" in script,
        "Shared data-derived y-domain logic is missing",
    )
    require(
        "sort((a, b) => b.generation_twh - a.generation_twh)" in script
        and "scaleBand()" in script,
        "Ranked horizontal bar logic is missing",
    )
    require("year-slider" in html and 'on("input"' in script, "Year slider is missing")
    require("id=\"tooltip\"" in html and "setTooltip" in script, "Reusable tooltip is missing")
    require(
        "updateHighlight" in script and "lockedSource" in script and "clear-highlight" in html,
        "Coordinated highlighting is missing",
    )
    require("aria-labelledby" in script and "role\", \"img\"" in script, "SVG accessibility text is missing")
    require("@media (max-width: 720px)" in css, "Responsive layout rules are missing")
    require("original-visualization.png" in html, "Original figure is not embedded")
    require("redesign-visualization.png" in html, "Redesign figure is not embedded")
    require("ourworldindata.org/grapher/electricity-mix" in html, "Original source link is missing")
    require("Official downloadable CSV" in html, "Data source link is missing")
    require("2026-09-27" in html, "Access date is missing")
    require("d3js.org" in html, "D3 reference is missing")

    unsafe_calls = ("innerHTML", "insertAdjacentHTML", "document.write")
    require(not any(call in script for call in unsafe_calls), "Unsafe data DOM API found")

    for lab_number in range(1, 11):
        require(f'href="lab{lab_number}/"' in root_html, f"Lab {lab_number} link changed or missing")
    require(
        root_html.count("Visualization Critique and Redesign") == 1
        and 'href="critique-redesign/"' in root_html,
        "Root project navigation link is incorrect",
    )


def validate_report() -> tuple[int, int, int, int]:
    parser = ReportParser()
    parser.feed(PAGE.read_text(encoding="utf-8"))
    prose = " ".join(parser.paragraphs)
    words = re.findall(r"\b[\w’'-]+\b", prose, flags=re.UNICODE)
    word_count = len(words)
    require(500 <= word_count <= 800, f"Report prose has {word_count} words; expected 500–800")

    required_sections = {
        "report-context",
        "report-critique",
        "report-rationale",
        "report-comparison",
        "report-tradeoffs",
    }
    require(required_sections <= parser.sections.keys(), "Required report section is missing")

    context = " ".join(parser.sections["report-context"]).lower()
    critique = " ".join(parser.sections["report-critique"]).lower()
    rationale = " ".join(parser.sections["report-rationale"]).lower()
    comparison = " ".join(parser.sections["report-comparison"]).lower()
    tradeoffs = " ".join(parser.sections["report-tradeoffs"]).lower()

    require("intended message" in context and "audience" in context, "Context lacks message or audience")
    require("main tasks" in context and "electricity generation" in context, "Context lacks viewer tasks or scope")

    strength_evidence = (
        "additive structure explicit",
        "familiar horizontal axis",
        "clear visual hierarchy",
    )
    strengths_count = sum(phrase in critique for phrase in strength_evidence)
    require(strengths_count >= 2, "Fewer than two distinct strengths are supported")

    weakness_evidence = (
        all(term in critique for term in ("fixed zero baseline", "band thickness", "common scale")),
        all(term in critique for term in ("thin bands", "relative growth", "harder to compare")),
        all(term in critique for term in ("absolute twh", "percentage share", "conflated")),
    )
    weaknesses_count = sum(weakness_evidence)
    require(weaknesses_count >= 3, "Fewer than three distinct weaknesses are supported")

    decision_evidence = (
        all(term in rationale for term in ("first redesign decision", "small-multiple", "moving-band thickness")),
        all(term in rationale for term in ("second decision", "relative trend", "absolute view")),
        all(term in rationale for term in ("third decision", "ranked horizontal bars", "bar length")),
    )
    decisions_count = sum(decision_evidence)
    require(decisions_count >= 3, "Fewer than three redesign decisions are explained")

    require("compare any two sources" in comparison and "exact twh" in comparison, "Comparison evidence is incomplete")
    require(
        "screen space" in tradeoffs
        and "single-shape impression" in tradeoffs
        and "compactness" in tradeoffs,
        "Trade-off or limitation evidence is incomplete",
    )

    return word_count, strengths_count, weaknesses_count, decisions_count


def main() -> None:
    rows, years = validate_data()
    validate_images_and_page()
    word_count, strengths, weaknesses, decisions = validate_report()
    print("VALIDATE_CRITIQUE=PASS")
    print(f"DATA_ROWS={rows}")
    print(f"DATA_YEARS={years[0]}-{years[-1]}")
    print(f"DATA_SOURCES={len(EXPECTED_SOURCES)}")
    print("YEARLY_SHARE_SUMS_RECONCILE=PASS")
    print(f"REPORT_WORD_COUNT={word_count}")
    print(f"STRENGTHS_COUNT={strengths}")
    print(f"WEAKNESSES_COUNT={weaknesses}")
    print(f"REDESIGN_DECISIONS_COUNT={decisions}")


if __name__ == "__main__":
    main()
