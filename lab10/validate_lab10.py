"""Offline validation for the Lab 10 voice extension of Lab 9."""

from __future__ import annotations

import html.parser
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


class PageFacts(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.h1_count = 0
        self.title = ""
        self.in_title = False
        self.in_reflection = False
        self.reflection: list[str] = []
        self.lab10_current = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "link" and values.get("href"):
            self.links.append(values["href"])
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        if tag == "h1":
            self.h1_count += 1
        if tag == "title":
            self.in_title = True
        if values.get("id") == "reflection-text":
            self.in_reflection = True
        if tag == "a" and values.get("href") == "../lab10/" and values.get("aria-current") == "page":
            self.lab10_current = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag == "div" and self.in_reflection:
            self.in_reflection = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        if self.in_reflection:
            self.reflection.append(data)


def validate_html(path: Path) -> int:
    facts = PageFacts()
    facts.feed(path.read_text(encoding="utf-8"))
    require(facts.title.strip() == "Lab 10: Novel Interaction with Visualizations", "Incorrect page title")
    require(facts.h1_count == 1, "Page must have exactly one h1")
    require(facts.lab10_current, "Lab 10 navigation item lacks aria-current")
    for asset in ("../lab9/lab9.css", "lab10.css"):
        require(asset in facts.links, f"Required stylesheet missing: {asset}")
    required_scripts = ["https://d3js.org/d3.v7.min.js", "../lab9/lab9.js", "lab10.js"]
    require(facts.scripts == required_scripts, "Required scripts or their order are incorrect")
    for element_id in ("stat-count", "stat-high", "stat-low", "country-select", "clear-selection", "reset-map", "selection-status", "choropleth-map", "choropleth-legend", "cartogram-map", "tooltip", "voice-button", "voice-status", "voice-heard", "voice-action", "reflection-text"):
        require(element_id in facts.ids, f"Required element missing: {element_id}")
    words = re.findall(r"\b[\w’'-]+\b", " ".join(facts.reflection))
    require(100 <= len(words) <= 200, f"Reflection must be 100..200 words, got {len(words)}")
    return len(words)


def validate_source(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for token in ("window.SpeechRecognition", "window.webkitSpeechRecognition", 'recognition.lang = "en-US"', "recognition.continuous = false", "recognition.interimResults = false", "recognition.onresult", "recognition.onerror", "recognition.onend", "voiceButton.addEventListener(\"click\", startListening)", "normalizeSpeech", "parseVoiceCommand", "select.dispatchEvent(new Event(\"change\", { bubbles: true }))", "clearButton.click()", "resetButton.click()"):
        require(token in source, f"Voice implementation missing: {token}")
    require(source.count("recognition.start()") == 1, "Recognition start must appear only in the explicit start handler")
    require("recognition.continuous = true" not in source, "Continuous recognition must be disabled")
    require("navigator.mediaDevices.getUserMedia" not in source, "Voice-only implementation must not request a camera")
    for forbidden in ("d3.geoEqualEarth()", "d3.geoPath()", "d3.zoom()", "lab9_gdp_2025_top50.csv", "lab9_world.geojson"):
        require(forbidden not in source, f"Lab 10 must reuse Lab 9 rather than duplicate: {forbidden}")
    for unsafe in ("innerHTML", "insertAdjacentHTML", "outerHTML", "document.write"):
        require(unsafe not in source, f"Unsafe DOM API found: {unsafe}")
    require("typeof window !== \"undefined\"" in source and "typeof document !== \"undefined\"" in source, "Browser initialization guard missing")
    require("module.exports = { normalizeSpeech, parseVoiceCommand }" in source, "Pure helpers are not exported for Node")


def validate_parser(js_path: Path) -> None:
    program = r'''
const {normalizeSpeech, parseVoiceCommand} = require(process.argv[1]);
const economies = [
  {iso3:'USA', country:'United States'}, {iso3:'JPN', country:'Japan'},
  {iso3:'SGP', country:'Singapore'}, {iso3:'HKG', country:'Hong Kong SAR'},
  {iso3:'KOR', country:'Korea, Republic of'}
];
function expect(command, type, iso) { const r=parseVoiceCommand(command,economies); if(r.type!==type || (iso && r.iso3!==iso)) throw new Error(command + JSON.stringify(r)); }
expect('Highlight Japan','select-country','JPN');
expect('select singapore','select-country','SGP');
expect('show Hong Kong','select-country','HKG');
expect('highlight south korea','select-country','KOR');
expect('clear selection','clear-selection'); expect('reset map','reset-map'); expect('help','help'); expect('something unrelated','unknown');
if(normalizeSpeech('  HIGHLIGHT,   Japan!! ') !== 'highlight japan') throw new Error('normalization');
if(parseVoiceCommand('',economies).type !== 'unknown') throw new Error('empty transcript');
if(parseVoiceCommand('highlight Atlantis',economies).type !== 'unknown') throw new Error('unknown country');
if(parseVoiceCommand('highlight Japan',[]).type !== 'not-ready') throw new Error('empty economy list');
'''
    result = subprocess.run(["node", "-e", program, str(js_path)], capture_output=True, text=True, check=False)
    require(result.returncode == 0, "Node parser test failed: " + result.stderr)


def expect_rejection(label: str, action) -> None:
    try:
        action()
    except ValueError:
        print(f"Failure check: {label}: rejected")
        return
    raise ValueError(f"Failure check did not reject: {label}")


def run_failure_checks(html_path: Path, js_path: Path) -> None:
    """Exercise isolated source and reflection failures without altering Lab 10."""
    source = js_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="lab10-validation-") as directory:
        temp = Path(directory)
        candidate_js = temp / "lab10.js"
        candidate_html = temp / "index.html"
        candidate_js.write_text(source, encoding="utf-8")
        candidate_html.write_text(html, encoding="utf-8")
        print("Failure check: unsupported browser: handled by source guard")
        print("Failure check: unknown command: rejected safely by parser")
        print("Failure check: empty transcript: rejected safely by parser")
        print("Failure check: unknown country: rejected safely by parser")
        print("Failure check: empty economy list: returns not-ready")
        candidate_js.write_text(source + "\ndocument.innerHTML = 'bad';\n", encoding="utf-8")
        expect_rejection("unsafe DOM", lambda: validate_source(candidate_js))
        candidate_js.write_text(source + "\nrecognition.continuous = true;\n", encoding="utf-8")
        expect_rejection("continuous recognition", lambda: validate_source(candidate_js))
        candidate_js.write_text(source + "\nrecognition.start();\n", encoding="utf-8")
        expect_rejection("automatic recognition start", lambda: validate_source(candidate_js))
        candidate_js.write_text(source, encoding="utf-8")
        short_html = re.sub(r'(<div id="reflection-text"[^>]*>).*?(</div>)', r'\1<p>Brief.</p>\2', html, flags=re.DOTALL)
        candidate_html.write_text(short_html, encoding="utf-8")
        expect_rejection("short reflection", lambda: validate_html(candidate_html))
        long_html = re.sub(r'(<div id="reflection-text"[^>]*>).*?(</div>)', r'\1<p>' + ("word " * 210) + r'</p>\2', html, flags=re.DOTALL)
        candidate_html.write_text(long_html, encoding="utf-8")
        expect_rejection("long reflection", lambda: validate_html(candidate_html))


def main() -> None:
    html_path = ROOT / "lab10" / "index.html"
    js_path = ROOT / "lab10" / "lab10.js"
    words = validate_html(html_path)
    validate_source(js_path)
    validate_parser(js_path)
    run_failure_checks(html_path, js_path)
    print("HTML and Lab 9 reuse validation: PASS")
    print("Voice source validation: PASS")
    print("Node command parser validation: PASS")
    print(f"Reflection word count: {words}")
    print("Lab 10 validation: PASS")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("Lab 10 validation: FAIL - " + str(error), file=sys.stderr)
        raise SystemExit(1)
