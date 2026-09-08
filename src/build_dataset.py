from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ORIGINALS = ROOT / "data" / "sampled" / "original_questions.csv"
DEFAULT_TRANSFORMED = (
    ROOT / "data" / "transformations" / "full_transformation_sheet_validated.csv"
)
OUT_DIR = ROOT / "data" / "validated"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def render_original(row):
    import json

    parts = []
    context = str(row.get("context", "") or "").strip()
    if context and context.lower() != "nan":
        parts.append(f"Context:\n{context}")

    parts.append(f"Question:\n{str(row['question']).strip()}")

    raw_choices = row.get("choices_json", "")
    if isinstance(raw_choices, str) and raw_choices.strip() and raw_choices.lower() != "nan":
        obj = json.loads(raw_choices)
        parts.append(
            "Choices:\n" +
            "\n".join(
                f"{a}. {b}" for a, b in zip(obj["label"], obj["text"])
            )
        )

    return "\n\n".join(parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--transformations", default=str(DEFAULT_TRANSFORMED))
    args = p.parse_args()

    transformed_path = Path(args.transformations)

    if not ORIGINALS.exists():
        raise FileNotFoundError(ORIGINALS)
    if not transformed_path.exists():
        raise FileNotFoundError(transformed_path)

    originals = pd.read_csv(ORIGINALS)
    transformed = pd.read_csv(transformed_path)

    if "accepted" not in transformed.columns:
        raise ValueError(
            "Transformation file has no `accepted` column. "
            "Run check_full_transformations.py first."
        )

    # Robustly interpret bools saved to CSV.
    accepted = transformed["accepted"].astype(str).str.lower().eq("true")
    transformed = transformed.loc[accepted].copy()

    if len(originals) != 150:
        raise ValueError(f"Expected 150 originals, found {len(originals)}.")
    if len(transformed) != 450:
        raise ValueError(
            f"Expected all 450 transformations to be accepted before inference; "
            f"found {len(transformed)}."
        )

    original_records = pd.DataFrame({
        "group_id": originals["group_id"],
        "reasonshift_id": originals["reasonshift_id"],
        "dataset": originals["dataset"],
        "task_type": originals["task_type"],
        "variant_type": "original",
        "input_text": originals.apply(render_original, axis=1),
        "gold_answer": originals["gold_answer"],
        "gold_label": originals["gold_label"],
        "source_split": originals["source_split"],
        "source_index": originals["source_index"],
        "source_id": originals["source_id"],
    })

    transformed_records = pd.DataFrame({
        "group_id": transformed["group_id"],
        "reasonshift_id": transformed["reasonshift_id"],
        "dataset": transformed["dataset"],
        "task_type": transformed["task_type"],
        "variant_type": transformed["variant_type"],
        "input_text": transformed["transformed_input"],
        "gold_answer": transformed["gold_answer"],
        "gold_label": transformed["gold_label"],
        "source_split": transformed["source_split"],
        "source_index": transformed["source_index"],
        "source_id": transformed["source_id"],
    })

    final = pd.concat(
        [original_records, transformed_records],
        ignore_index=True,
    )

    # Stable ordering: group, then original/lexical/syntactic/order.
    order = {
        "original": 0,
        "lexical": 1,
        "syntactic": 2,
        "information_order": 3,
    }
    final["_variant_order"] = final["variant_type"].map(order)
    final = (
        final.sort_values(["dataset", "group_id", "_variant_order"])
        .drop(columns="_variant_order")
        .reset_index(drop=True)
    )

    if len(final) != 600:
        raise AssertionError(f"Expected final dataset size 600, found {len(final)}.")

    # Every group must contain exactly four conditions.
    sizes = final.groupby("group_id").size()
    if not (sizes == 4).all():
        bad = sizes[sizes != 4]
        raise ValueError(f"Invalid group sizes:\n{bad}")

    final_path = OUT_DIR / "reasonshift_dataset.csv"
    final.to_csv(final_path, index=False)

    manifest = OUT_DIR / "reasonshift_dataset_manifest.txt"
    manifest.write_text(
        "\n".join([
            f"rows={len(final)}",
            f"groups={final['group_id'].nunique()}",
            f"datasets={','.join(sorted(final['dataset'].unique()))}",
            "conditions=original,lexical,syntactic,information_order",
            f"sha256={sha256_file(final_path)}",
        ]) + "\n",
        encoding="utf-8",
    )

    print(f"[build] final rows: {len(final)}")
    print(f"[build] question groups: {final['group_id'].nunique()}")
    print("[build] conditions:")
    print(final["variant_type"].value_counts().to_string())
    print(f"[build] -> {final_path}")
    print(f"[build] manifest -> {manifest}")
    print(f"[build] SHA256: {sha256_file(final_path)}")


if __name__ == "__main__":
    main()
