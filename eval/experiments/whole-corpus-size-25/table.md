# Evidence — whole-corpus-size-25

experiment digest: 4c3d5c79ec44… · invocation: 335e52b91a5749fc83a2aa4467cd650d · repetitions: baseline 1, whole-corpus 1
corpus: ../../corpus/subsets/validation-en-25 (ba5aa8f9346d…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'baseline', pooled over the repetitions both ran, each paired with the same repetition of 'baseline'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'answer_correctness', higher-is-better, margin 0.05 — the verdict column reads the paired interval against it

| arm | metric | baseline | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| whole-corpus | answer_correctness | 0.736 (n 23) | 0.756 (n 23) | -0.032 to +0.077 | +0.020 | 23, 23 differing | unjudgeable | inconclusive |
| whole-corpus | token_recall | 0.540 (n 23) | 0.554 (n 23) | -0.020 to +0.054 | +0.015 | 23, 21 differing | unjudgeable | — |
| whole-corpus | rouge_l | 0.369 (n 23) | 0.342 (n 23) | -0.058 to +0.009 | -0.027 | 23, 23 differing | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 3.095 | 7.564 | embed: 251.3, generate: 1539.3, grade: 1426.7 |
| whole-corpus | 3.640 | 7.525 | embed: 253.8, generate: 95096.8, grade: 1517.5 |
