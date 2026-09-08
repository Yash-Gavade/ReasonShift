import json
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.contingency_tables import mcnemar

# ============================================================
# PATHS / CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

PARSED_DIR = ROOT / "outputs" / "parsed"
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

FILES = {
    "Qwen2.5-3B-Instruct":
        PARSED_DIR / "qwen_2_5_3b_outputs_parsed.jsonl",

    "Llama-3.2-3B-Instruct":
        PARSED_DIR / "llama_3_2_3b_outputs_parsed.jsonl",

    "Gemma-3-1B-IT":
        PARSED_DIR / "gemma_3_1b_outputs_parsed.jsonl",
}

VARIANTS = [
    "original",
    "lexical",
    "syntactic",
    "information_order",
]

TRANSFORMATIONS = [
    "lexical",
    "syntactic",
    "information_order",
]

EXPECTED_ROWS_PER_MODEL = 120
EXPECTED_GROUPS_PER_MODEL = 30
EXPECTED_ROWS_PER_VARIANT = 30

EXPECTED_DATASETS = {
    "commonsense_qa": 40,
    "gsm8k": 40,
    "logiqa": 40,
}


# ============================================================
# HELPERS
# ============================================================

def read_jsonl(path):
    """Read JSONL file into a pandas DataFrame."""

    rows = []

    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                rows.append(json.loads(line))

            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON in {path} at line {line_number}: {e}"
                )

    return pd.DataFrame(rows)


def normalize_correct(series):
    """
    Convert the correct column safely to integer 0/1.
    Handles bools, integers and common string forms.
    """

    def convert(x):

        if isinstance(x, (bool, np.bool_)):
            return int(x)

        if isinstance(x, (int, np.integer)):
            return int(x != 0)

        if isinstance(x, (float, np.floating)):
            if pd.isna(x):
                return 0
            return int(x != 0)

        value = str(x).strip().lower()

        if value in {"true", "1", "yes", "correct"}:
            return 1

        if value in {"false", "0", "no", "incorrect", "", "nan", "none"}:
            return 0

        raise ValueError(f"Unexpected value in 'correct' column: {x!r}")

    return series.apply(convert).astype(int)


def bootstrap_delta(original, transformed, n_boot=5000, seed=42):
    """
    Paired bootstrap CI for:

        transformed_accuracy - original_accuracy
    """

    original = np.asarray(original, dtype=int)
    transformed = np.asarray(transformed, dtype=int)

    if len(original) != len(transformed):
        raise ValueError("Bootstrap arrays have different lengths.")

    if len(original) == 0:
        return np.nan, np.nan

    rng = np.random.default_rng(seed)

    deltas = np.empty(n_boot, dtype=float)

    for i in range(n_boot):

        idx = rng.integers(
            0,
            len(original),
            size=len(original)
        )

        deltas[i] = (
            transformed[idx] - original[idx]
        ).mean()

    low, high = np.percentile(
        deltas,
        [2.5, 97.5]
    )

    return float(low), float(high)


def benjamini_hochberg(p_values):
    """
    Benjamini-Hochberg FDR correction.
    """

    p_values = np.asarray(p_values, dtype=float)

    n = len(p_values)

    if n == 0:
        return np.array([])

    order = np.argsort(p_values)

    ranked = p_values[order]

    adjusted = np.empty(n, dtype=float)

    running_min = 1.0

    for i in range(n - 1, -1, -1):

        corrected = ranked[i] * n / (i + 1)

        running_min = min(
            running_min,
            corrected
        )

        adjusted[order[i]] = min(
            running_min,
            1.0
        )

    return adjusted


# ============================================================
# LOAD + VALIDATE FINAL MODEL OUTPUTS
# ============================================================

frames = []

print("=" * 70)
print("REASONSHIFT FINAL ANALYSIS")
print("=" * 70)

print("\nLoading parsed model outputs...\n")


required_columns = {
    "group_id",
    "dataset",
    "variant_type",
    "correct",
    "parsed_answer",
    "raw_output",
    "gold_answer",
    "gold_label",
}


for model, path in FILES.items():

    if not path.exists():
        raise FileNotFoundError(
            f"Missing parsed output file:\n{path}"
        )

    d = read_jsonl(path)

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    missing_columns = required_columns - set(d.columns)

    if missing_columns:

        raise ValueError(
            f"{model}: missing required columns: "
            f"{sorted(missing_columns)}"
        )

    # --------------------------------------------------------
    # Row count
    # --------------------------------------------------------

    if len(d) != EXPECTED_ROWS_PER_MODEL:

        raise ValueError(
            f"{model}: expected "
            f"{EXPECTED_ROWS_PER_MODEL} rows, "
            f"got {len(d)}"
        )

    # --------------------------------------------------------
    # Correct column
    # --------------------------------------------------------

    d["correct"] = normalize_correct(
        d["correct"]
    )

    # --------------------------------------------------------
    # Group count
    # --------------------------------------------------------

    n_groups = d["group_id"].nunique()

    if n_groups != EXPECTED_GROUPS_PER_MODEL:

        raise ValueError(
            f"{model}: expected "
            f"{EXPECTED_GROUPS_PER_MODEL} unique groups, "
            f"got {n_groups}"
        )

    # --------------------------------------------------------
    # Duplicate group × condition
    # --------------------------------------------------------

    duplicate_count = d.duplicated(
        subset=[
            "group_id",
            "variant_type"
        ]
    ).sum()

    if duplicate_count:

        raise ValueError(
            f"{model}: found "
            f"{duplicate_count} duplicate "
            f"group_id × variant_type rows"
        )

    # --------------------------------------------------------
    # Variant validation
    # --------------------------------------------------------

    observed_variants = set(
        d["variant_type"].unique()
    )

    expected_variants = set(VARIANTS)

    if observed_variants != expected_variants:

        raise ValueError(
            f"{model}: variant mismatch.\n"
            f"Expected: {sorted(expected_variants)}\n"
            f"Observed: {sorted(observed_variants)}"
        )

    variant_counts = (
        d["variant_type"]
        .value_counts()
        .to_dict()
    )

    for variant in VARIANTS:

        count = variant_counts.get(
            variant,
            0
        )

        if count != EXPECTED_ROWS_PER_VARIANT:

            raise ValueError(
                f"{model}: expected "
                f"{EXPECTED_ROWS_PER_VARIANT} rows "
                f"for {variant}, got {count}"
            )

    # --------------------------------------------------------
    # Dataset validation
    # --------------------------------------------------------

    dataset_counts = (
        d["dataset"]
        .value_counts()
        .to_dict()
    )

    for dataset, expected_count in EXPECTED_DATASETS.items():

        observed_count = dataset_counts.get(
            dataset,
            0
        )

        if observed_count != expected_count:

            raise ValueError(
                f"{model}: expected "
                f"{expected_count} rows for "
                f"{dataset}, got {observed_count}"
            )

    # --------------------------------------------------------
    # Each group must contain all four conditions
    # --------------------------------------------------------

    group_variant_counts = (
        d.groupby("group_id")["variant_type"]
        .nunique()
    )

    bad_groups = group_variant_counts[
        group_variant_counts != 4
    ]

    if len(bad_groups):

        raise ValueError(
            f"{model}: some groups do not "
            f"contain all four conditions:\n"
            f"{bad_groups}"
        )

    # --------------------------------------------------------
    # Add model name
    # --------------------------------------------------------

    d["model"] = model

    frames.append(d)

    print(
        f"[OK] {model}: "
        f"{len(d)} rows | "
        f"{n_groups} groups | "
        f"correct={d['correct'].sum()}/{len(d)} "
        f"({d['correct'].mean():.1%})"
    )


# ============================================================
# COMBINE ALL THREE MODELS
# ============================================================

df = pd.concat(
    frames,
    ignore_index=True
)

print(
    f"\nCombined final responses: {len(df)}"
)

if len(df) != 360:

    raise ValueError(
        f"Expected 360 total model responses, "
        f"got {len(df)}"
    )


# ============================================================
# 1. OVERALL ACCURACY
# ============================================================

overall = (
    df.groupby("model")["correct"]
    .agg(["count", "sum", "mean"])
    .reset_index()
)

overall.columns = [
    "model",
    "n",
    "correct",
    "accuracy",
]

overall.to_csv(
    RESULTS_DIR / "overall_accuracy_by_model.csv",
    index=False
)


# ============================================================
# 2. ACCURACY BY MODEL × TRANSFORMATION
# ============================================================

accuracy_variant = (
    df.groupby(
        [
            "model",
            "variant_type"
        ]
    )["correct"]
    .agg(["count", "sum", "mean"])
    .reset_index()
)

accuracy_variant.columns = [
    "model",
    "variant_type",
    "n",
    "correct",
    "accuracy",
]

accuracy_variant.to_csv(
    RESULTS_DIR / "accuracy_by_model_variant.csv",
    index=False
)


# ============================================================
# 3. ACCURACY BY MODEL × DATASET × TRANSFORMATION
# ============================================================

accuracy_dataset_variant = (
    df.groupby(
        [
            "model",
            "dataset",
            "variant_type"
        ]
    )["correct"]
    .agg(["count", "sum", "mean"])
    .reset_index()
)

accuracy_dataset_variant.columns = [
    "model",
    "dataset",
    "variant_type",
    "n",
    "correct",
    "accuracy",
]

accuracy_dataset_variant.to_csv(
    RESULTS_DIR / "accuracy_by_model_dataset_variant.csv",
    index=False
)


# ============================================================
# 4. PAIRED ROBUSTNESS ANALYSIS
# ============================================================

paired_rows = []
robust_rows = []


for model, model_df in df.groupby("model"):

    dataset_groups = list(
        model_df.groupby("dataset")
    )

    # Also calculate aggregate results
    dataset_groups.append(
        ("ALL", model_df)
    )

    for dataset, dataset_df in dataset_groups:

        wide = dataset_df.pivot(
            index="group_id",
            columns="variant_type",
            values="correct"
        )

        # Ensure fixed condition ordering
        wide = wide[VARIANTS]

        if wide.isna().any().any():

            raise ValueError(
                f"{model}/{dataset}: "
                f"missing condition values "
                f"in paired analysis"
            )

        original = (
            wide["original"]
            .astype(int)
            .astype(bool)
        )

        # ----------------------------------------------------
        # Robust accuracy:
        # question is correct under ALL four formulations
        # ----------------------------------------------------

        all_four_correct = (
            wide[VARIANTS]
            .astype(bool)
            .all(axis=1)
        )

        original_accuracy = (
            original.mean()
        )

        robust_accuracy = (
            all_four_correct.mean()
        )

        robust_rows.append({
            "model": model,
            "dataset": dataset,
            "n_groups": len(wide),
            "original_accuracy": original_accuracy,
            "robust_accuracy_core": robust_accuracy,
            "robustness_gap":
                robust_accuracy - original_accuracy,
            "all_four_correct":
                int(all_four_correct.sum()),
        })

        # ----------------------------------------------------
        # Original vs each transformation
        # ----------------------------------------------------

        for variant in TRANSFORMATIONS:

            transformed = (
                wide[variant]
                .astype(int)
                .astype(bool)
            )

            n11 = int(
                (original & transformed).sum()
            )

            n10 = int(
                (original & ~transformed).sum()
            )

            n01 = int(
                (~original & transformed).sum()
            )

            n00 = int(
                (~original & ~transformed).sum()
            )

            # Exact McNemar
            result = mcnemar(
                [
                    [n11, n10],
                    [n01, n00]
                ],
                exact=True
            )

            ci_low, ci_high = bootstrap_delta(
                original.astype(int),
                transformed.astype(int)
            )

            original_acc = (
                original.mean()
            )

            variant_acc = (
                transformed.mean()
            )

            accuracy_delta = (
                variant_acc -
                original_acc
            )

            flip_rate = (
                original != transformed
            ).mean()

            degradation_rate = (
                original &
                ~transformed
            ).mean()

            recovery_rate = (
                ~original &
                transformed
            ).mean()

            paired_rows.append({

                "model": model,
                "dataset": dataset,
                "variant_type": variant,

                "n_groups": len(wide),

                "original_accuracy":
                    original_acc,

                "variant_accuracy":
                    variant_acc,

                "accuracy_delta":
                    accuracy_delta,

                "delta_ci95_low":
                    ci_low,

                "delta_ci95_high":
                    ci_high,

                "correctness_flip_rate":
                    flip_rate,

                "degradation_rate":
                    degradation_rate,

                "recovery_rate":
                    recovery_rate,

                "correct_to_wrong":
                    n10,

                "wrong_to_correct":
                    n01,

                "both_correct":
                    n11,

                "both_wrong":
                    n00,

                "mcnemar_p":
                    float(result.pvalue),
            })


paired = pd.DataFrame(
    paired_rows
)

# BH correction across all paired tests
paired["mcnemar_p_bh"] = (
    benjamini_hochberg(
        paired["mcnemar_p"].values
    )
)

paired["significant_raw_005"] = (
    paired["mcnemar_p"] < 0.05
)

paired["significant_bh_005"] = (
    paired["mcnemar_p_bh"] < 0.05
)

paired.to_csv(
    RESULTS_DIR / "paired_robustness_results.csv",
    index=False
)


# ============================================================
# 5. ROBUST ACCURACY
# ============================================================

robust = pd.DataFrame(
    robust_rows
)

robust.to_csv(
    RESULTS_DIR / "robust_accuracy_results.csv",
    index=False
)


# ============================================================
# 6. TRANSITION CANDIDATES
# ============================================================

transition_rows = []


for model, model_df in df.groupby("model"):

    for dataset, dataset_df in model_df.groupby("dataset"):

        original_df = dataset_df[
            dataset_df["variant_type"] == "original"
        ][
            [
                "group_id",
                "correct",
                "parsed_answer",
                "raw_output",
                "gold_answer",
                "gold_label",
            ]
        ].copy()

        original_df = original_df.rename(
            columns={
                "correct":
                    "original_correct",

                "parsed_answer":
                    "original_answer",

                "raw_output":
                    "original_raw_output",
            }
        )

        for variant in TRANSFORMATIONS:

            transformed_df = dataset_df[
                dataset_df["variant_type"] == variant
            ][
                [
                    "group_id",
                    "correct",
                    "parsed_answer",
                    "raw_output",
                ]
            ].copy()

            transformed_df = transformed_df.rename(
                columns={
                    "correct":
                        "variant_correct",

                    "parsed_answer":
                        "variant_answer",

                    "raw_output":
                        "variant_raw_output",
                }
            )

            merged = original_df.merge(
                transformed_df,
                on="group_id",
                how="inner",
                validate="one_to_one"
            )

            for _, row in merged.iterrows():

                original_correct = bool(
                    row["original_correct"]
                )

                variant_correct = bool(
                    row["variant_correct"]
                )

                if (
                    original_correct
                    and not variant_correct
                ):

                    direction = (
                        "correct_to_wrong"
                    )

                elif (
                    not original_correct
                    and variant_correct
                ):

                    direction = (
                        "wrong_to_correct"
                    )

                elif (
                    original_correct
                    and variant_correct
                ):

                    direction = (
                        "correct_to_correct"
                    )

                else:

                    direction = (
                        "wrong_to_wrong"
                    )

                transition_rows.append({

                    "model":
                        model,

                    "dataset":
                        dataset,

                    "group_id":
                        row["group_id"],

                    "variant_type":
                        variant,

                    "direction":
                        direction,

                    "original_correct":
                        int(original_correct),

                    "variant_correct":
                        int(variant_correct),

                    "original_answer":
                        row["original_answer"],

                    "variant_answer":
                        row["variant_answer"],

                    "gold_answer":
                        row["gold_answer"],

                    "gold_label":
                        row["gold_label"],

                    "original_raw_output":
                        row["original_raw_output"],

                    "variant_raw_output":
                        row["variant_raw_output"],
                })


transitions = pd.DataFrame(
    transition_rows
)

transitions.to_csv(
    RESULTS_DIR / "transition_candidates.csv",
    index=False
)


# ============================================================
# 7. TRANSITION SUMMARY
# ============================================================

transition_summary = (
    transitions
    .groupby(
        [
            "model",
            "variant_type",
            "direction"
        ]
    )
    .size()
    .reset_index(name="count")
)

transition_summary.to_csv(
    RESULTS_DIR / "transition_summary.csv",
    index=False
)


# ============================================================
# 8. FINAL HUMAN-READABLE SUMMARY
# ============================================================

robust_all = robust[
    robust["dataset"] == "ALL"
].copy()

paired_all = paired[
    paired["dataset"] == "ALL"
].copy()


summary_lines = [

    "REASONSHIFT FINAL ANALYSIS SUMMARY",

    "=" * 78,

    "",

    "FINAL EXPERIMENT DESIGN",

    "30 original question groups",
    "10 CommonsenseQA + 10 GSM8K + 10 LogiQA",
    "4 formulations per group",
    "Original + Lexical + Syntactic + Information Order",
    "120 inputs per model",
    "3 models",
    "360 total model responses",

    "",

    "OVERALL ACCURACY",

    overall.to_string(
        index=False
    ),

    "",

    "ACCURACY BY TRANSFORMATION",

    accuracy_variant.to_string(
        index=False
    ),

    "",

    "ROBUST ACCURACY — ALL DATASETS",

    robust_all[
        [
            "model",
            "n_groups",
            "original_accuracy",
            "robust_accuracy_core",
            "robustness_gap",
            "all_four_correct",
        ]
    ].to_string(
        index=False
    ),

    "",

    "PAIRED ROBUSTNESS — ALL DATASETS",

    paired_all[
        [
            "model",
            "variant_type",
            "original_accuracy",
            "variant_accuracy",
            "accuracy_delta",
            "correctness_flip_rate",
            "degradation_rate",
            "recovery_rate",
            "correct_to_wrong",
            "wrong_to_correct",
            "mcnemar_p",
            "mcnemar_p_bh",
            "significant_bh_005",
        ]
    ].to_string(
        index=False
    ),

    "",

    "INTERPRETATION NOTE",

    (
        "Accuracy delta = transformed accuracy - "
        "original accuracy."
    ),

    (
        "Correctness flip rate measures how often "
        "the correctness state changes between the "
        "original and transformed formulation."
    ),

    (
        "Robust accuracy requires a question group "
        "to be answered correctly under all four "
        "formulations."
    ),

    (
        "McNemar tests are exact paired tests. "
        "mcnemar_p_bh contains Benjamini-Hochberg "
        "multiple-testing corrected p-values."
    ),

    (
        "Because the final benchmark contains only "
        "30 question groups, statistical power is "
        "limited. Effect sizes, flip rates, and "
        "paired transitions should therefore be "
        "reported alongside significance tests."
    ),
]


summary_text = "\n".join(
    summary_lines
)

summary_path = (
    RESULTS_DIR /
    "analysis_summary.txt"
)

summary_path.write_text(
    summary_text,
    encoding="utf-8"
)


# ============================================================
# DONE
# ============================================================

print("\n")
print(summary_text)

print("\n" + "=" * 70)
print("FILES CREATED")
print("=" * 70)

for filename in [
    "overall_accuracy_by_model.csv",
    "accuracy_by_model_variant.csv",
    "accuracy_by_model_dataset_variant.csv",
    "paired_robustness_results.csv",
    "robust_accuracy_results.csv",
    "transition_candidates.csv",
    "transition_summary.csv",
    "analysis_summary.txt",
]:

    print(
        "[done]",
        RESULTS_DIR / filename
    )

print("\nAnalysis completed successfully.")