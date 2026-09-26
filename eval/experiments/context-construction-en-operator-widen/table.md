# Evidence — context-construction-en-operator-widen

experiment digest: 69556de8f338… · invocation: 301036c84ba945858ab8f032cef0693b · repetitions: 2
corpus: ../../corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
interval and paired Δ: arm minus 'baseline' on repetition 1, 95% bootstrap interval over questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.

| arm | metric | baseline | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| adjacent-chunks | token_recall | 0.531 (n 53) | 0.554 (n 53) | -0.003 to +0.053 | +0.024 | 53, 43 differing | outside-baseline-spread |
| adjacent-chunks | rouge_l | 0.342 (n 53) | 0.333 (n 53) | -0.034 to +0.016 | -0.009 | 53, 50 differing | within-baseline-spread |
| context-construction | token_recall | 0.531 (n 53) | 0.561 (n 53) | +0.004 to +0.058 | +0.030 | 53, 51 differing | outside-baseline-spread |
| context-construction | rouge_l | 0.342 (n 53) | 0.339 (n 53) | -0.027 to +0.021 | -0.003 | 53, 53 differing | within-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 2.742 | 6.323 | embed: 29.0, generate: 1478.4 |
| adjacent-chunks | 2.874 | 6.361 | embed: 29.0, generate: 3654.8 |
| context-construction | 2.855 | 6.571 | embed: 58.0, generate: 3119.7 |
