# Evidence — whole-corpus-size-50

experiment digest: 72737c693d89… · invocation: 65978e3a3beb482fb75e9900e90d191a · repetitions: baseline 1, whole-corpus 1
corpus: ../../corpus/subsets/validation-en-50 (fa7a074ad22e…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'baseline', pooled over the repetitions both ran, each paired with the same repetition of 'baseline'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'answer_correctness', higher-is-better, margin 0.05 — the verdict column reads the paired interval against it

| arm | metric | baseline | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| whole-corpus | answer_correctness | 0.722 (n 50) | 0.758 (n 50) | -0.012 to +0.089 | +0.036 | 50, 50 differing | unjudgeable | inconclusive |
| whole-corpus | token_recall | 0.526 (n 50) | 0.569 (n 50) | +0.012 to +0.076 | +0.043 | 50, 44 differing | unjudgeable | — |
| whole-corpus | rouge_l | 0.352 (n 50) | 0.346 (n 50) | -0.036 to +0.033 | -0.005 | 50, 50 differing | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 3.037 | 7.761 | embed: 235.9, generate: 1554.9, grade: 1327.6 |
| whole-corpus | 4.459 | 10.074 | embed: 235.9, generate: 155693.2, grade: 1505.7 |
