# Evidence — musique-retrieval

experiment digest: 8a51134dea39… · invocation: 178fb26ddc3247619d0a54221fede3f8 · repetitions: dense 1, hybrid 1, multi-query 1, iterative 1, broad-and-refined 1
corpus: ../../corpus/musique/corpus (562c2bff7b0a…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'dense', pooled over the repetitions both ran, each paired with the same repetition of 'dense'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'dense'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'answer_correctness', higher-is-better, margin 0.05 — the verdict column reads the paired interval against it

| arm | metric | dense | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| hybrid | answer_correctness | 0.485 (n 600) | 0.487 (n 600) | -0.011 to +0.015 | +0.002 | 600, 500 differing | unjudgeable | benefit-ruled-out |
| hybrid | recall@5 | 0.748 (n 600) | 0.739 (n 600) | -0.020 to -0.001 | -0.010 | 600, 29 differing | unjudgeable | — |
| hybrid | recall@10 | — | — | — | — | — | unjudgeable | — |
| hybrid | exact_match | 0.000 (n 600) | 0.000 (n 600) | +0.000 to +0.000 | +0.000 | 600, 0 differing | unjudgeable | — |
| hybrid | f1_score | 0.133 (n 600) | 0.137 (n 600) | -0.006 to +0.014 | +0.004 | 600, 225 differing | unjudgeable | — |
| multi-query | answer_correctness | 0.485 (n 600) | 0.475 (n 599, 1 excluded) | -0.026 to +0.004 | -0.011 | 599, 509 differing | unjudgeable | benefit-ruled-out |
| multi-query | recall@5 | 0.748 (n 600) | 0.739 (n 600) | -0.022 to +0.004 | -0.010 | 600, 108 differing | unjudgeable | — |
| multi-query | recall@10 | — | — | — | — | — | unjudgeable | — |
| multi-query | exact_match | 0.000 (n 600) | 0.000 (n 600) | +0.000 to +0.000 | +0.000 | 600, 0 differing | unjudgeable | — |
| multi-query | f1_score | 0.133 (n 600) | 0.135 (n 600) | -0.008 to +0.014 | +0.002 | 600, 246 differing | unjudgeable | — |
| iterative | answer_correctness | 0.485 (n 600) | 0.505 (n 597, 3 excluded) | +0.002 to +0.034 | +0.018 | 597, 477 differing | unjudgeable | benefit-ruled-out |
| iterative | recall@5 | 0.748 (n 600) | 0.770 (n 597, 3 excluded) | +0.007 to +0.032 | +0.019 | 597, 89 differing | unjudgeable | — |
| iterative | recall@10 | — | — | — | — | — | unjudgeable | — |
| iterative | exact_match | 0.000 (n 600) | 0.000 (n 597, 3 excluded) | +0.000 to +0.000 | +0.000 | 597, 0 differing | unjudgeable | — |
| iterative | f1_score | 0.133 (n 600) | 0.140 (n 597, 3 excluded) | -0.003 to +0.016 | +0.006 | 597, 230 differing | unjudgeable | — |
| broad-and-refined | answer_correctness | 0.485 (n 600) | 0.494 (n 600) | -0.005 to +0.023 | +0.009 | 600, 494 differing | unjudgeable | benefit-ruled-out |
| broad-and-refined | recall@5 | 0.748 (n 600) | 0.761 (n 600) | +0.001 to +0.023 | +0.012 | 600, 85 differing | unjudgeable | — |
| broad-and-refined | recall@10 | — | — | — | — | — | unjudgeable | — |
| broad-and-refined | exact_match | 0.000 (n 600) | 0.000 (n 600) | +0.000 to +0.000 | +0.000 | 600, 0 differing | unjudgeable | — |
| broad-and-refined | f1_score | 0.133 (n 600) | 0.135 (n 600) | -0.009 to +0.013 | +0.002 | 600, 247 differing | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| dense | 2.387 | 8.349 | embed: 47.8, generate: 922.9, grade: 713.2 |
| hybrid | 2.394 | 6.457 | embed: 47.9, generate: 943.8, grade: 701.6 |
| multi-query | 5.691 | 11.860 | embed: 101.1, fanout: 675.6, generate: 932.7, grade: 706.3 |
| iterative | 4.672 | 18.032 | embed: 91.0, generate: 913.5, grade: 3106.5 |
| broad-and-refined | 6.255 | 21.733 | embed: 107.2, generate: 929.8, grade: 3078.2 |
