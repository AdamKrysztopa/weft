# Evidence — route-shipped-en-r44-13

experiment digest: df801a3d2629… · invocation: 003e6379bd6a4b88b0c8c2a9c8d1b972 · repetitions: fixed 1, route 1
corpus: ../../../../../../../Users/adamkrysztopa/projects/weft/corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'fixed', pooled over the repetitions both ran, each paired with the same repetition of 'fixed'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'fixed'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'answer_correctness', higher-is-better, margin 0.03 — the verdict column reads the paired interval against it

| arm | metric | fixed | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| route | answer_correctness | 0.661 (n 107) | 0.683 (n 107) | -0.001 to +0.046 | +0.022 | 107, 106 differing | unjudgeable | inconclusive |
| route | token_recall | 0.486 (n 107) | 0.498 (n 107) | -0.006 to +0.029 | +0.012 | 107, 88 differing | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| fixed | 2.999 | 8.226 | embed: 243.0, generate: 1543.3, grade: 1353.4 |
| route | 8.988 | 22.825 | embed: 1074.6, generate: 1753.6, grade: 2500.1, route: 2298.0 |
