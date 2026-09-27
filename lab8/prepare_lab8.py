"""Build the Lab 8 semantic corpus and all derived data from the official
Duke Kunshan University Undergraduate Bulletin (2021-2022).

Pipeline (source -> committed data):

    official 400-page bulletin PDF
        -> PyMuPDF text + layout extraction (text-layer, no OCR)
        -> TOC-anchored document hierarchy (chapter / section / subsection)
        -> meaningful paragraph / policy / course passages
        -> cleaned corpus                      data/lab8_bulletin_passages.csv
        -> corpus summaries                    data/lab8_corpus_summary.json
                                               data/lab8_section_summary.csv
                                               data/lab8_top_terms.csv
        -> sentence embeddings (all-MiniLM-L6-v2, normalized)
        -> UMAP 2D projection (cosine, seed 401)
        -> KMeans topics on the ORIGINAL embeddings (seed 401)
        -> human topic labels (CLUSTER_LABELS below)
        -> semantic map                        data/lab8_embedding_map.csv
        -> nearest neighbours (cosine, top 5)  data/lab8_neighbors.json
        -> topic x section matrix              data/lab8_topic_section_matrix.csv

Run from the repository root:

    python lab8/prepare_lab8.py

The script is deterministic and idempotent: re-running it reproduces byte-stable
committed artifacts. It fails loudly rather than silently degrading (for example
it never falls back from sentence embeddings to a TF-IDF stand-in).

The 400-page PDF and the sentence-transformer weights are NOT committed. The PDF
is read from (in order): the LAB8_PDF environment variable, a local cache under
the system temp directory, or a fresh download from the official URL into that
cache. Model weights download to the local Hugging Face cache.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import tempfile
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------------- #
# configuration                                                               #
# --------------------------------------------------------------------------- #

LAB_DIR = Path(__file__).resolve().parent
ROOT = LAB_DIR.parent
DATA_DIR = ROOT / "data"

BULLETIN_TITLE = "Bulletin of Duke Kunshan University: Undergraduate Instruction"
BULLETIN_VERSION = "2021-2022 (July 2021)"
BULLETIN_SOURCE = (
    "https://dku-web-admissions.s3.cn-north-1.amazonaws.com.cn/"
    "dkumain/files/V2021-22_DKU_UG_Bulletin.pdf"
)
ACCESSED_DATE = "2026-09-27"

# hierarchy
CONTENT_START_PAGE = 10  # 1-based PDF page of "Part 1: General Information"
# the two Part 10 level-2 headings are >100-page containers; the meaningful
# section for their passages is the level-3 heading (the major or the course
# subject), not the entire container.
PART10_CONTAINERS = {
    "Majors (listed in alphabetical order)",
    "Course Descriptions",
}

# passage sizing
MIN_WORDS = 18       # merge target: passages below this absorb adjacent fragments
ABSORB_WORDS = 10    # tiny trailing/leading fragments (prereqs, stubs) get absorbed
MAX_WORDS = 140      # passages above this are split at sentence boundaries
DROP_BELOW_WORDS = 5  # final drop threshold for uninterpretable stubs

# semantic model
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# reproducibility
RANDOM_STATE = 401

# UMAP
UMAP_N_COMPONENTS = 2
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.15
UMAP_METRIC = "cosine"

# clustering
CLUSTER_N_INIT = 20
FINAL_K = 10  # chosen from the k = 8..12 silhouette / interpretability scan

# nearest neighbours
N_NEIGHBORS_EXPORT = 5

# TF-IDF
TFIDF_MIN_DF = 5
TFIDF_MAX_DF = 0.4
TFIDF_TOP_TERMS = 25
# generic academic boilerplate suppressed from the displayed corpus term chart so
# it surfaces characteristic content terms rather than ubiquitous filler words.
TFIDF_DOMAIN_STOPWORDS = [
    "student", "students", "course", "courses", "prerequisite", "prerequisites",
    "university", "class", "classes", "study", "studies", "including", "include",
]

# Human topic labels for the FINAL_K deterministic clusters (KMeans seed 401).
# Filled after inspecting representative passages and TF-IDF terms with
# lab8/analyze_lab8.py. Every cluster id 0..FINAL_K-1 must have exactly one label.
CLUSTER_LABELS: dict[int, str] = {
    0: "Student Development, Advising & Skills",
    1: "China & Global History",
    2: "Language & Writing Courses",
    3: "Transfer Credit & Global Education",
    4: "Grading, Registration & Academic Standing",
    5: "Culture, Literature & the Arts",
    6: "Mathematics, Physical Science & Computing",
    7: "Placement Credit & Degree Requirements",
    8: "Biology, Environment & Global Health",
    9: "Politics, Policy & Economics",
}


# --------------------------------------------------------------------------- #
# text normalisation                                                          #
# --------------------------------------------------------------------------- #

_PUNCT_MAP = {
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ", "�": "'",
}


def _apply_punct(text: str) -> str:
    for src, dst in _PUNCT_MAP.items():
        text = text.replace(src, dst)
    return text


def norm_title(text: str) -> str:
    """Normalise a heading for matching against TOC titles."""
    text = unicodedata.normalize("NFKC", text)
    text = _apply_punct(text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(text: str) -> str:
    """Clean an extracted block into natural language for embedding."""
    text = unicodedata.normalize("NFKC", text)    # decompose ligatures (fi, fl, ...)
    text = _apply_punct(text)
    text = re.sub(r"[-]", "", text)   # private-use glyphs (wingdings)
    text = re.sub(r"-\s*\n\s*", "", text)         # de-hyphenate line wraps
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def join_spans(spans) -> str:
    """Join a text line's spans, inserting a space only where the glyph geometry
    shows a real horizontal gap. PyMuPDF emits word-level spans, but a superscript
    footnote marker or a font change can split a single word into adjacent spans
    (e.g. "s" + "tudents"); a blind space join turns that into "s tudents". Using
    the span bounding boxes repairs those intra-word splits deterministically while
    preserving ordinary inter-word spacing."""
    parts = []
    prev_x1 = None
    prev_size = 11.0
    for span in spans:
        text = span["text"]
        if not text:
            continue
        x0, x1 = span["bbox"][0], span["bbox"][2]
        if parts and prev_x1 is not None:
            gap = x0 - prev_x1
            ends_space = parts[-1].endswith(" ") or parts[-1].endswith("\t")
            starts_space = text[:1].isspace()
            if gap > 0.25 * prev_size and not ends_space and not starts_space:
                parts.append(" ")
        parts.append(text)
        prev_x1 = x1
        prev_size = span["size"] or prev_size
    return "".join(parts)


def part_short(chapter: str) -> str:
    return re.sub(r"^Part\s+\d+:\s*", "", chapter).strip()


# structural course-group headings inside Part 10 (e.g. "Disciplinary Courses",
# "Chinese as Second Language Courses") are layout labels, not document units.
_GROUP_WORDS = {
    "courses", "course", "electives", "elective", "requirements", "requirement",
    "sequence", "track", "tracks", "concentration", "concentrations",
}


def is_structure_heading(text: str, chapter: str) -> bool:
    """A short Part-10 course-group heading with no sentence content: title-like,
    no course code, no digits, no sentence punctuation, ends on a group word."""
    if not chapter.startswith("Part 10"):
        return False
    words = text.split()
    if not (1 <= len(words) <= 8):
        return False
    if re.search(r"[.!?:;,()]", text):
        return False
    if any(ch.isdigit() for ch in text):
        return False
    if re.search(r"\b[A-Z]{2,}\s*\d", text):  # course code such as MATH 405
        return False
    if words[-1].lower() not in _GROUP_WORDS:
        return False
    return text[:1].isupper()


def ends_open(text: str) -> bool:
    """True when a passage does not end on a sentence-terminal boundary."""
    return re.search(r"[.!?]['\")\]]?\s*$", text) is None


def begins_lowercase(text: str) -> bool:
    match = re.search(r"[A-Za-z]", text)
    return bool(match) and match.group().islower()


def looks_like_page_continuation(prev, cur) -> bool:
    """Strong, geometry-backed evidence that `cur` continues `prev`'s paragraph
    across a page break: same hierarchy, consecutive PDF pages, the previous block
    sits low on its page, the current block starts high on the next page, the
    previous text is syntactically unfinished, and the current text starts lower
    case. Two independent paragraphs that merely straddle a page break do not meet
    all of these conditions."""
    if not (prev["chapter"] == cur["chapter"]
            and prev["section"] == cur["section"]
            and prev["subsection"] == cur["subsection"]):
        return False
    if cur["page"] != prev["end_page"] + 1:
        return False
    if prev["end_y_bottom"] < 0.72 * prev["end_page_height"]:
        return False
    if cur["y_top"] > 0.32 * cur["page_height"]:
        return False
    return ends_open(prev["text"]) and begins_lowercase(cur["text"])


def short_section(section: str) -> str:
    """Clean the Part 10 level-3 section labels into readable names."""
    section = re.sub(r"^Courses with Course Subject:\s*", "", section)
    section = re.sub(r"\s+with [Tt]racks.*$", "", section)
    return section.strip().rstrip(",").strip()


# --------------------------------------------------------------------------- #
# PDF acquisition                                                             #
# --------------------------------------------------------------------------- #


def resolve_pdf_path() -> Path:
    """Locate the bulletin PDF without committing it to the repository."""
    env = os.environ.get("LAB8_PDF")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(Path(tempfile.gettempdir()) / "lab8_cache" / "V2021-22_DKU_UG_Bulletin.pdf")
    for path in candidates:
        if path.is_file() and path.stat().st_size > 1_000_000:
            print(f"[pdf] using cached bulletin: {path}")
            return path

    target = candidates[-1]
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"[pdf] downloading official bulletin -> {target}")
    try:
        with urllib.request.urlopen(BULLETIN_SOURCE, timeout=120) as resp:
            data = resp.read()
    except Exception as exc:  # noqa: BLE001 - fail loudly with an actionable message
        raise SystemExit(
            f"ERROR: could not download the bulletin from {BULLETIN_SOURCE}\n"
            f"       {exc}\n"
            f"       Download it manually and set LAB8_PDF to its path."
        )
    if len(data) < 1_000_000:
        raise SystemExit("ERROR: downloaded bulletin is too small; aborting.")
    target.write_bytes(data)
    print(f"[pdf] downloaded {len(data):,} bytes")
    return target


# --------------------------------------------------------------------------- #
# extraction                                                                  #
# --------------------------------------------------------------------------- #


def extract_fragments(pdf_path: Path):
    """Stream content pages and emit body fragments tagged with the hierarchy
    resolved from the embedded PDF outline (table of contents)."""
    try:
        import pymupdf
    except ImportError:
        raise SystemExit("ERROR: PyMuPDF is required. Install with: pip install pymupdf")

    doc = pymupdf.open(pdf_path)
    page_count = doc.page_count
    toc = doc.get_toc()
    if not toc:
        raise SystemExit("ERROR: the bulletin has no embedded outline; cannot build hierarchy.")

    headings = [(lvl, norm_title(title), page) for (lvl, title, page) in toc
                if page >= CONTENT_START_PAGE]

    ptr = 0
    cur = {1: None, 2: None, 3: None, 4: None}
    fragments = []
    printed_page = {}
    page_num_re = re.compile(r"^\d{1,3}$")
    table_hdr_re = re.compile(r"^Course Code\s+Course Name", re.I)

    for pno in range(CONTENT_START_PAGE - 1, page_count):
        page1 = pno + 1
        page_height = doc[pno].rect.height
        blocks = [b for b in doc[pno].get_text("dict")["blocks"] if b.get("type") == 0]
        blocks.sort(key=lambda b: (round(b["bbox"][1]), round(b["bbox"][0])))
        for block in blocks:
            line_texts = [join_spans(line["spans"]) for line in block["lines"]]
            text = clean_text(" ".join(line_texts))
            if not text:
                continue
            ntext = norm_title(text)
            y_top = block["bbox"][1]
            y_bottom = block["bbox"][3]

            # footer page number -> record printed page, drop from corpus
            if y_top > 720 and page_num_re.match(text):
                printed_page.setdefault(page1, text)
                continue

            # heading? match against upcoming TOC entries near this page
            matched = None
            for j in range(ptr, min(ptr + 40, len(headings))):
                lvl, title, page = headings[j]
                if abs(page - page1) <= 1 and (
                    ntext == title
                    or (len(title) > 6 and ntext.startswith(title))
                    or (len(ntext) > 6 and title.startswith(ntext))
                ):
                    matched = (j, lvl)
                    break
            if matched:
                j, lvl = matched
                ptr = j + 1
                cur[lvl] = headings[j][1]
                for deeper in range(lvl + 1, 5):
                    cur[deeper] = None
                continue

            if table_hdr_re.match(text):  # repeated "Course Code Course Name..." header
                continue

            chapter = cur[1] or ""
            if cur[2] in PART10_CONTAINERS:
                section = short_section(cur[3] or cur[2] or "")
                subsection = cur[4] or ""
            else:
                section = cur[2] or ""
                subsection = cur[3] or ""
            if not section:
                section = part_short(chapter)

            # structure-only course-group heading -> not a semantic passage
            if is_structure_heading(text, chapter):
                continue

            fragments.append({
                "page": page1,
                "chapter": chapter,
                "section": section,
                "subsection": subsection,
                "text": text,
                "words": len(text.split()),
                "y_top": y_top,
                "y_bottom": y_bottom,
                "page_height": page_height,
            })

    consumed = ptr
    return fragments, printed_page, page_count, len(headings), consumed


def _absorb(prev, frag):
    """Fold `frag` into `prev`, extending the page span and end geometry."""
    prev["text"] = f'{prev["text"]} {frag["text"]}'.strip()
    prev["words"] = len(prev["text"].split())
    prev["end_page"] = frag["page"]
    prev["end_y_bottom"] = frag["y_bottom"]
    prev["end_page_height"] = frag["page_height"]


def merge_fragments(fragments):
    """Merge fragments into passages. Two fragments join when either (a) the block
    geometry shows a clear cross-page paragraph continuation, or (b) one side is a
    tiny fragment (a stub or a prerequisite line) sharing the same hierarchy."""
    merged = []
    for frag in fragments:
        work = dict(frag)
        work["end_page"] = frag["page"]
        work["end_y_bottom"] = frag["y_bottom"]
        work["end_page_height"] = frag["page_height"]
        if merged:
            prev = merged[-1]
            if looks_like_page_continuation(prev, frag):
                _absorb(prev, frag)
                continue
            same = (prev["section"] == frag["section"]
                    and prev["subsection"] == frag["subsection"]
                    and abs(prev["end_page"] - frag["page"]) <= 1)
            if same and (prev["words"] < MIN_WORDS or frag["words"] < ABSORB_WORDS):
                _absorb(prev, frag)
                continue
        merged.append(work)
    return merged


def split_long(text: str):
    if len(text.split()) <= MAX_WORDS:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, buf = [], ""
    for sentence in sentences:
        candidate = f"{buf} {sentence}".strip()
        if len(candidate.split()) > MAX_WORDS and buf:
            chunks.append(buf.strip())
            buf = sentence
        else:
            buf = candidate
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def build_passages(fragments, printed_page):
    merged = merge_fragments(fragments)

    split = []
    for frag in merged:
        for piece in split_long(frag["text"]):
            row = dict(frag)
            row["text"] = piece
            row["words"] = len(piece.split())
            split.append(row)

    # drop uninterpretable stubs and non-alphabetic fragments
    kept = [f for f in split
            if f["words"] >= DROP_BELOW_WORDS and re.search(r"[A-Za-z]{3}", f["text"])]

    # drop exact duplicate cleaned text
    seen, passages = set(), []
    for frag in kept:
        key = frag["text"]
        if key in seen:
            continue
        seen.add(key)
        passages.append(frag)

    rows = []
    for idx, frag in enumerate(passages, start=1):
        text = frag["text"]
        text_clean = re.sub(r"\s+", " ", text).strip()
        rows.append({
            "passage_id": f"p{idx:04d}",
            "chapter": frag["chapter"],
            "section": frag["section"],
            "subsection": frag["subsection"],
            "page": frag["page"],
            "page_end": frag.get("end_page", frag["page"]),
            "printed_page": printed_page.get(frag["page"], ""),
            "text": text,
            "text_clean": text_clean,
            "word_count": len(text_clean.split()),
        })
    return rows, len(fragments)


# --------------------------------------------------------------------------- #
# corpus summaries                                                            #
# --------------------------------------------------------------------------- #


def write_passages_csv(rows):
    import pandas as pd

    columns = ["passage_id", "chapter", "section", "subsection", "page", "page_end",
               "printed_page", "text", "text_clean", "word_count"]
    df = pd.DataFrame(rows, columns=columns)
    out = DATA_DIR / "lab8_bulletin_passages.csv"
    df.to_csv(out, index=False, lineterminator="\n")
    print(f"[data] wrote {out.name}  ({len(df)} passages)")
    return df


def write_section_summary(df):
    import pandas as pd

    grouped = (df.groupby("section")
                 .agg(passage_count=("passage_id", "count"),
                      avg_word_count=("word_count", "mean"),
                      chapter=("chapter", "first"))
                 .reset_index()
                 .sort_values(["passage_count", "section"], ascending=[False, True]))
    grouped["avg_word_count"] = grouped["avg_word_count"].round(2)
    out = DATA_DIR / "lab8_section_summary.csv"
    grouped.to_csv(out, index=False, lineterminator="\n",
                   columns=["section", "chapter", "passage_count", "avg_word_count"])
    print(f"[data] wrote {out.name}  ({len(grouped)} sections)")


def write_top_terms(df):
    import pandas as pd
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

    stop_words = list(ENGLISH_STOP_WORDS.union(TFIDF_DOMAIN_STOPWORDS))
    vectorizer = TfidfVectorizer(
        stop_words=stop_words,
        ngram_range=(1, 2),
        min_df=TFIDF_MIN_DF,
        max_df=TFIDF_MAX_DF,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
    )
    matrix = vectorizer.fit_transform(df["text_clean"].tolist())
    terms = np.array(vectorizer.get_feature_names_out())
    scores = np.asarray(matrix.mean(axis=0)).ravel()
    order = np.argsort(scores)[::-1][:TFIDF_TOP_TERMS]
    top = pd.DataFrame({"term": terms[order], "tfidf": np.round(scores[order], 6)})
    out = DATA_DIR / "lab8_top_terms.csv"
    top.to_csv(out, index=False, lineterminator="\n")
    print(f"[data] wrote {out.name}  ({len(top)} terms)")
    return vectorizer, matrix, terms


def write_corpus_summary(df, raw_passages, pdf_pages):
    summary = {
        "bulletin_title": BULLETIN_TITLE,
        "bulletin_version": BULLETIN_VERSION,
        "source": BULLETIN_SOURCE,
        "accessed_date": ACCESSED_DATE,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimension": EMBEDDING_DIM,
        "umap": {
            "n_components": UMAP_N_COMPONENTS,
            "n_neighbors": UMAP_N_NEIGHBORS,
            "min_dist": UMAP_MIN_DIST,
            "metric": UMAP_METRIC,
            "random_state": RANDOM_STATE,
        },
        "clustering": {
            "method": "KMeans",
            "k": FINAL_K,
            "random_state": RANDOM_STATE,
            "n_init": CLUSTER_N_INIT,
        },
        "pdf_pages": pdf_pages,
        "raw_passages": raw_passages,
        "clean_passages": int(len(df)),
        "average_word_count": round(float(df["word_count"].mean()), 2),
        "formal_section_count": int(df["section"].nunique()),
    }
    out = DATA_DIR / "lab8_corpus_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"[data] wrote {out.name}")
    return summary


# --------------------------------------------------------------------------- #
# semantic pipeline                                                           #
# --------------------------------------------------------------------------- #


def build_embeddings(df):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise SystemExit(
            "ERROR: sentence-transformers is required. "
            "Install with: pip install sentence-transformers"
        )
    try:
        model = SentenceTransformer(EMBEDDING_MODEL)
    except Exception as exc:  # noqa: BLE001 - do not fall back to TF-IDF
        raise SystemExit(
            f"ERROR: could not load embedding model {EMBEDDING_MODEL!r}: {exc}\n"
            f"       A working sentence-transformer model is required; there is no fallback."
        )
    dim = model.get_sentence_embedding_dimension()
    if dim != EMBEDDING_DIM:
        raise SystemExit(f"ERROR: embedding dimension {dim} != expected {EMBEDDING_DIM}")
    print(f"[embed] encoding {len(df)} passages with {EMBEDDING_MODEL} (dim {dim})")
    embeddings = model.encode(
        df["text_clean"].tolist(),
        normalize_embeddings=True,
        batch_size=64,
        show_progress_bar=False,
    )
    return np.asarray(embeddings, dtype=np.float32)


def scan_k(embeddings):
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    print("[cluster] k scan (silhouette on original embeddings):")
    for k in range(8, 13):
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=CLUSTER_N_INIT)
        labels = km.fit_predict(embeddings)
        sizes = np.bincount(labels)
        sil = silhouette_score(embeddings, labels, metric="cosine")
        print(f"    k={k:>2}  silhouette={sil:.4f}  min_cluster={sizes.min()}  max_cluster={sizes.max()}")


def cluster(embeddings):
    from sklearn.cluster import KMeans

    km = KMeans(n_clusters=FINAL_K, random_state=RANDOM_STATE, n_init=CLUSTER_N_INIT)
    labels = km.fit_predict(embeddings)
    return labels, km


def project_umap(embeddings):
    try:
        import umap
    except ImportError:
        raise SystemExit("ERROR: umap-learn is required. Install with: pip install umap-learn")
    reducer = umap.UMAP(
        n_components=UMAP_N_COMPONENTS,
        n_neighbors=UMAP_N_NEIGHBORS,
        min_dist=UMAP_MIN_DIST,
        metric=UMAP_METRIC,
        random_state=RANDOM_STATE,
    )
    coords = reducer.fit_transform(embeddings)
    return np.asarray(coords, dtype=np.float64)


def write_embedding_map(df, labels, coords):
    import pandas as pd

    if not set(np.unique(labels)) <= set(CLUSTER_LABELS):
        missing = sorted(set(np.unique(labels)) - set(CLUSTER_LABELS))
        raise SystemExit(f"ERROR: clusters without labels: {missing}")

    out_df = df.copy()
    out_df["cluster"] = labels.astype(int)
    out_df["cluster_name"] = out_df["cluster"].map(CLUSTER_LABELS)
    out_df["x"] = np.round(coords[:, 0], 4)
    out_df["y"] = np.round(coords[:, 1], 4)
    columns = ["passage_id", "chapter", "section", "subsection", "page", "page_end",
               "text", "word_count", "cluster", "cluster_name", "x", "y"]
    out = DATA_DIR / "lab8_embedding_map.csv"
    out_df.to_csv(out, index=False, lineterminator="\n", columns=columns)
    print(f"[data] wrote {out.name}  ({len(out_df)} rows)")
    return out_df


def write_neighbors(df, embeddings):
    from sklearn.neighbors import NearestNeighbors

    n = len(df)
    k = min(N_NEIGHBORS_EXPORT + 1, n)
    nn = NearestNeighbors(n_neighbors=k, metric="cosine")
    nn.fit(embeddings)
    distances, indices = nn.kneighbors(embeddings)
    ids = df["passage_id"].tolist()

    neighbors = {}
    for i, pid in enumerate(ids):
        entry = []
        for dist, j in zip(distances[i], indices[i]):
            if j == i:
                continue
            entry.append({
                "passage_id": ids[j],
                "similarity": round(float(1.0 - dist), 6),
            })
            if len(entry) == N_NEIGHBORS_EXPORT:
                break
        entry.sort(key=lambda e: e["similarity"], reverse=True)
        neighbors[pid] = entry

    out = DATA_DIR / "lab8_neighbors.json"
    out.write_text(json.dumps(neighbors, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[data] wrote {out.name}  ({len(neighbors)} passages x {N_NEIGHBORS_EXPORT})")


def write_matrix(map_df):
    import pandas as pd

    sections = sorted(map_df["section"].unique())
    topics = [CLUSTER_LABELS[c] for c in range(FINAL_K)]
    counts = map_df.groupby(["section", "cluster_name"]).size()
    section_totals = map_df.groupby("section").size()

    records = []
    for section in sections:
        total = int(section_totals[section])
        for topic in topics:
            count = int(counts.get((section, topic), 0))
            records.append({
                "section": section,
                "topic": topic,
                "count": count,
                "section_total": total,
                "proportion": round(count / total, 6) if total else 0.0,
            })
    matrix = pd.DataFrame.from_records(records)
    out = DATA_DIR / "lab8_topic_section_matrix.csv"
    matrix.to_csv(out, index=False, lineterminator="\n")
    print(f"[data] wrote {out.name}  ({len(sections)} sections x {len(topics)} topics)")


# --------------------------------------------------------------------------- #
# main                                                                        #
# --------------------------------------------------------------------------- #


def main():
    os.environ.setdefault("PYTHONHASHSEED", "0")
    random.seed(RANDOM_STATE)
    np.random.seed(RANDOM_STATE)
    DATA_DIR.mkdir(exist_ok=True)

    pdf_path = resolve_pdf_path()

    print("[extract] parsing bulletin ...")
    fragments, printed_page, pdf_pages, heading_count, consumed = extract_fragments(pdf_path)
    print(f"[extract] {len(fragments)} body fragments; "
          f"{consumed}/{heading_count} TOC headings consumed; {pdf_pages} PDF pages")

    rows, raw_fragment_count = build_passages(fragments, printed_page)
    df = write_passages_csv(rows)

    write_section_summary(df)
    write_top_terms(df)
    summary = write_corpus_summary(df, raw_fragment_count, pdf_pages)

    embeddings = build_embeddings(df)
    scan_k(embeddings)
    labels, _ = cluster(embeddings)
    coords = project_umap(embeddings)

    map_df = write_embedding_map(df, labels, coords)
    write_neighbors(df, embeddings)
    write_matrix(map_df)

    print("\n[done] corpus + semantic artifacts rebuilt.")
    print(f"       passages={summary['clean_passages']}  "
          f"sections={summary['formal_section_count']}  "
          f"avg_words={summary['average_word_count']}  k={FINAL_K}")


if __name__ == "__main__":
    main()
