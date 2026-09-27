"""Independent validator for Lab 8: the semantic corpus, the derived data
artifacts, the page implementation, and the evidence behind the written findings.

Run from the repository root:

    python lab8/validate_lab8.py

Exits with status 1 if any check fails. It recomputes the numeric facts quoted in
lab8/index.html directly from the committed data so the prose cannot drift from the
artifacts.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

LAB_DIR = Path(__file__).resolve().parent
ROOT = LAB_DIR.parent
DATA_DIR = ROOT / "data"

PASSAGES_CSV = DATA_DIR / "lab8_bulletin_passages.csv"
SUMMARY_JSON = DATA_DIR / "lab8_corpus_summary.json"
SECTION_CSV = DATA_DIR / "lab8_section_summary.csv"
TERMS_CSV = DATA_DIR / "lab8_top_terms.csv"
MAP_CSV = DATA_DIR / "lab8_embedding_map.csv"
NEIGHBORS_JSON = DATA_DIR / "lab8_neighbors.json"
MATRIX_CSV = DATA_DIR / "lab8_topic_section_matrix.csv"
HTML_PATH = LAB_DIR / "index.html"
JS_PATH = LAB_DIR / "lab8.js"
CSS_PATH = LAB_DIR / "lab8.css"

EXPECTED_K = 10
N_NEIGHBORS = 5
CONTENT_START_PAGE = 10
PDF_PAGES = 400

failures = []


def check(condition, message):
    print(f"[{'ok  ' if condition else 'FAIL'}] {message}")
    if not condition:
        failures.append(message)
    return bool(condition)


def section(title):
    print("\n" + title)
    print("-" * len(title))


def entropy_of(counts):
    total = counts.sum()
    if total == 0:
        return 0.0
    probs = counts[counts > 0] / total
    value = float(-(probs * np.log2(probs)).sum())
    return 0.0 if abs(value) < 1e-9 else value


# --------------------------------------------------------------------------- #
# corpus                                                                      #
# --------------------------------------------------------------------------- #


def check_corpus():
    section("CORPUS")
    if not check(PASSAGES_CSV.is_file(), "lab8_bulletin_passages.csv exists"):
        return None
    df = pd.read_csv(PASSAGES_CSV, dtype={"printed_page": str}).fillna(
        {"subsection": "", "printed_page": ""})

    required = ["passage_id", "chapter", "section", "subsection", "page",
                "text", "text_clean", "word_count"]
    check(all(c in df.columns for c in required), f"required columns present: {required}")

    check(df["passage_id"].is_unique, "passage_id is unique")
    check(df["passage_id"].str.match(r"^p\d{4}$").all(), "passage_id matches p####")
    check(df["text_clean"].fillna("").str.strip().astype(bool).all(), "text_clean is never empty")
    check(not df["text_clean"].duplicated().any(), "no exact duplicate cleaned passages")

    wc = df["word_count"]
    check(np.isfinite(wc).all() and (wc > 0).all(), "word_count is finite and positive")
    recomputed = df["text_clean"].str.split().str.len()
    check((recomputed == wc).all(), "word_count matches text_clean token count")

    pages = df["page"]
    check(pages.between(CONTENT_START_PAGE, PDF_PAGES).all(),
          f"page numbers in [{CONTENT_START_PAGE}, {PDF_PAGES}]")

    check(df["chapter"].fillna("").str.strip().astype(bool).all(), "chapter is never empty")
    check(df["section"].fillna("").str.strip().astype(bool).all(), "section is never empty")

    count = len(df)
    check(800 <= count <= 4000, f"reasonable cleaned passage count ({count})")

    # hierarchy sanity
    check(df["chapter"].str.match(r"^Part \d+:").all(),
          "every chapter is a known 'Part N:' heading")
    sec_to_chapters = df.groupby("section")["chapter"].nunique()
    check((sec_to_chapters == 1).all(),
          "each formal section maps to a single chapter (consistent hierarchy)")

    # artifacts absent
    dotted = df["text_clean"].str.contains(r"\.{5,}", regex=True)
    check(not dotted.any(), "no table-of-contents dotted-line artifacts")
    pure_numbers = df["text_clean"].str.match(r"^[\d\s.]+$")
    check(not pure_numbers.any(), "no standalone page-number passages")

    # manual samples from early / middle / late bulletin
    for lo, hi, label in [(10, 40, "early"), (150, 260, "middle"), (360, 400, "late")]:
        sample = df[df["page"].between(lo, hi)]
        check(len(sample) > 0 and sample["section"].str.strip().astype(bool).all(),
              f"{label} bulletin sample (pages {lo}-{hi}) has non-empty sections")

    return df


def check_summary(df):
    section("CORPUS SUMMARY")
    if not check(SUMMARY_JSON.is_file(), "lab8_corpus_summary.json exists"):
        return
    s = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    for key in ["bulletin_title", "bulletin_version", "source", "accessed_date",
                "pdf_pages", "raw_passages", "clean_passages", "average_word_count",
                "formal_section_count"]:
        check(key in s, f"summary has '{key}'")
    check("timestamp" not in json.dumps(s).lower(), "summary carries no generation timestamp")
    if df is not None:
        check(s["clean_passages"] == len(df), "summary clean_passages matches corpus")
        check(s["formal_section_count"] == df["section"].nunique(),
              "summary formal_section_count matches corpus")
        check(abs(s["average_word_count"] - round(df["word_count"].mean(), 2)) < 0.01,
              "summary average_word_count matches corpus")
        check(s["pdf_pages"] == PDF_PAGES, f"summary pdf_pages is {PDF_PAGES}")


# --------------------------------------------------------------------------- #
# semantic map                                                                #
# --------------------------------------------------------------------------- #


def check_map(corpus):
    section("SEMANTIC MAP DATA")
    if not check(MAP_CSV.is_file(), "lab8_embedding_map.csv exists"):
        return None
    df = pd.read_csv(MAP_CSV).fillna({"subsection": ""})
    required = ["passage_id", "chapter", "section", "subsection", "page", "text",
                "word_count", "cluster", "cluster_name", "x", "y"]
    check(all(c in df.columns for c in required), f"map has required columns: {required}")

    if corpus is not None:
        check(len(df) == len(corpus), "map row count == cleaned corpus count")
        check(set(df["passage_id"]) == set(corpus["passage_id"]),
              "map passage_id set == corpus passage_id set")
        merged = df.merge(corpus[["passage_id", "word_count"]], on="passage_id",
                          suffixes=("_map", "_corpus"))
        check((merged["word_count_map"] == merged["word_count_corpus"]).all(),
              "map word_count agrees with corpus")

    check(np.isfinite(df["x"]).all() and np.isfinite(df["y"]).all(), "x/y are finite")
    check((df["cluster"] == df["cluster"].astype(int)).all(), "cluster is integer-valued")
    check(df["cluster_name"].fillna("").str.strip().astype(bool).all(), "cluster_name never empty")

    clusters = sorted(df["cluster"].unique())
    check(clusters == list(range(EXPECTED_K)), f"clusters are 0..{EXPECTED_K - 1}")
    label_map = df.groupby("cluster")["cluster_name"].nunique()
    check((label_map == 1).all(), "each cluster id has exactly one label")
    generic = df["cluster_name"].str.match(r"(?i)^(cluster|topic|misc)")
    check(not generic.any(), "no generic unlabeled topic names")
    return df


# --------------------------------------------------------------------------- #
# matrix                                                                       #
# --------------------------------------------------------------------------- #


def check_matrix(map_df):
    section("TOPIC x SECTION MATRIX")
    if not check(MATRIX_CSV.is_file(), "lab8_topic_section_matrix.csv exists"):
        return
    m = pd.read_csv(MATRIX_CSV)
    for col in ["section", "topic", "count", "section_total", "proportion"]:
        check(col in m.columns, f"matrix has '{col}'")

    if map_df is None:
        return
    sections = sorted(map_df["section"].unique())
    topics = sorted(map_df["cluster_name"].unique())
    check(len(m) == len(sections) * len(topics),
          f"complete section x topic grid ({len(sections)} x {len(topics)} = {len(sections) * len(topics)})")
    check(not m.duplicated(subset=["section", "topic"]).any(), "unique section/topic cells")
    check((m["count"] >= 0).all(), "counts are non-negative")
    check(m["proportion"].between(0, 1).all(), "proportion in [0, 1]")

    check(int(m["count"].sum()) == len(map_df), "cell counts sum to the corpus size")

    section_totals = map_df.groupby("section").size()
    grid_totals = m.groupby("section")["count"].sum()
    check(all(int(grid_totals[s]) == int(section_totals[s]) for s in sections),
          "per-section matrix sum == corpus section count")

    prop_ok = True
    for _, r in m.iterrows():
        if r["section_total"] > 0:
            expected = round(r["count"] / r["section_total"], 6)
            if abs(expected - r["proportion"]) > 1e-6:
                prop_ok = False
                break
    check(prop_ok, "proportion == count / section_total for every cell")


# --------------------------------------------------------------------------- #
# neighbours                                                                   #
# --------------------------------------------------------------------------- #


def check_neighbors(map_df):
    section("NEAREST NEIGHBOURS")
    if not check(NEIGHBORS_JSON.is_file(), "lab8_neighbors.json exists"):
        return None
    nb = json.loads(NEIGHBORS_JSON.read_text(encoding="utf-8"))
    if map_df is None:
        return nb
    ids = set(map_df["passage_id"])

    check(set(nb.keys()) == ids, "neighbours cover exactly the corpus passages")
    all_five = all(len(v) == N_NEIGHBORS for v in nb.values())
    check(all_five, f"every passage has exactly {N_NEIGHBORS} neighbours")

    problems = {"self": 0, "dup": 0, "unknown": 0, "bad_sim": 0, "unsorted": 0}
    for pid, entry in nb.items():
        nids = [e["passage_id"] for e in entry]
        sims = [e["similarity"] for e in entry]
        if pid in nids:
            problems["self"] += 1
        if len(set(nids)) != len(nids):
            problems["dup"] += 1
        if any(n not in ids for n in nids):
            problems["unknown"] += 1
        if any((not math.isfinite(s)) or s < -1 or s > 1 for s in sims):
            problems["bad_sim"] += 1
        if sims != sorted(sims, reverse=True):
            problems["unsorted"] += 1
    check(problems["self"] == 0, "no passage is its own neighbour")
    check(problems["dup"] == 0, "neighbour ids are unique per passage")
    check(problems["unknown"] == 0, "every neighbour id is a valid passage")
    check(problems["bad_sim"] == 0, "similarities are finite and within [-1, 1]")
    check(problems["unsorted"] == 0, "neighbours are sorted by descending similarity")
    return nb


# --------------------------------------------------------------------------- #
# page implementation                                                          #
# --------------------------------------------------------------------------- #


def check_html():
    section("HTML / PAGE REQUIREMENTS")
    if not check(HTML_PATH.is_file(), "lab8/index.html exists"):
        return ""
    html = HTML_PATH.read_text(encoding="utf-8")

    required = [
        ("page title names Lab 8", r"<title>[^<]*Lab 8[^<]*</title>"),
        ("lab title heading", r"<h1>\s*Lab 8: Web Text Data and Visualization\s*</h1>"),
        ("D3 v7 from CDN", r"cdn\.jsdelivr\.net/npm/d3@7"),
        ("lab8.css linked", r'href="lab8\.css"'),
        ("global stylesheet linked", r'href="\.\./css/style\.css"'),
        ("lab8.js loaded", r'src="lab8\.js"'),
        ("Lab 8 marked aria-current", r'href="\.\./lab8/"\s+aria-current="page"'),
        ("bulletin metadata title slot", r'id="meta-title"'),
        ("bulletin metadata version slot", r'id="meta-version"'),
        ("bulletin source link slot", r'id="meta-source"'),
        ("bulletin accessed slot", r'id="meta-accessed"'),
        ("corpus counter: pdf pages", r'id="stat-pages"'),
        ("corpus counter: raw passages", r'id="stat-raw"'),
        ("corpus counter: clean passages", r'id="stat-clean"'),
        ("corpus counter: avg words", r'id="stat-avg"'),
        ("corpus counter: sections", r'id="stat-sections"'),
        ("passages-by-section chart", r'id="section-chart"'),
        ("top-terms chart", r'id="terms-chart"'),
        ("search input", r'id="search"'),
        ("topic filter", r'id="topic-filter"'),
        ("section filter", r'id="section-filter"'),
        ("reset control", r'id="reset-map"'),
        ("semantic map svg", r'id="semantic-map"'),
        ("detail panel", r'id="detail-body"'),
        ("nearest-neighbour panel", r'id="neighbor-list"'),
        ("topic legend", r'id="topic-legend"'),
        ("matrix header", r'id="matrix-header"'),
        ("matrix body", r'id="matrix-body"'),
        ("clear matrix selection control", r'id="clear-matrix"'),
        ("matrix status region", r'id="matrix-status"'),
        ("single reusable tooltip", r'id="tooltip"'),
        ("design description block", r'class="lab8-design"'),
        ("method summary present", r'class="lab8-method"'),
        ("limitations present", r'lab8-limitations'),
        ("UMAP interpretation note", r"axes have no standalone meaning"),
        ("back link to main page", r'href="\.\./index\.html"'),
    ]
    for label, pattern in required:
        check(re.search(pattern, html) is not None, label)

    answers = re.findall(r'<article class="lab8-answer">\s*<h3>(.*?)</h3>', html, re.S)
    check(len(answers) >= 4, f"at least four findings answers (found {len(answers)})")

    # exactly one tooltip element
    check(html.count('id="tooltip"') == 1, "exactly one tooltip element")

    # design description word count 200-300
    design = re.search(r'<div class="lab8-design">(.*?)</div>', html, re.S)
    if check(design is not None, "design description block found"):
        words = re.sub(r"<[^>]+>", " ", design.group(1))
        words = re.sub(r"&[a-z]+;", " ", words)
        n = len(words.split())
        check(200 <= n <= 300, f"design description is 200-300 words (found {n})")

    return html


def check_js_safe_dom():
    section("JAVASCRIPT / SAFE DOM & D3 SEMANTICS")
    if not check(JS_PATH.is_file(), "lab8/lab8.js exists"):
        return
    js = JS_PATH.read_text(encoding="utf-8")

    # scan executable code only: strip block and line comments so that mentions
    # of forbidden APIs inside explanatory comments do not trip the check
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)

    check(".innerHTML" not in code, "innerHTML is never used")
    check("insertAdjacentHTML" not in code, "insertAdjacentHTML is never used")
    check("document.write" not in code, "document.write is never used")
    check(".html(" not in code, "D3 .html() is never used for content")
    check("textContent" in js and "replaceChildren" in js,
          "data-derived text uses safe DOM (textContent / replaceChildren)")

    semantics = [
        ("UMAP x -> position", r'"cx",\s*\(d\)\s*=>\s*xScale\(d\.x\)'),
        ("UMAP y -> position", r'"cy",\s*\(d\)\s*=>\s*yScale\(d\.y\)'),
        ("topic -> colour", r'color\(d\.cluster\)'),
        ("word_count -> size (sqrt scale)", r'scaleSqrt\('),
        ("size uses word_count", r'sizeScale\(d\.word_count\)'),
        ("d3.zoom used", r'd3\.zoom\('),
        ("matrix count -> intensity", r'scaleSequential\(d3\.interpolateBlues\)'),
        ("nearest neighbours in original space (from data)", r'neighborsData\['),
        ("matrix click sets a matrix selection", r'state\.matrixSel\s*='),
        ("selected point highlights its matrix cell", r'is-point'),
        ("map click coordination -> matrix highlight", r'updateMatrixHighlight'),
    ]
    for label, pattern in semantics:
        check(re.search(pattern, js) is not None, label)

    # single central render path
    check(len(re.findall(r"function updateVisualState\(", js)) == 1,
          "exactly one central updateVisualState() render path")
    for field in ["query", "topic", "section", "selected", "neighborIds", "matrixSel"]:
        check(re.search(rf"\b{field}\b", js) is not None, f"central state tracks '{field}'")

    # no fabricated analytical constants: findings numbers must not be hard-coded in JS
    check(not re.search(r"\b215\b|\b184\b|\b2\.550\b", js),
          "finding figures are not hard-coded in the visualization JS")


def check_css():
    section("CSS")
    if not check(CSS_PATH.is_file(), "lab8/lab8.css exists"):
        return
    css = CSS_PATH.read_text(encoding="utf-8")
    required = [
        ("responsive media queries", r"@media \(max-width:"),
        ("map layout collapses on narrow screens", r"grid-template-columns: 1fr"),
        ("matrix uses a scrollable container", r"\.lab8-matrix-scroll[\s\S]{0,120}overflow: auto"),
        ("section chart scrolls", r"\.lab8-scroll-chart[\s\S]{0,120}overflow-y: auto"),
        ("tooltip styles", r"\.lab8-tooltip\b"),
        ("neighbour ring treatment (not colour only)", r"\.lab8-point\.is-neighbor"),
        ("selected point treatment", r"\.lab8-point\.is-selected"),
        ("focus-visible outlines", r":focus-visible"),
        ("reduced-motion rule", r"@media \(prefers-reduced-motion: reduce\)"),
        ("explicit light background", r"background: #ffffff"),
    ]
    for label, pattern in required:
        check(re.search(pattern, css) is not None, label)


# --------------------------------------------------------------------------- #
# findings evidence recomputed from committed data                            #
# --------------------------------------------------------------------------- #


def check_findings(map_df, matrix_df_none, neighbors, html):
    section("FINDINGS EVIDENCE (recomputed from committed data)")
    if map_df is None or not html:
        check(False, "map data and HTML available for findings checks")
        return
    matrix = pd.read_csv(MATRIX_CSV)
    total = len(map_df)

    # ---- finding 1: topic sizes
    sizes = map_df["cluster_name"].value_counts()
    expected_sizes = {
        "Sciences, Mathematics & Computing": 215,
        "Grading, Registration & Academic Standing": 210,
        "Culture, Literature & Society": 202,
        "Politics, Policy & Economics": 181,
        "Language & Writing Courses": 95,
    }
    for name, n in expected_sizes.items():
        check(int(sizes.get(name, -1)) == n, f"topic '{name[:34]}' has {n} passages")
        pct = round(100 * n / total, 1)
        check(f"{pct}%" in html, f"HTML quotes {pct}% for that topic")

    # ---- finding 2: topic spread across sections
    spread = map_df.groupby("cluster_name")["section"].nunique()
    expected_spread = {
        "Student Development, Advising & Signature Work": 61,
        "Grading, Registration & Academic Standing": 57,
        "Credit, Transfer & Degree Policy": 52,
        "Media, Arts & Communication": 22,
        "Language & Writing Courses": 24,
    }
    for name, n in expected_spread.items():
        check(int(spread.get(name, -1)) == n, f"topic '{name[:30]}' spans {n} sections")
        check(str(n) in html, f"HTML quotes section-spread {n}")

    # ---- finding 3: section diversity (entropy)
    diversity = {}
    for sec, grp in matrix.groupby("section"):
        diversity[sec] = (int(grp["count"].sum()),
                          int((grp["count"] > 0).sum()),
                          round(entropy_of(grp["count"].values), 3))
    for sec, passages, ntopics, ent in [
        ("Computation and Design", 27, 7, 2.550),
        ("Degree Requirements", 40, 7, 2.440),
        ("History (HIST)", 60, 6, 1.878),
        ("Chinese (CHINESE)", 37, 1, 0.000),
    ]:
        got = diversity.get(sec)
        check(got == (passages, ntopics, ent),
              f"section '{sec}' diversity = {passages} passages / {ntopics} topics / entropy {ent:.3f} (got {got})")
        check(f"{ent:.3f}" in html, f"HTML quotes entropy {ent:.3f}")

    # ---- finding 4: cross-section similar passages (cross-listed courses)
    meta = map_df.set_index("passage_id")["section"].to_dict()
    for a, b in [("p0769", "p0962"), ("p0572", "p0700")]:
        hit = [e for e in neighbors.get(a, []) if e["passage_id"] == b]
        ok = bool(hit) and hit[0]["similarity"] >= 0.999 and meta.get(a) != meta.get(b)
        check(ok, f"{a} and {b} are near-identical neighbours from different sections")
        check(a in html and b in html, f"HTML cites {a} and {b}")

    # ---- finding 5: search concept distribution
    def term_dist(term):
        hits = map_df[map_df["text"].str.contains(re.escape(term), case=False)]
        return len(hits), Counter(hits["cluster_name"])

    credit_n, credit_dist = term_dist("credit")
    check(credit_n == 184, f"'credit' appears in 184 passages (got {credit_n})")
    check(len(credit_dist) == 9, f"'credit' spans 9 topics (got {len(credit_dist)})")
    check(credit_dist["Grading, Registration & Academic Standing"] == 77,
          "'credit' concentrates 77 in Grading/Registration")
    check(credit_dist["Credit, Transfer & Degree Policy"] == 54,
          "'credit' has 54 in Credit/Transfer")
    grad_n, grad_dist = term_dist("graduation")
    check(grad_n == 34, f"'graduation' appears in 34 passages (got {grad_n})")
    check(len(grad_dist) == 3, f"'graduation' spans 3 topics (got {len(grad_dist)})")

    for value in ["184", "77", "54", "34", "71%", "9 of the 10"]:
        check(value in html, f"HTML quotes '{value}'")


def main():
    corpus = check_corpus()
    check_summary(corpus)
    map_df = check_map(corpus)
    check_matrix(map_df)
    neighbors = check_neighbors(map_df)
    html = check_html()
    check_js_safe_dom()
    check_css()
    check_findings(map_df, None, neighbors, html)

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        for message in failures:
            print(f"  - {message}")
        sys.exit(1)
    print("Lab 8 validation passed with zero failures.")


if __name__ == "__main__":
    main()
