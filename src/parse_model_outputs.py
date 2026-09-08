from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_math(text):
    if not text:
        return None
    # Prefer a standalone final numeric expression.
    nums = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?(?:/\d+)?", str(text))
    if not nums:
        return None
    return nums[-1].replace(",", "")


def parse_mcq(text):
    if not text:
        return None
    s = str(text).strip().upper()
    # Strong first: single-letter response.
    m = re.fullmatch(r"\s*[\(\[]?([A-F])[\)\].:\s]*", s)
    if m:
        return m.group(1)
    # Then common answer patterns.
    for pat in [
        r"(?:ANSWER|OPTION|CHOICE)\s*[:\-]?\s*[\(\[]?([A-F])\b",
        r"^\s*[\(\[]?([A-F])[\)\].:]",
        r"\b([A-F])\b",
    ]:
        m = re.search(pat, s)
        if m:
            return m.group(1)
    return None


def normalize_num(x):
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    inp = Path(args.input)
    out = Path(args.output) if args.output else ROOT/"outputs"/"parsed"/(inp.stem + "_parsed.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    n = ok = correct = 0
    with inp.open("r", encoding="utf-8") as fi, out.open("w", encoding="utf-8") as fo:
        for line in fi:
            rec = json.loads(line)
            n += 1
            text = rec.get("raw_output")
            task = rec["task_type"]

            if task == "math":
                pred = parse_math(text)
                gold = str(rec["gold_answer"]).replace(",", "").strip()
                pv, gv = normalize_num(pred), normalize_num(gold)
                is_correct = pv is not None and gv is not None and abs(pv-gv) < 1e-9
            else:
                pred = parse_mcq(text)
                gold = str(rec.get("gold_label","")).strip().upper()
                is_correct = pred is not None and pred == gold

            parse_success = pred is not None
            ok += int(parse_success)
            correct += int(is_correct)

            rec["parsed_answer"] = pred
            rec["parse_success"] = parse_success
            rec["correct"] = bool(is_correct)
            fo.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[parse] records: {n}")
    print(f"[parse] success: {ok}/{n} ({100*ok/n:.1f}%)" if n else "[parse] no rows")
    print(f"[score] correct: {correct}/{n} ({100*correct/n:.1f}%)" if n else "")
    print(f"[done] -> {out}")


if __name__ == "__main__":
    main()
