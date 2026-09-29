# Evidence — quality-long-document

experiment digest: 8a647d38076b… · invocation: e96b04bfeeeb417aad7e9dee6c4761bd · repetitions: dense 1, adjacent-chunks 1, context-construction 1
corpus: ../../corpus/quality/corpus (3ffe67fa2e4f…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'dense', pooled over the repetitions both ran, each paired with the same repetition of 'dense'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'dense'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'answer_correctness', higher-is-better, margin 0.05 — the verdict column reads the paired interval against it

| arm | metric | dense | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| adjacent-chunks | answer_correctness | 0.538 (n 365) | 0.551 (n 365) | -0.011 to +0.040 | +0.013 | 365, 365 differing | unjudgeable | benefit-ruled-out |
| adjacent-chunks | f1_score | 0.345 (n 365) | 0.348 (n 365) | -0.015 to +0.022 | +0.003 | 365, 294 differing | unjudgeable | — |
| adjacent-chunks | recall@5 | 0.986 (n 365) | 0.986 (n 365) | +0.000 to +0.000 | +0.000 | 365, 0 differing | unjudgeable | — |
| adjacent-chunks | recall@10 | — | 0.989 (n 365) | — | — | — | unjudgeable | — |
| context-construction | answer_correctness | 0.538 (n 365) | 0.560 (n 365) | -0.003 to +0.048 | +0.022 | 365, 365 differing | unjudgeable | benefit-ruled-out |
| context-construction | f1_score | 0.345 (n 365) | 0.356 (n 365) | -0.009 to +0.031 | +0.011 | 365, 292 differing | unjudgeable | — |
| context-construction | recall@5 | 0.986 (n 365) | 0.984 (n 365) | -0.014 to +0.005 | -0.003 | 365, 3 differing | unjudgeable | — |
| context-construction | recall@10 | — | 0.992 (n 365) | — | — | — | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| dense | 2.209 | 4.651 | embed: 104.2, generate: 1264.1, grade: 738.2 |
| adjacent-chunks | 2.101 | 4.952 | embed: 104.9, generate: 3198.6, grade: 742.0 |
| context-construction | 2.516 | 5.231 | embed: 164.9, generate: 2771.6, grade: 726.4 |
