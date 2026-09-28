# Evidence — whole-corpus-pl

experiment digest: d20cd7fdc3ce… · invocation: 800e1e9cf55644f5b260e9c9770d1297 · repetitions: 2
corpus: ../../corpus/pl-wiki (4514a81d6c14…)
minimum detectable effect: 0.24
interval and paired Δ: arm minus 'baseline', pooled over the repetitions both ran, each paired with the same repetition of 'baseline'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.

| arm | metric | baseline | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| whole-corpus | answer_correctness | 0.723 (n 12) | 0.706 (n 12) | -0.039 to +0.057 | +0.004 | 24, 24 differing | outside-baseline-spread |
| whole-corpus | token_recall | 0.459 (n 12) | 0.499 (n 12) | -0.038 to +0.059 | +0.013 | 24, 23 differing | outside-baseline-spread |
| whole-corpus | rouge_l | 0.233 (n 12) | 0.232 (n 12) | -0.052 to +0.018 | -0.018 | 24, 24 differing | within-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 3.533 | 5.900 | embed: 403.8, generate: 1650.0, grade: 1582.5 |
| whole-corpus | 3.843 | 7.110 | embed: 398.1, generate: 16277.7, grade: 1598.8 |
