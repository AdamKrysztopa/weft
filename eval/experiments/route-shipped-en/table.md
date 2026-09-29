# Evidence — route-shipped-en

experiment digest: d2bbda412bdc… · invocation: 05c3ea9337ad4b14aa01f71681a3eeaf · repetitions: fixed 1, route 1, by-score 1
corpus: ../../corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'fixed', pooled over the repetitions both ran, each paired with the same repetition of 'fixed'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'fixed'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'answer_correctness', higher-is-better, margin 0.03 — the verdict column reads the paired interval against it

| arm | metric | fixed | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| route | answer_correctness | 0.670 (n 107) | 0.670 (n 107) | -0.026 to +0.024 | -0.000 | 107, 106 differing | unjudgeable | benefit-ruled-out |
| route | token_recall | 0.502 (n 107) | 0.486 (n 107) | -0.032 to -0.001 | -0.016 | 107, 88 differing | unjudgeable | — |
| by-score | answer_correctness | 0.670 (n 107) | 0.682 (n 107) | -0.008 to +0.030 | +0.012 | 107, 106 differing | unjudgeable | benefit-ruled-out |
| by-score | token_recall | 0.502 (n 107) | 0.487 (n 107) | -0.027 to -0.004 | -0.015 | 107, 82 differing | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| fixed | 3.709 | 9.106 | embed: 244.4, generate: 1545.3, grade: 1374.5 |
| route | 7.656 | 21.766 | embed: 1263.8, generate: 1643.9, grade: 1910.5, route: 2665.0 |
| by-score | 6.519 | 12.892 | embed: 243.3, generate: 1541.9, grade: 1367.2, route: 2663.8 |
