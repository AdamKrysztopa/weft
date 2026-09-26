# Evidence — whole-corpus-en

experiment digest: 33af3a396a64… · invocation: 77a0ab088ccd43688bc0403932c95e6b · repetitions: 2
corpus: ../../corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'baseline' on repetition 1, 95% bootstrap interval over questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.

| arm | metric | baseline | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| whole-corpus | answer_correctness | 0.672 (n 107) | 0.743 (n 106, 1 excluded) | +0.031 to +0.111 | +0.070 | 106, 106 differing | outside-baseline-spread |
| whole-corpus | token_recall | 0.496 (n 107) | 0.542 (n 107) | +0.021 to +0.072 | +0.046 | 107, 97 differing | outside-baseline-spread |
| whole-corpus | rouge_l | 0.341 (n 107) | 0.338 (n 107) | -0.025 to +0.021 | -0.002 | 107, 105 differing | within-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 3.699 | 8.611 | embed: 241.3, generate: 1540.7, grade: 1346.0 |
| whole-corpus | 5.451 | 10.880 | embed: 237.9, generate: 261498.0, grade: 1490.3 |
