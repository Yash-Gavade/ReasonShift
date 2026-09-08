from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd
from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

LETTERS = ["A", "B", "C", "D", "E", "F"]


def gsm8k_gold(answer: str) -> str:
    """Extract the official final answer after ####."""
    if "####" not in answer:
        raise ValueError(f"Unexpected GSM8K answer format: {answer[:120]!r}")
    gold = answer.rsplit("####", 1)[1].strip()
    return gold.replace(",", "")


def choice_block(labels, texts) -> str:
    return "\n".join(f"{lab}. {txt}" for lab, txt in zip(labels, texts))


def prepare_gsm8k() -> pd.DataFrame:
    # Official HF mirror: openai/gsm8k, main config.
    ds = load_dataset("openai/gsm8k", "main", split="test")
    rows = []
    for i, ex in enumerate(ds):
        rows.append({
            "dataset": "gsm8k",
            "task_type": "math",
            "source_split": "test",
            "source_index": i,
            "source_id": f"gsm8k_test_{i}",
            "context": "",
            "question": ex["question"].strip(),
            "choices_json": "",
            "gold_answer": gsm8k_gold(ex["answer"]),
            "gold_label": "",
        })
    return pd.DataFrame(rows)


def prepare_commonsenseqa() -> pd.DataFrame:
    # Use validation because the public test split does not expose labels.
    ds = load_dataset("tau/commonsense_qa", split="validation")
    rows = []
    for i, ex in enumerate(ds):
        labels = list(ex["choices"]["label"])
        texts = list(ex["choices"]["text"])
        mapping = dict(zip(labels, texts))
        gold_label = str(ex["answerKey"]).strip()
        rows.append({
            "dataset": "commonsense_qa",
            "task_type": "commonsense",
            "source_split": "validation",
            "source_index": i,
            "source_id": str(ex.get("id") or f"csqa_validation_{i}"),
            "context": "",
            "question": ex["question"].strip(),
            "choices_json": json.dumps({"label": labels, "text": texts}, ensure_ascii=False),
            "gold_answer": mapping[gold_label],
            "gold_label": gold_label,
        })
    return pd.DataFrame(rows)


def _normalize_logiqa_label(label) -> str:
    # Different HF mirrors expose either integer correct_option or string label.
    if isinstance(label, int):
        return LETTERS[label]
    s = str(label).strip()
    if s.isdigit():
        n = int(s)
        # LogiQA labels are commonly 0..3; keep a fallback for 1..4.
        if 0 <= n <= 3:
            return LETTERS[n]
        if 1 <= n <= 4:
            return LETTERS[n - 1]
    s = s.upper()
    if s in LETTERS:
        return s
    raise ValueError(f"Unknown LogiQA label: {label!r}")


def prepare_logiqa() -> pd.DataFrame:
    """
    Load the auto-converted Parquet revision of lucasmccabe/logiqa.

    New versions of `datasets` no longer execute the repository's legacy
    logiqa.py script. Hugging Face exposes an automatically converted
    Parquet revision under refs/convert/parquet, so we explicitly load that.
    """
    try:
        ds = load_dataset(
            "lucasmccabe/logiqa",
            split="validation",
            revision="refs/convert/parquet",
        )
    except Exception as e:
        raise RuntimeError(
            "Could not load LogiQA from Hugging Face's converted Parquet "
            "revision (refs/convert/parquet)."
        ) from e

    rows = []
    for i, ex in enumerate(ds):
        # Current converted LogiQA schema:
        # context, query, options, correct_option
        context = str(ex.get("context", "")).strip()
        question = str(ex.get("query", ex.get("question", ""))).strip()
        options = list(ex.get("options", ex.get("answers", [])))

        raw_label = ex.get("correct_option")
        if raw_label is None:
            raw_label = ex.get("label")
        if raw_label is None:
            raw_label = ex.get("answer")

        if raw_label is None:
            raise ValueError(
                f"Could not find LogiQA gold label at validation row {i}. "
                f"Available fields: {list(ex.keys())}"
            )

        gold_label = _normalize_logiqa_label(raw_label)
        labels = LETTERS[:len(options)]
        mapping = dict(zip(labels, options))

        if gold_label not in mapping:
            raise ValueError(
                f"LogiQA label {gold_label!r} not among {labels!r}; "
                f"source row {i}; raw label={raw_label!r}"
            )

        rows.append({
            "dataset": "logiqa",
            "task_type": "logical",
            "source_split": "validation",
            "source_index": i,
            "source_id": f"logiqa_validation_{i}",
            "context": context,
            "question": question,
            "choices_json": json.dumps(
                {"label": labels, "text": options},
                ensure_ascii=False,
            ),
            "gold_answer": mapping[gold_label],
            "gold_label": gold_label,
        })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["gsm8k", "commonsense_qa", "logiqa"],
        choices=["gsm8k", "commonsense_qa", "logiqa"],
    )
    args = parser.parse_args()

    loaders = {
        "gsm8k": prepare_gsm8k,
        "commonsense_qa": prepare_commonsenseqa,
        "logiqa": prepare_logiqa,
    }

    all_frames = []
    for name in args.datasets:
        print(f"[prepare] Loading {name} ...")
        df = loaders[name]()
        path = OUT_DIR / f"{name}_pool.csv"
        df.to_csv(path, index=False)
        all_frames.append(df)
        print(f"[prepare] {name}: {len(df)} rows -> {path}")

    combined = pd.concat(all_frames, ignore_index=True)
    combined_path = OUT_DIR / "all_dataset_pools.csv"
    combined.to_csv(combined_path, index=False)
    print(f"[prepare] Combined: {len(combined)} rows -> {combined_path}")


if __name__ == "__main__":
    main()
