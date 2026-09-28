# Evidence — context-construction-en-fetch-widen

experiment digest: 280cac2cd82b… · invocation: 9253c9aae61644e58c34f17e535d2284 · repetitions: 2
corpus: ../../corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'baseline', pooled over the repetitions both ran, each paired with the same repetition of 'baseline'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.

| arm | metric | baseline | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| adjacent-chunks | token_recall | 0.464 (n 54) | 0.496 (n 54) | +0.026 to +0.060 | +0.042 | 108, 97 differing | outside-baseline-spread |
| adjacent-chunks | rouge_l | 0.328 (n 54) | 0.345 (n 54) | -0.004 to +0.032 | +0.014 | 108, 107 differing | outside-baseline-spread |
| context-construction | token_recall | 0.464 (n 54) | 0.499 (n 54) | +0.017 to +0.059 | +0.038 | 108, 90 differing | outside-baseline-spread |
| context-construction | rouge_l | 0.328 (n 54) | 0.340 (n 54) | -0.015 to +0.032 | +0.009 | 108, 108 differing | outside-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 2.869 | 8.568 | embed: 36.0, generate: 1638.4 |
| adjacent-chunks | 2.652 | 7.117 | embed: 36.0, generate: 3916.1 |
| context-construction | 2.854 | 7.520 | embed: 72.0, generate: 3224.4 |
