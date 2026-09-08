# Transformation Validation Guidelines

For every generated variant assign:

- semantic_equivalence: YES / NO / UNCERTAIN
- answer_preserved: YES / NO / UNCERTAIN
- transformation_valid: YES / NO / UNCERTAIN
- fluency: 1 / 2 / 3
- answer_leakage: YES / NO

Reject a variant if semantic_equivalence != YES, answer_preserved != YES, transformation_valid != YES, or answer_leakage == YES.

## Fatal errors
- Negation added/dropped.
- Number or entity changed.
- Subject/object or relational roles reversed.
- Temporal/causal direction altered.
- Answer choice content changed.
- New information that affects the answer.
- Explicit or implicit answer leakage.

## Category boundaries
Lexical: primarily wording changes; structure should remain substantially similar.
Syntactic: grammatical/clausal organization changes; facts/order need not be intentionally reordered.
Information order: the presentation order of existing facts is deliberately changed.
