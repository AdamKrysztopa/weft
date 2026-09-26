# Evidence — whole-corpus-pl

experiment digest: d20cd7fdc3ce… · invocation: 800e1e9cf55644f5b260e9c9770d1297 · repetitions: 2
corpus: ../../corpus/pl-wiki (4514a81d6c14…)
minimum detectable effect: 0.24
interval and paired Δ: arm minus 'baseline' on repetition 1, 95% bootstrap interval over questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.

| arm | metric | baseline | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| whole-corpus | answer_correctness | 0.723 (n 12) | 0.706 (n 12) | -0.079 to +0.049 | -0.017 | 12, 12 differing | outside-baseline-spread |
| whole-corpus | token_recall | 0.459 (n 12) | 0.499 (n 12) | -0.005 to +0.087 | +0.041 | 12, 12 differing | outside-baseline-spread |
| whole-corpus | rouge_l | 0.233 (n 12) | 0.232 (n 12) | -0.036 to +0.040 | -0.001 | 12, 12 differing | within-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 3.533 | 5.900 | embed: 403.8, generate: 1650.0, grade: 1582.5 |
| whole-corpus | 3.843 | 7.110 | embed: 398.1, generate: 16277.7, grade: 1598.8 |
