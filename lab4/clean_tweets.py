"""Lab 4: clean disaster-tweet data and estimate sentiment with RoBERTa.

Source dataset: "Disaster Tweets" by Viktor Stepanenko (vstepanenko/disaster-tweets)
  https://www.kaggle.com/datasets/vstepanenko/disaster-tweets
  Licence: CC0 (Public Domain). 11,370 tweets collected 14 Jan 2020.
  Columns: id, keyword, location, text, target (1 = real disaster, 0 = not).

data/lab4_raw_tweets.csv is a deterministic 1,500-row random sample of that
source (random_state=401), keeping only id, keyword, text and target. The
location column is deliberately left out: the assignment question does not
need it and it is the only roughly personal field in the source.

Reads : data/lab4_raw_tweets.csv
Writes: data/lab4_clean_tweets.csv
        data/lab4_sentiment_by_disaster.csv

Sentiment is estimated by cardiffnlp/twitter-roberta-base-sentiment-latest.
These are model estimates, not ground-truth labels.
"""

from pathlib import Path
from urllib.parse import unquote
import re
import sys
import time

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_PATH = DATA_DIR / "lab4_raw_tweets.csv"
CLEAN_PATH = DATA_DIR / "lab4_clean_tweets.csv"
AGGREGATE_PATH = DATA_DIR / "lab4_sentiment_by_disaster.csv"

KAGGLE_DATASET = "vstepanenko/disaster-tweets"
SAMPLE_SIZE = 1500
RANDOM_STATE = 401
MIN_CLEAN_ROWS = 1000

MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"
BATCH_SIZE = 16

DISASTER_LABELS = {1: "Disaster-related", 0: "Non-disaster"}
SENTIMENTS = ["Negative", "Neutral", "Positive"]

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
MENTION_PATTERN = re.compile(r"@\w+")
WHITESPACE_PATTERN = re.compile(r"\s+")


def build_raw_sample():
    """Rebuild the raw sample from Kaggle if it is missing."""
    import kagglehub

    print(f"Raw sample not found; downloading {KAGGLE_DATASET} from Kaggle")
    folder = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    source = pd.read_csv(folder / "tweets.csv", encoding="utf-8-sig")
    print(f"Source dataset: {len(source)} rows, columns {list(source.columns)}")

    sample = source[["id", "keyword", "text", "target"]].sample(
        n=SAMPLE_SIZE, random_state=RANDOM_STATE
    )
    sample = sample.sort_values("id").reset_index(drop=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sample.to_csv(RAW_PATH, index=False, encoding="utf-8")
    print(f"Wrote {len(sample)} sampled rows to {RAW_PATH}")


def preprocess_for_tfidf(text):
    """Heavier normalisation for the bag-of-words style field."""
    lowered = text.lower()
    lowered = URL_PATTERN.sub(" url ", lowered)
    lowered = MENTION_PATTERN.sub(" user ", lowered)
    return WHITESPACE_PATTERN.sub(" ", lowered).strip()


def preprocess_for_roberta(text):
    """Light normalisation the Cardiff model expects: keep punctuation and emoji."""
    normalised = MENTION_PATTERN.sub("@user", text)
    normalised = URL_PATTERN.sub("http", normalised)
    return WHITESPACE_PATTERN.sub(" ", normalised).strip()


def inspect_quality(frame):
    """Report the data-quality problems that actually exist in the raw sample."""
    text = frame["text"].astype(str)
    keyword = frame["keyword"].astype(str)

    print("\n--- data quality before cleaning ---")
    print(f"shape: {frame.shape}")
    print(f"columns: {list(frame.columns)}")
    print("dtypes:")
    for name, dtype in frame.dtypes.items():
        print(f"  {name}: {dtype}")
    print("missing values per column:")
    for name, count in frame.isna().sum().items():
        print(f"  {name}: {count}")

    whitespace_issues = int((text != text.str.strip()).sum()) + int(
        text.str.contains(r"\s{2,}", regex=True).sum()
    )
    checks = {
        "full-row duplicates": int(frame.duplicated().sum()),
        "duplicate tweet ids": int(frame["id"].duplicated().sum()),
        "duplicate tweet text": int(text.duplicated().sum()),
        "blank or whitespace-only text": int(text.str.strip().eq("").sum()),
        "text needing whitespace tidy": whitespace_issues,
        "keywords with percent-encoding": int(keyword.str.contains("%", regex=False).sum()),
        "keywords needing whitespace tidy": int((keyword != keyword.str.strip()).sum()),
        "tweets containing a URL": int(text.str.contains("http", regex=False).sum()),
        "tweets containing an @mention": int(text.str.contains(r"@\w", regex=True).sum()),
    }
    for label, count in checks.items():
        print(f"  {label}: {count}")

    invalid_target = frame.loc[~frame["target"].isin(DISASTER_LABELS)]
    print(f"  rows with a target outside {sorted(DISASTER_LABELS)}: {len(invalid_target)}")
    return checks


def clean_dataframe(frame):
    """Apply the cleaning steps for problems this dataset really has."""
    before = len(frame)
    cleaned = frame.copy()

    # keep ids as integers rather than letting them become floats
    cleaned["tweet_id"] = cleaned["id"].astype("int64")

    # keyword: the source stores multi-word keywords percent-encoded, e.g. airplane%20accident
    cleaned["keyword"] = cleaned["keyword"].fillna("").astype(str).map(unquote).str.strip()
    cleaned["keyword"] = cleaned["keyword"].map(lambda s: WHITESPACE_PATTERN.sub(" ", s))

    # keep the tweet as published, only trimming surrounding whitespace
    cleaned["tweet_text_raw"] = cleaned["text"].astype(str).str.strip()

    # drop tweets with no usable text
    cleaned = cleaned.loc[cleaned["tweet_text_raw"] != ""]
    dropped_blank = before - len(cleaned)

    # drop repeated tweet ids, then identical tweet text
    before_ids = len(cleaned)
    cleaned = cleaned.drop_duplicates(subset="tweet_id", keep="first")
    dropped_ids = before_ids - len(cleaned)

    before_text = len(cleaned)
    cleaned = cleaned.drop_duplicates(subset="tweet_text_raw", keep="first")
    dropped_text = before_text - len(cleaned)

    # target must be 0 or 1; anything else is not silently reinterpreted
    invalid = cleaned.loc[~cleaned["target"].isin(DISASTER_LABELS)]
    if len(invalid):
        raise SystemExit(f"Unexpected target values: {sorted(invalid['target'].unique())}")
    cleaned["disaster_class"] = cleaned["target"].map(DISASTER_LABELS)

    cleaned["text_clean"] = cleaned["tweet_text_raw"].map(preprocess_for_tfidf)
    cleaned["sentiment_text"] = cleaned["tweet_text_raw"].map(preprocess_for_roberta)

    print("\n--- cleaning actions ---")
    print(f"  rows in: {before}")
    print(f"  dropped for blank text: {dropped_blank}")
    print(f"  dropped duplicate ids: {dropped_ids}")
    print(f"  dropped duplicate tweet text: {dropped_text}")
    print(f"  rows out: {len(cleaned)}")

    return cleaned.reset_index(drop=True)


def tfidf_sanity_check(texts):
    """Optional check that the cleaned-text path produces a sensible vocabulary."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        print("\nscikit-learn not installed; skipping TF-IDF sanity check")
        return

    import numpy as np

    vectorizer = TfidfVectorizer(min_df=5, max_df=0.8, stop_words="english")
    matrix = vectorizer.fit_transform(texts)
    scores = np.asarray(matrix.sum(axis=0)).ravel()
    names = vectorizer.get_feature_names_out()
    top = sorted(zip(names, scores), key=lambda pair: pair[1], reverse=True)[:10]

    print("\n--- TF-IDF sanity check on text_clean ---")
    print(f"  matrix shape: {matrix.shape}")
    print(f"  vocabulary size: {len(names)}")
    print("  top terms: " + ", ".join(name for name, _ in top))


def run_sentiment(texts):
    """Score every tweet with the required CardiffNLP RoBERTa model."""
    import torch
    import transformers
    from transformers import pipeline

    print("\n--- sentiment model ---")
    print(f"  transformers: {transformers.__version__}")
    print(f"  torch: {torch.__version__}")
    print(f"  model: {MODEL_NAME}")

    classifier = pipeline(
        "sentiment-analysis",
        model=MODEL_NAME,
        top_k=None,
        batch_size=BATCH_SIZE,
    )
    print(f"  device: {classifier.device}")

    probe = classifier(texts[:3], truncation=True)
    print(f"  labels returned: {sorted({item['label'] for row in probe for item in row})}")

    start = time.time()
    raw_scores = classifier(list(texts), truncation=True)
    elapsed = time.time() - start
    print(f"  scored {len(raw_scores)} tweets in {elapsed:.1f}s (batch size {BATCH_SIZE})")

    rows = []
    for entry in raw_scores:
        scores = {item["label"].lower(): float(item["score"]) for item in entry}
        rows.append(
            {
                "sentiment_negative": scores["negative"],
                "sentiment_neutral": scores["neutral"],
                "sentiment_positive": scores["positive"],
            }
        )

    frame = pd.DataFrame(rows)
    frame["sentiment_score"] = frame["sentiment_positive"] - frame["sentiment_negative"]
    frame["sentiment"] = (
        frame[["sentiment_negative", "sentiment_neutral", "sentiment_positive"]]
        .idxmax(axis=1)
        .str.replace("sentiment_", "", regex=False)
        .str.capitalize()
    )
    return frame, elapsed


def validate_sentiment(frame):
    """Fail loudly if any model output looks wrong."""
    probs = frame[["sentiment_negative", "sentiment_neutral", "sentiment_positive"]]

    problems = []
    if probs.isna().any().any():
        problems.append("non-finite probability")
    if not ((probs >= 0) & (probs <= 1)).all().all():
        problems.append("probability outside 0-1")
    if not (probs.sum(axis=1) - 1).abs().lt(1e-4).all():
        problems.append("probabilities do not sum to 1")
    if not frame["sentiment"].isin(SENTIMENTS).all():
        problems.append("unexpected sentiment label")
    if not frame["sentiment_score"].between(-1, 1).all():
        problems.append("sentiment_score outside -1..1")

    if problems:
        raise SystemExit("Sentiment validation failed: " + "; ".join(problems))
    print("  validation: probabilities finite, in range, sum to 1; labels and scores valid")


def build_aggregate(frame):
    """Counts and within-class proportions for the D3 chart."""
    counts = frame.groupby(["disaster_class", "sentiment"]).size().rename("count").reset_index()
    full_index = pd.MultiIndex.from_product(
        [sorted(DISASTER_LABELS.values()), SENTIMENTS],
        names=["disaster_class", "sentiment"],
    )
    counts = (
        counts.set_index(["disaster_class", "sentiment"])
        .reindex(full_index, fill_value=0)
        .reset_index()
    )
    totals = counts.groupby("disaster_class")["count"].transform("sum")
    counts["proportion"] = (counts["count"] / totals).round(6)
    return counts


def main():
    if not RAW_PATH.exists():
        build_raw_sample()

    raw = pd.read_csv(RAW_PATH, encoding="utf-8")
    print(f"Loaded {len(raw)} raw sampled tweets from {RAW_PATH}")
    inspect_quality(raw)

    cleaned = clean_dataframe(raw)
    if len(cleaned) < MIN_CLEAN_ROWS:
        raise SystemExit(f"Only {len(cleaned)} rows survived cleaning, need {MIN_CLEAN_ROWS}")

    tfidf_sanity_check(cleaned["text_clean"])

    sentiment, _ = run_sentiment(cleaned["sentiment_text"].tolist())
    validate_sentiment(sentiment)

    cleaned = pd.concat([cleaned.reset_index(drop=True), sentiment], axis=1)

    columns = [
        "tweet_id",
        "keyword",
        "tweet_text_raw",
        "text_clean",
        "disaster_class",
        "sentiment_negative",
        "sentiment_neutral",
        "sentiment_positive",
        "sentiment_score",
        "sentiment",
    ]
    cleaned[columns].to_csv(CLEAN_PATH, index=False, encoding="utf-8")
    print(f"\nWrote {len(cleaned)} cleaned tweets to {CLEAN_PATH}")

    aggregate = build_aggregate(cleaned)
    aggregate.to_csv(AGGREGATE_PATH, index=False, encoding="utf-8")
    print(f"Wrote {len(aggregate)} aggregate rows to {AGGREGATE_PATH}")

    print("\n--- sentiment by disaster class ---")
    for label in sorted(DISASTER_LABELS.values()):
        part = aggregate.loc[aggregate["disaster_class"] == label]
        total = int(part["count"].sum())
        shares = ", ".join(
            f"{record['sentiment']} {record['count']} ({record['proportion']:.1%})"
            for record in part.to_dict("records")
        )
        print(f"  {label} (n={total}): {shares}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
