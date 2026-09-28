# Evidence — context-construction-pl-ir

experiment digest: c4d32b49c347… · invocation: 247ce33f3b4c4da0b0a8f266ab93828f · repetitions: 2
corpus: ../../corpus/pl-wiki (4514a81d6c14…)
minimum detectable effect: 0.24
interval and paired Δ: arm minus 'baseline', pooled over the repetitions both ran, each paired with the same repetition of 'baseline'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
at least one spread verdict below was judged against a zero-width baseline spread: these repetitions did not vary at all, which is a claim about them, not proof the system is deterministic.

| arm | metric | baseline | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| dedupe | recall@5 | 0.958 (n 12) | 0.958 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| dedupe | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| dedupe | ndcg@5 | 0.968 (n 12) | 0.968 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| dedupe | token_recall | 0.474 (n 12) | 0.492 (n 12) | -0.028 to +0.027 | -0.001 | 24, 20 differing | within-baseline-spread |
| dedupe | rouge_l | 0.256 (n 12) | 0.277 (n 12) | -0.022 to +0.022 | +0.000 | 24, 24 differing | outside-baseline-spread |
| dedupe-t030 | recall@5 | 0.958 (n 12) | 0.958 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t030 | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t030 | ndcg@5 | 0.968 (n 12) | 0.968 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t030 | token_recall | 0.474 (n 12) | 0.462 (n 12) | -0.017 to +0.053 | +0.017 | 24, 23 differing | within-baseline-spread |
| dedupe-t030 | rouge_l | 0.256 (n 12) | 0.208 (n 12) | -0.043 to +0.008 | -0.018 | 24, 24 differing | outside-baseline-spread |
| dedupe-t070 | recall@5 | 0.958 (n 12) | 0.958 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t070 | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t070 | ndcg@5 | 0.968 (n 12) | 0.968 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t070 | token_recall | 0.474 (n 12) | 0.462 (n 12) | -0.026 to +0.019 | -0.004 | 24, 18 differing | within-baseline-spread |
| dedupe-t070 | rouge_l | 0.256 (n 12) | 0.265 (n 12) | -0.027 to +0.024 | -0.002 | 24, 24 differing | within-baseline-spread |
| mmr | recall@5 | 0.958 (n 12) | 0.958 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| mmr | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| mmr | ndcg@5 | 0.968 (n 12) | 0.961 (n 12) | -0.020 to +0.000 | -0.007 | 24, 2 differing | outside-baseline-spread (zero-width) |
| mmr | token_recall | 0.474 (n 12) | 0.468 (n 12) | -0.044 to +0.047 | +0.001 | 24, 21 differing | within-baseline-spread |
| mmr | rouge_l | 0.256 (n 12) | 0.235 (n 12) | -0.051 to +0.027 | -0.010 | 24, 24 differing | outside-baseline-spread |
| mmr-w030 | recall@5 | 0.958 (n 12) | 1.000 (n 12) | +0.000 to +0.125 | +0.042 | 24, 2 differing | outside-baseline-spread (zero-width) |
| mmr-w030 | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| mmr-w030 | ndcg@5 | 0.968 (n 12) | 0.983 (n 12) | -0.031 to +0.077 | +0.015 | 24, 4 differing | outside-baseline-spread (zero-width) |
| mmr-w030 | token_recall | 0.474 (n 12) | 0.425 (n 12) | -0.087 to -0.006 | -0.045 | 24, 21 differing | outside-baseline-spread |
| mmr-w030 | rouge_l | 0.256 (n 12) | 0.225 (n 12) | -0.079 to +0.026 | -0.023 | 24, 24 differing | outside-baseline-spread |
| mmr-w100 | recall@5 | 0.958 (n 12) | 0.958 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | ndcg@5 | 0.968 (n 12) | 0.968 (n 12) | +0.000 to +0.000 | +0.000 | 24, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | token_recall | 0.474 (n 12) | 0.481 (n 12) | -0.036 to +0.040 | +0.005 | 24, 21 differing | within-baseline-spread |
| mmr-w100 | rouge_l | 0.256 (n 12) | 0.248 (n 12) | -0.024 to +0.031 | +0.005 | 24, 24 differing | within-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 2.750 | 4.526 | embed: 33.9, generate: 1654.9 |
| dedupe | 2.520 | 4.007 | embed: 33.9, generate: 1637.6 |
| dedupe-t030 | 2.482 | 4.221 | embed: 33.9, generate: 1663.8 |
| dedupe-t070 | 2.573 | 4.142 | embed: 33.9, generate: 1633.6 |
| mmr | 3.407 | 4.379 | embed: 67.8, generate: 1625.7 |
| mmr-w030 | 3.291 | 5.253 | embed: 67.8, generate: 1606.5 |
| mmr-w100 | 3.160 | 4.448 | embed: 67.8, generate: 1639.1 |
