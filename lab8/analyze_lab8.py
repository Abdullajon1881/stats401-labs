"""Audit the Lab 8 semantic topics and compute the evidence behind the written
findings on lab8/index.html.

Run from the repository root:

    python lab8/analyze_lab8.py

This helper is not used by the webpage. It reads the committed derived data
(the passage corpus, embedding map, nearest-neighbour and matrix artifacts) and
prints:

  * per-topic audit: size, top TF-IDF terms, representative passages, and the
    formal sections each topic draws from (used to write CLUSTER_LABELS);
  * findings evidence: topic spread across sections, section semantic diversity
    (topic entropy), cross-section semantically similar passages, and the topic
    distribution of the search concepts credit / graduation / registration /
    academic integrity.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PASSAGES_CSV = DATA_DIR / "lab8_bulletin_passages.csv"
MAP_CSV = DATA_DIR / "lab8_embedding_map.csv"
MATRIX_CSV = DATA_DIR / "lab8_topic_section_matrix.csv"
NEIGHBORS_JSON = DATA_DIR / "lab8_neighbors.json"

SEARCH_TERMS = ["credit", "graduation", "registration", "academic integrity"]


def load():
    passages = pd.read_csv(PASSAGES_CSV, dtype={"printed_page": str}).fillna({"subsection": "", "printed_page": ""})
    mapping = pd.read_csv(MAP_CSV).fillna({"subsection": ""})
    df = mapping.merge(passages[["passage_id", "text_clean"]], on="passage_id", how="left")
    return df


def section(title):
    print("\n" + title)
    print("=" * len(title))


# --------------------------------------------------------------------------- #
# topic audit                                                                 #
# --------------------------------------------------------------------------- #


def audit_topics(df):
    section("TOPIC AUDIT")
    vectorizer = TfidfVectorizer(
        stop_words="english", ngram_range=(1, 2), min_df=5, max_df=0.5,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
    )
    matrix = vectorizer.fit_transform(df["text_clean"].tolist())
    terms = np.array(vectorizer.get_feature_names_out())

    for cluster in sorted(df["cluster"].unique()):
        idx = np.where(df["cluster"].values == cluster)[0]
        name = df.iloc[idx[0]]["cluster_name"]
        sub = matrix[idx]
        mean = np.asarray(sub.mean(axis=0)).ravel()
        top = terms[np.argsort(mean)[::-1][:12]]

        # representative passages: highest total characteristic-term weight
        row_scores = np.asarray(sub.sum(axis=1)).ravel()
        rep = idx[np.argsort(row_scores)[::-1][:4]]

        sect_counts = Counter(df.iloc[idx]["section"])
        chap_counts = Counter(df.iloc[idx]["chapter"])

        print(f"\n--- cluster {cluster}: {name}  (size {len(idx)}) ---")
        print("  top terms :", ", ".join(top))
        print("  chapters  :", ", ".join(f"{c[:34]}({n})" for c, n in chap_counts.most_common(4)))
        print("  sections  :", ", ".join(f"{s[:26]}({n})" for s, n in sect_counts.most_common(6)))
        for r in rep:
            row = df.iloc[r]
            print(f"    [{row['passage_id']} | {row['section'][:22]} | p{row['page']}] "
                  f"{row['text'][:120]}")


# --------------------------------------------------------------------------- #
# findings evidence                                                           #
# --------------------------------------------------------------------------- #


def finding_topic_sizes(df):
    section("FINDING: topic sizes")
    sizes = df.groupby(["cluster", "cluster_name"]).size().sort_values(ascending=False)
    total = len(df)
    for (cluster, name), n in sizes.items():
        print(f"  {n:>4} ({100*n/total:4.1f}%)  topic {cluster}: {name}")


def finding_topics_across_sections(df):
    section("FINDING: how many formal sections each topic spans")
    for cluster in sorted(df["cluster"].unique()):
        sub = df[df["cluster"] == cluster]
        name = sub.iloc[0]["cluster_name"]
        n_sections = sub["section"].nunique()
        top = Counter(sub["section"]).most_common(3)
        print(f"  topic {cluster} {name[:34]:34} spans {n_sections:>3} sections; "
              f"top: {', '.join(f'{s[:20]}({c})' for s, c in top)}")


def finding_section_diversity(matrix_df):
    section("FINDING: section semantic diversity (topic entropy)")
    rows = []
    for sec, grp in matrix_df.groupby("section"):
        total = int(grp["count"].sum())
        if total == 0:
            continue
        n_topics = int((grp["count"] > 0).sum())
        probs = grp["count"].values / total
        probs = probs[probs > 0]
        entropy = float(-(probs * np.log2(probs)).sum())
        rows.append((sec, total, n_topics, entropy))
    diverse = pd.DataFrame(rows, columns=["section", "passages", "n_topics", "entropy"])
    # only sections with enough passages to be meaningfully "diverse"
    meaningful = diverse[diverse["passages"] >= 15].sort_values(
        ["entropy", "n_topics"], ascending=False)
    print("  most diverse (>=15 passages), by topic entropy:")
    for _, r in meaningful.head(8).iterrows():
        print(f"    {r['section'][:34]:34} passages={int(r['passages']):>3} "
              f"topics={int(r['n_topics']):>2} entropy={r['entropy']:.3f}")
    print("  least diverse (>=15 passages):")
    for _, r in meaningful.tail(5).iterrows():
        print(f"    {r['section'][:34]:34} passages={int(r['passages']):>3} "
              f"topics={int(r['n_topics']):>2} entropy={r['entropy']:.3f}")


def finding_cross_section_similarity(df, neighbors):
    section("FINDING: most similar passages from DIFFERENT formal sections")
    meta = df.set_index("passage_id")[["section", "chapter", "page", "cluster_name", "text"]].to_dict("index")
    pairs = []
    seen = set()
    for pid, neigh in neighbors.items():
        if pid not in meta:
            continue
        for entry in neigh:
            nid = entry["passage_id"]
            if nid not in meta:
                continue
            if meta[pid]["section"] == meta[nid]["section"]:
                continue
            key = tuple(sorted((pid, nid)))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((entry["similarity"], pid, nid))
    pairs.sort(reverse=True)
    print("  highest cross-section similarity (includes cross-listed courses):")
    for sim, a, b in pairs[:6]:
        print(f"  sim={sim:.3f}  {a} [{meta[a]['section'][:22]}] <-> {b} [{meta[b]['section'][:22]}]")
        print(f"           A: {meta[a]['text'][:95]}")
        print(f"           B: {meta[b]['text'][:95]}")

    def word_jaccard(x, y):
        sx, sy = set(x.lower().split()), set(y.lower().split())
        return len(sx & sy) / len(sx | sy) if (sx | sy) else 0.0

    print("\n  highest cross-section similarity between DISTINCT passages (word Jaccard < 0.6):")
    shown = 0
    for sim, a, b in pairs:
        if word_jaccard(meta[a]["text"], meta[b]["text"]) >= 0.6:
            continue
        print(f"  sim={sim:.3f}  {a} [{meta[a]['section'][:22]}|p{meta[a]['page']}] "
              f"<-> {b} [{meta[b]['section'][:22]}|p{meta[b]['page']}]")
        print(f"           A: {meta[a]['text'][:110]}")
        print(f"           B: {meta[b]['text'][:110]}")
        shown += 1
        if shown == 6:
            break
    return pairs


def finding_search_terms(df):
    section("FINDING: search-concept topic distribution")
    for term in SEARCH_TERMS:
        pattern = re.compile(re.escape(term), re.I)
        hits = df[df["text"].str.contains(pattern)]
        dist = Counter(hits["cluster_name"])
        n_topics = len(dist)
        print(f"\n  '{term}': {len(hits)} passages across {n_topics} topics")
        for name, n in dist.most_common():
            print(f"      {n:>4}  {name}")


def main():
    df = load()
    matrix_df = pd.read_csv(MATRIX_CSV)
    neighbors = json.loads(NEIGHBORS_JSON.read_text(encoding="utf-8"))

    print(f"passages={len(df)}  sections={df['section'].nunique()}  "
          f"topics={df['cluster'].nunique()}  chapters={df['chapter'].nunique()}")

    audit_topics(df)
    finding_topic_sizes(df)
    finding_topics_across_sections(df)
    finding_section_diversity(matrix_df)
    finding_cross_section_similarity(df, neighbors)
    finding_search_terms(df)


if __name__ == "__main__":
    main()
