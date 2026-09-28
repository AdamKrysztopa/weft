# Evidence — context-construction-pl-widen

experiment digest: 9bddf6a9c2a7… · invocation: e0782e833c884013835c83aae6d184ba · repetitions: 2
corpus: ../../corpus/pl-wiki (4514a81d6c14…)
minimum detectable effect: 0.24
interval and paired Δ: arm minus 'baseline', pooled over the repetitions both ran, each paired with the same repetition of 'baseline'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.

| arm | metric | baseline | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| adjacent-chunks | token_recall | 0.486 (n 12) | 0.483 (n 12) | -0.041 to +0.029 | -0.009 | 24, 19 differing | within-baseline-spread |
| adjacent-chunks | rouge_l | 0.267 (n 12) | 0.248 (n 12) | -0.036 to +0.005 | -0.016 | 24, 24 differing | within-baseline-spread |
| context-construction | token_recall | 0.486 (n 12) | 0.479 (n 12) | -0.056 to +0.027 | -0.011 | 24, 17 differing | within-baseline-spread |
| context-construction | rouge_l | 0.267 (n 12) | 0.238 (n 12) | -0.039 to +0.013 | -0.015 | 24, 22 differing | within-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 3.054 | 4.818 | embed: 33.9, generate: 1655.2 |
| adjacent-chunks | 2.680 | 3.954 | embed: 33.9, generate: 3996.8 |
| context-construction | 3.216 | 4.120 | embed: 67.8, generate: 2651.5 |
