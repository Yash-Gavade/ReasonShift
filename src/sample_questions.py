from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "data" / "processed"
OUT_DIR = ROOT / "data" / "sampled"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=50, help="Original items per dataset.")
    p.add_argument("--pilot-n", type=int, default=5, help="Pilot items per dataset.")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    frames = []
    pilot_frames = []
    for dataset in ["gsm8k", "commonsense_qa", "logiqa"]:
        src = IN_DIR / f"{dataset}_pool.csv"
        if not src.exists():
            raise FileNotFoundError(f"Run prepare_datasets.py first: missing {src}")
        df = pd.read_csv(src)
        if len(df) < args.n:
            raise ValueError(f"{dataset}: requested {args.n}, only {len(df)} available.")

        sampled = df.sample(n=args.n, random_state=args.seed).sort_values("source_index").copy()
        sampled.insert(0, "group_id", [f"RS_{dataset.upper()}_{i:03d}" for i in range(1, len(sampled)+1)])
        sampled.insert(1, "variant_type", "original")
        sampled.insert(2, "reasonshift_id", sampled["group_id"] + "_ORIG")
        frames.append(sampled)

        pilot = sampled.head(args.pilot_n).copy()
        pilot_frames.append(pilot)

    full = pd.concat(frames, ignore_index=True)
    pilot = pd.concat(pilot_frames, ignore_index=True)

    full_path = OUT_DIR / "original_questions.csv"
    pilot_path = OUT_DIR / "pilot_originals.csv"
    full.to_csv(full_path, index=False)
    pilot.to_csv(pilot_path, index=False)

    manifest = OUT_DIR / "sample_manifest.txt"
    manifest.write_text(
        "\n".join([
            f"seed={args.seed}",
            f"n_per_dataset={args.n}",
            f"pilot_n_per_dataset={args.pilot_n}",
            f"original_questions_sha256={sha256_file(full_path)}",
            f"pilot_originals_sha256={sha256_file(pilot_path)}",
        ]) + "\n",
        encoding="utf-8",
    )

    print(f"[sample] Full originals: {len(full)} -> {full_path}")
    print(f"[sample] Pilot originals: {len(pilot)} -> {pilot_path}")
    print(f"[sample] Manifest -> {manifest}")
    print(f"[sample] SHA256 full: {sha256_file(full_path)}")


if __name__ == "__main__":
    main()
