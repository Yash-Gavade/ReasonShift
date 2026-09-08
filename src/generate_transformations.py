from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "sampled" / "original_questions.csv"
OUT = ROOT / "data" / "transformations" / "full_transformation_sheet_v2.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

GENERATOR_ID = "Qwen/Qwen2.5-1.5B-Instruct"
TRANSFORMS = ["lexical", "syntactic", "information_order"]

PREFIX_ONLY = (
    "in other words",
    "given the same information",
    "considering the situation described",
    "considering the information above",
    "given the information provided",
)

NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?(?:/\d+)?")

def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip()

def num_multiset(s):
    return Counter(NUM_RE.findall(str(s)))

def split_choices(text):
    text = str(text)
    if "\n\nChoices:\n" in text:
        body, ch = text.split("\n\nChoices:\n", 1)
        return body, "Choices:\n" + ch.strip()
    return text, ""

def render_item(row):
    parts = []
    context = str(row.get("context", "") or "").strip()
    if context and context.lower() != "nan":
        parts.append(f"Context:\n{context}")
    parts.append(f"Question:\n{str(row['question']).strip()}")

    raw = row.get("choices_json", "")
    if isinstance(raw, str) and raw.strip() and raw.lower() != "nan":
        obj = json.loads(raw)
        parts.append(
            "Choices:\n" +
            "\n".join(f"{a}. {b}" for a,b in zip(obj["label"], obj["text"]))
        )
    return "\n\n".join(parts)

def prompt_for(kind, body):
    common = """You are creating a controlled NLP robustness benchmark.
Rewrite ONLY the supplied text. Preserve the exact intended meaning and correct answer.
STRICT CONSTRAINTS:
- Preserve every number, named entity, logical relation, negation, comparison, temporal relation, causal relation, and condition.
- Do not add or remove facts.
- Do not reveal or hint at the answer.
- Do not solve the problem.
- Do not add commentary such as "In other words", "Given the same information", or "Considering the situation".
- Return ONLY the rewritten text, with the same Context:/Question: labels when present.
"""
    if kind == "lexical":
        spec = """TRANSFORMATION TYPE: LEXICAL.
Make genuine lexical substitutions: replace at least one meaningful word or phrase with a natural semantic equivalent.
Keep the sentence/clause structure as similar as possible.
Do NOT satisfy this task only by changing punctuation, capitalization, discourse markers, or the question stem.
"""
    elif kind == "syntactic":
        spec = """TRANSFORMATION TYPE: SYNTACTIC.
Make a genuine grammatical restructuring while preserving meaning.
Examples: active/passive alternation, subordinate/main-clause restructuring, relative-clause restructuring, or a meaningful change in question syntax.
Do NOT satisfy this task only by adding a discourse prefix or swapping one synonym.
"""
    else:
        spec = """TRANSFORMATION TYPE: INFORMATION_ORDER.
Change the order in which existing information is presented while preserving all facts and dependencies.
For multi-sentence/context items, move at least one factual proposition to a different position.
For a single sentence with multiple clauses, reorder clauses or front/back a condition so that the information presentation order genuinely changes.
Keep the actual question/request semantically equivalent and do not merely add a discourse prefix.
"""
    return common + "\n" + spec + "\nTEXT TO REWRITE:\n" + body

def load_generator():
    tok = AutoTokenizer.from_pretrained(GENERATOR_ID)
    if tok.pad_token_id is None:
        tok.pad_token_id = tok.eos_token_id
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required. Run src.check_environment first.")
    model = AutoModelForCausalLM.from_pretrained(
        GENERATOR_ID,
        torch_dtype=torch.float16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    model.eval()
    return tok, model

def generate(tok, model, prompt, max_new_tokens=512):
    msgs=[{"role":"user","content":prompt}]
    formatted=tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)
    inputs=tok(formatted,return_tensors="pt",truncation=True,max_length=4096)
    dev=model.get_input_embeddings().weight.device
    inputs={k:v.to(dev) for k,v in inputs.items()}
    with torch.inference_mode():
        out=model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tok.pad_token_id,
            eos_token_id=tok.eos_token_id,
        )
    plen=inputs["input_ids"].shape[1]
    return tok.decode(out[0][plen:],skip_special_tokens=True).strip()

def strip_labels(s):
    return str(s).replace("Context:\n","").replace("Question:\n","").strip()

def prefix_only(original, transformed):
    o=norm(strip_labels(original)).lower()
    t=norm(strip_labels(transformed)).lower()
    if t == o:
        return True
    for p in PREFIX_ONLY:
        if t.startswith(p):
            rem=t[len(p):].lstrip(" ,:-")
            if rem == o:
                return True
    return False

def sentence_chunks(s):
    s=strip_labels(s)
    return [norm(x).lower() for x in re.split(r"(?<=[.!?])\s+",s) if norm(x)]

def auto_valid(kind, original_body, transformed_body):
    reasons=[]
    if not transformed_body.strip():
        reasons.append("empty")
    if norm(original_body)==norm(transformed_body):
        reasons.append("unchanged")
    if prefix_only(original_body, transformed_body):
        reasons.append("prefix_only")
    if num_multiset(original_body) != num_multiset(transformed_body):
        reasons.append("numbers_changed")

    # Require meaningful surface change.
    if len(norm(transformed_body)) < max(10, int(0.55*len(norm(original_body)))):
        reasons.append("too_short")

    # Information-order needs observable order/structure change.
    if kind=="information_order":
        o_chunks=sentence_chunks(original_body)
        t_chunks=sentence_chunks(transformed_body)
        if o_chunks == t_chunks:
            reasons.append("no_order_change")

    return (len(reasons)==0), reasons

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--max-attempts",type=int,default=4)
    ap.add_argument("--limit",type=int,default=None)
    ap.add_argument("--overwrite",action="store_true")
    args=ap.parse_args()

    if not SRC.exists():
        raise FileNotFoundError(SRC)
    if OUT.exists() and not args.overwrite:
        raise FileExistsError(f"{OUT} exists. Use --overwrite intentionally.")

    originals=pd.read_csv(SRC)
    if args.limit:
        originals=originals.head(args.limit)

    tok,model=load_generator()
    rows=[]

    total=len(originals)*3
    n=0
    for _,r in originals.iterrows():
        original=render_item(r)
        body, choice_block = split_choices(original)

        for kind in TRANSFORMS:
            n+=1
            accepted=False
            candidate=""
            reasons=[]
            attempts=0

            for attempts in range(1,args.max_attempts+1):
                candidate=generate(tok,model,prompt_for(kind,body))
                ok,reasons=auto_valid(kind,body,candidate)
                if ok:
                    accepted=True
                    break

            transformed = candidate
            if choice_block:
                transformed = transformed.rstrip() + "\n\n" + choice_block

            rows.append({
                "group_id":r["group_id"],
                "reasonshift_id":f"{r['group_id']}_{kind.upper()}",
                "dataset":r["dataset"],
                "task_type":r["task_type"],
                "variant_type":kind,
                "source_split":r["source_split"],
                "source_index":r["source_index"],
                "source_id":r["source_id"],
                "original_input":original,
                "transformed_input":transformed,
                "gold_answer":r["gold_answer"],
                "gold_label":r.get("gold_label",""),
                "generator_model":GENERATOR_ID,
                "generation_attempts":attempts,
                "auto_generation_pass":accepted,
                "auto_generation_reasons":";".join(reasons),
                "semantic_equivalence":"",
                "answer_preserved":"",
                "transformation_valid":"",
                "fluency":"",
                "answer_leakage":"",
                "validation_source":"",
                "notes":"",
            })
            print(f"[{n:>3}/{total}] {r['group_id']} {kind}: {'PASS' if accepted else 'REVIEW'} attempts={attempts} reasons={reasons}")

    out=pd.DataFrame(rows)
    out.to_csv(OUT,index=False,encoding="utf-8-sig")
    print(f"[done] rows={len(out)} -> {OUT}")
    print("[done] auto generation pass:",int(out.auto_generation_pass.sum()),"/",len(out))

if __name__=="__main__":
    main()
