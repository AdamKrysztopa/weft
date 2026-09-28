# Evidence — whole-corpus-en

experiment digest: 33af3a396a64… · invocation: 77a0ab088ccd43688bc0403932c95e6b · repetitions: 2
corpus: ../../corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'baseline', pooled over the repetitions both ran, each paired with the same repetition of 'baseline'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.

| arm | metric | baseline | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| whole-corpus | answer_correctness | 0.672 (n 107) | 0.743 (n 106, 1 excluded) | +0.039 to +0.117 | +0.075 | 210, 210 differing | outside-baseline-spread |
| whole-corpus | token_recall | 0.496 (n 107) | 0.542 (n 107) | +0.024 to +0.076 | +0.049 | 214, 196 differing | outside-baseline-spread |
| whole-corpus | rouge_l | 0.341 (n 107) | 0.338 (n 107) | -0.025 to +0.019 | -0.003 | 214, 212 differing | within-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 3.699 | 8.611 | embed: 241.3, generate: 1540.7, grade: 1346.0 |
| whole-corpus | 5.451 | 10.880 | embed: 237.9, generate: 261498.0, grade: 1490.3 |
