# Evidence — context-construction-en-fetch-widen

experiment digest: a59285c18c53… · invocation: df4496c8cb6d45009a3f0d902e9a5de7 · repetitions: 2
corpus: ../../corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
paired Δ and its interval: arm minus 'baseline' on repetition 1, 95% bootstrap interval over questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.

| arm | metric | baseline | arm | paired Δ | 95% CI | n | spread verdict |
|---|---|---|---|---|---|---|---|
| adjacent-chunks | token_recall | 0.462 (n 54) | 0.487 (n 54) | +0.025 | +0.007 to +0.043 | 54, 48 differing | outside-baseline-spread |
| adjacent-chunks | rouge_l | 0.328 (n 54) | 0.331 (n 54) | +0.003 | -0.016 to +0.023 | 54, 52 differing | within-baseline-spread |
| context-construction | token_recall | 0.462 (n 54) | 0.509 (n 54) | +0.047 | +0.025 to +0.070 | 54, 48 differing | outside-baseline-spread |
| context-construction | rouge_l | 0.328 (n 54) | 0.346 (n 54) | +0.018 | -0.005 to +0.044 | 54, 54 differing | outside-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 2.705 | 8.912 | embed: 36.0, generate: 1645.5 |
| adjacent-chunks | 2.947 | 7.055 | embed: 36.0, generate: 3912.2 |
| context-construction | 3.081 | 7.264 | embed: 72.0, generate: 3225.9 |
