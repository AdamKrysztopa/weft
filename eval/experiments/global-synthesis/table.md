# Evidence — global-synthesis

experiment digest: 998817f06da3… · invocation: 66c44023c1004b06b13d07ad633e6540 · repetitions: dense 1, whole-corpus 1, summarise 1, graph 1
corpus: ../../corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'dense', pooled over the repetitions both ran, each paired with the same repetition of 'dense'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'dense'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'answer_correctness', higher-is-better, margin 0.05 — the verdict column reads the paired interval against it

| arm | metric | dense | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| whole-corpus | answer_correctness | 0.496 (n 80) | 0.555 (n 80) | +0.030 to +0.089 | +0.059 | 80, 80 differing | unjudgeable | worthwhile |
| whole-corpus | token_recall | 0.348 (n 80) | 0.506 (n 80) | +0.138 to +0.177 | +0.158 | 80, 78 differing | unjudgeable | — |
| whole-corpus | rouge_l | 0.158 (n 80) | 0.147 (n 80) | -0.017 to -0.004 | -0.011 | 80, 80 differing | unjudgeable | — |
| summarise | answer_correctness | 0.496 (n 80) | 0.478 (n 80) | -0.049 to +0.010 | -0.018 | 80, 80 differing | unjudgeable | benefit-ruled-out |
| summarise | token_recall | 0.348 (n 80) | 0.275 (n 80) | -0.087 to -0.058 | -0.072 | 80, 77 differing | unjudgeable | — |
| summarise | rouge_l | 0.158 (n 80) | 0.159 (n 80) | -0.005 to +0.008 | +0.001 | 80, 80 differing | unjudgeable | — |
| graph | answer_correctness | 0.496 (n 80) | 0.416 (n 80) | -0.111 to -0.049 | -0.080 | 80, 80 differing | unjudgeable | harm |
| graph | token_recall | 0.348 (n 80) | 0.279 (n 80) | -0.086 to -0.054 | -0.069 | 80, 74 differing | unjudgeable | — |
| graph | rouge_l | 0.158 (n 80) | 0.148 (n 80) | -0.016 to -0.003 | -0.010 | 80, 80 differing | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| dense | 6.950 | 11.903 | embed: 504.1, generate: 1672.7, grade: 2309.4 |
| whole-corpus | 11.065 | 18.834 | embed: 797.5, generate: 262127.5, grade: 2944.5 |
| summarise | 18.373 | 38.156 | embed: 404.6, generate: 477.3, grade: 2172.9, index: 7401.9 |
| graph | 7.173 | 12.595 | embed: 427.4, generate: 1033.9, grade: 2103.6 |
