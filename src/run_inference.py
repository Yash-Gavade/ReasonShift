from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "validated" / "reasonshift_dataset.csv"
MODEL_CONFIG = ROOT / "configs" / "models.json"
OUT_DIR = ROOT / "outputs" / "generations"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def build_prompt(row) -> str:
    task = row["task_type"]
    text = row["input_text"]

    if task == "math":
        instruction = (
            "Solve the problem and return only the final numerical answer. "
            "Do not include explanation."
        )
    elif task in {"commonsense", "logical"}:
        instruction = (
            "Answer the multiple-choice question and return only the option letter "
            "(for example: A, B, C, or D). Do not include explanation."
        )
    else:
        instruction = "Return only the final answer. Do not include explanation."

    return f"{instruction}\n\n{text}"


def load_model(model_id: str, trust_remote_code: bool):
    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        trust_remote_code=trust_remote_code,
    )

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    # fp16 on CUDA is the most compatible baseline for the user's Windows setup.
    # device_map='auto' permits CPU offload if the model does not fully fit VRAM.
    kwargs = {
        "trust_remote_code": trust_remote_code,
        "device_map": "auto",
        "low_cpu_mem_usage": True,
    }

    if torch.cuda.is_available():
        kwargs["torch_dtype"] = torch.float16
    else:
        kwargs["torch_dtype"] = torch.float32

    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    model.eval()
    return tokenizer, model


def generate_one(tokenizer, model, prompt: str, max_new_tokens: int):
    messages = [{"role": "user", "content": prompt}]
    try:
        formatted = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        formatted = prompt

    inputs = tokenizer(
        formatted,
        return_tensors="pt",
        truncation=True,
        max_length=4096,
    )

    # Put tensors on the model's first device.
    try:
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
    except Exception:
        pass

    t0 = time.perf_counter()
    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.perf_counter() - t0

    prompt_len = inputs["input_ids"].shape[1]
    generated = output_ids[0][prompt_len:]
    text = tokenizer.decode(generated, skip_special_tokens=True).strip()

    return text, elapsed, int(len(generated))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["qwen_2_5_3b","llama_3_2_3b","gemma_3_1b"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dataset", choices=["gsm8k","commonsense_qa","logiqa"], default=None)
    ap.add_argument("--variant", choices=["original","lexical","syntactic","information_order"], default=None)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    configs = json.loads(MODEL_CONFIG.read_text(encoding="utf-8"))
    cfg = configs[args.model]

    df = pd.read_csv(DATASET)
    if args.dataset:
        df = df[df["dataset"] == args.dataset]
    if args.variant:
        df = df[df["variant_type"] == args.variant]
    if args.limit is not None:
        df = df.head(args.limit)

    suffix = []
    if args.dataset: suffix.append(args.dataset)
    if args.variant: suffix.append(args.variant)
    if args.limit is not None: suffix.append(f"limit{args.limit}")
    suffix_str = "_" + "_".join(suffix) if suffix else ""
    out_path = OUT_DIR / f"{args.model}{suffix_str}_outputs.jsonl"

    if out_path.exists() and not args.overwrite:
        print(f"[STOP] Output exists: {out_path}")
        print("Use --overwrite only if you intentionally want to rerun this exact job.")
        return

    print(f"[model] {args.model}: {cfg['hf_id']}")
    print(f"[rows] {len(df)}")
    print(f"[cuda] {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"[gpu] {torch.cuda.get_device_name(0)}")

    tokenizer, model = load_model(cfg["hf_id"], cfg.get("trust_remote_code", False))

    with out_path.open("w", encoding="utf-8") as f:
        for j, (_, row) in enumerate(df.iterrows(), start=1):
            prompt = build_prompt(row)
            rec = {
                "reasonshift_id": row["reasonshift_id"],
                "group_id": row["group_id"],
                "dataset": row["dataset"],
                "task_type": row["task_type"],
                "variant_type": row["variant_type"],
                "model_key": args.model,
                "model_id": cfg["hf_id"],
                "gold_answer": row["gold_answer"],
                "gold_label": row.get("gold_label", ""),
                "prompt": prompt,
                "raw_output": None,
                "generation_time_sec": None,
                "generated_tokens": None,
                "error": None,
            }

            try:
                text, elapsed, ntok = generate_one(
                    tokenizer, model, prompt, cfg["max_new_tokens"]
                )
                rec["raw_output"] = text
                rec["generation_time_sec"] = elapsed
                rec["generated_tokens"] = ntok
            except Exception as e:
                rec["error"] = repr(e)

            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()

            status = "OK" if rec["error"] is None else "ERR"
            print(f"[{j:>4}/{len(df)}] {status} {row['reasonshift_id']} -> {rec['raw_output']!r}")

    print(f"[done] -> {out_path}")


if __name__ == "__main__":
    main()
