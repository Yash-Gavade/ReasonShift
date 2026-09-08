# ReasonShift Novelty Audit — Phase 1

## Closest prior work

### Srikanth, Carpuat & Rudinger (TACL 2024)
Directly studies natural-language reasoning under meaning-preserving paraphrases and introduces ParaNlu and paraphrastic-consistency analysis.

**Overlap with ReasonShift:** paraphrase sensitivity, paired reasoning evaluation, semantic preservation.

**What ReasonShift must NOT claim:** that discovering paraphrase sensitivity in LLM reasoning is new.

**ReasonShift distinction:** controlled transformation *types* (lexical, syntactic, information order), directional correctness transitions, task/model fragility profiles, and manually analysed failure-state transitions.

### Elgaar & Amiri (Findings EMNLP 2025)
Introduces linguistically controlled paraphrase generation with fine-grained control over linguistic attributes while preserving semantic fidelity.

**Overlap:** controlled linguistic variation.

**Difference:** their contribution is paraphrase generation/control; ReasonShift evaluates downstream reasoning robustness and failure transitions.

### Xu et al. (Findings ACL 2025)
Introduces a 6-primary/15-secondary error-attribution framework, AttriData, and an automated judge.

**Overlap:** fine-grained failure diagnosis.

**Difference:** ReasonShift does not build a universal evaluator. It analyses how failure states change between an original item and a controlled linguistic variant of the same item.

## Defensible novelty statement

ReasonShift investigates linguistic robustness at the level of controlled transformation types and paired failure transitions. Rather than treating paraphrase sensitivity as one aggregate property, it measures how lexical, syntactic, and information-structural reformulations change correctness across reasoning tasks and small open-source LLMs, then analyses the transitions between behavioural error states.

## Contributions to target

1. A manually validated controlled transformation set derived from three reasoning benchmarks.
2. Paired evaluation across lexical, syntactic, and information-order transformations.
3. Robustness analysis using directional correctness flips and group-level robust accuracy.
4. Failure-transition analysis linking linguistic transformation types to changes in behavioural error states.

## Claims to avoid

- “First-ever study of paraphrase robustness.”
- “First study showing LLMs are sensitive to wording.”
- Any novel metric claim unless mathematical equivalence with prior metrics is ruled out.
- Any causal claim that wording alone caused a specific internal reasoning process.
