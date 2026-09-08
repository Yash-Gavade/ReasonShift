from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--input",
        default=str(ROOT / "data" / "transformations" / "pilot_transformation_sheet.csv"),
    )
    args = p.parse_args()

    path = Path(args.input)
    df = pd.read_csv(path)

    required = [
        "semantic_equivalence", "answer_preserved",
        "transformation_valid", "fluency", "answer_leakage"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing validation columns: {missing}")

    def norm(v):
        return str(v).strip().upper()

    accepted = (
        df["semantic_equivalence"].map(norm).eq("YES")
        & df["answer_preserved"].map(norm).eq("YES")
        & df["transformation_valid"].map(norm).eq("YES")
        & df["answer_leakage"].map(norm).eq("NO")
        & pd.to_numeric(df["fluency"], errors="coerce").ge(2)
        & df["transformed_input"].fillna("").str.strip().ne("")
    )

    df["accepted"] = accepted
    out = path.with_name(path.stem + "_validated.csv")
    df.to_csv(out, index=False)

    print(f"[validate] accepted {accepted.sum()}/{len(df)} ({accepted.mean()*100:.1f}%)")
    print(f"[validate] rejected {len(df)-accepted.sum()}/{len(df)}")
    print(f"[validate] -> {out}")

    if accepted.mean() < 0.80:
        print("[STOP] Acceptance <80%. Refine transformation protocol before scaling.")
    else:
        print("[PASS] Pilot acceptance >=80%. Scaling is reasonable after manual review.")


if __name__ == "__main__":
    main()
