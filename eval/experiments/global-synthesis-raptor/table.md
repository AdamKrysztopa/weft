# Evidence — global-synthesis-raptor

experiment digest: bee86cacf03e… · invocation: 8a4594b3f6ec480198cd1c15b4c79b40 · repetitions: dense 1, raptor 1
corpus: ../../corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'dense', pooled over the repetitions both ran, each paired with the same repetition of 'dense'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'dense'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'answer_correctness', higher-is-better, margin 0.05 — the verdict column reads the paired interval against it

| arm | metric | dense | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| raptor | answer_correctness | 0.485 (n 80) | 0.510 (n 80) | +0.000 to +0.051 | +0.025 | 80, 80 differing | unjudgeable | positive-below-margin |
| raptor | token_recall | 0.339 (n 80) | 0.364 (n 80) | +0.011 to +0.039 | +0.025 | 80, 75 differing | unjudgeable | — |
| raptor | rouge_l | 0.158 (n 80) | 0.148 (n 80) | -0.017 to -0.004 | -0.010 | 80, 80 differing | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| dense | 6.586 | 12.764 | embed: 496.7, generate: 1697.2, grade: 2269.2 |
| raptor | 7.461 | 12.902 | embed: 573.0, generate: 2134.5, grade: 2458.4 |
