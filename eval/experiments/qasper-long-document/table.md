# Evidence — qasper-long-document

experiment digest: 522c82d45c0b… · invocation: a0a82bd2d0334f55bffd5c025ab29519 · repetitions: dense 1, adjacent-chunks 1, context-construction 1
corpus: ../../corpus/qasper/corpus (5adcd095d6f1…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'dense', pooled over the repetitions both ran, each paired with the same repetition of 'dense'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'dense'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'answer_correctness', higher-is-better, margin 0.05 — the verdict column reads the paired interval against it

| arm | metric | dense | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| adjacent-chunks | answer_correctness | 0.232 (n 909, 1 excluded) | 0.239 (n 906, 4 excluded) | -0.002 to +0.018 | +0.008 | 905, 905 differing | unjudgeable | benefit-ruled-out |
| adjacent-chunks | f1_score | 0.074 (n 910) | 0.074 (n 910) | -0.004 to +0.003 | -0.001 | 910, 540 differing | unjudgeable | — |
| adjacent-chunks | recall@5 | 0.456 (n 910) | 0.457 (n 910) | +0.000 to +0.003 | +0.001 | 910, 1 differing | unjudgeable | — |
| adjacent-chunks | recall@10 | — | 0.481 (n 910) | — | — | — | unjudgeable | — |
| context-construction | answer_correctness | 0.232 (n 909, 1 excluded) | 0.234 (n 908, 2 excluded) | -0.008 to +0.013 | +0.003 | 907, 907 differing | unjudgeable | benefit-ruled-out |
| context-construction | f1_score | 0.074 (n 910) | 0.076 (n 910) | -0.002 to +0.006 | +0.002 | 910, 550 differing | unjudgeable | — |
| context-construction | recall@5 | 0.456 (n 910) | 0.453 (n 910) | -0.021 to +0.013 | -0.003 | 910, 57 differing | unjudgeable | — |
| context-construction | recall@10 | — | 0.501 (n 910) | — | — | — | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| dense | 3.516 | 6.675 | embed: 106.3, generate: 1142.8, grade: 914.8 |
| adjacent-chunks | 3.554 | 6.432 | embed: 113.7, generate: 2891.3, grade: 947.7 |
| context-construction | 3.213 | 5.727 | embed: 116.8, generate: 2760.5, grade: 918.5 |
