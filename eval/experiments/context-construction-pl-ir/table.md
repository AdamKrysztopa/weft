# Evidence — context-construction-pl-ir

experiment digest: c4d32b49c347… · invocation: 247ce33f3b4c4da0b0a8f266ab93828f · repetitions: 2
corpus: ../../corpus/pl-wiki (4514a81d6c14…)
minimum detectable effect: 0.24
paired Δ and its interval: arm minus 'baseline' on repetition 1, 95% bootstrap interval over questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
at least one spread verdict below was judged against a zero-width baseline spread: these repetitions did not vary at all, which is a claim about them, not proof the system is deterministic.

| arm | metric | baseline | arm | paired Δ | 95% CI | n | spread verdict |
|---|---|---|---|---|---|---|---|
| dedupe | recall@5 | 0.958 (n 12) | 0.958 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| dedupe | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| dedupe | ndcg@5 | 0.968 (n 12) | 0.968 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| dedupe | token_recall | 0.474 (n 12) | 0.492 (n 12) | +0.017 | -0.023 to +0.059 | 12, 11 differing | within-baseline-spread |
| dedupe | rouge_l | 0.256 (n 12) | 0.277 (n 12) | +0.021 | -0.014 to +0.058 | 12, 12 differing | outside-baseline-spread |
| dedupe-t030 | recall@5 | 0.958 (n 12) | 0.958 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t030 | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t030 | ndcg@5 | 0.968 (n 12) | 0.968 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t030 | token_recall | 0.474 (n 12) | 0.462 (n 12) | -0.012 | -0.064 to +0.039 | 12, 12 differing | within-baseline-spread |
| dedupe-t030 | rouge_l | 0.256 (n 12) | 0.208 (n 12) | -0.048 | -0.095 to -0.005 | 12, 12 differing | outside-baseline-spread |
| dedupe-t070 | recall@5 | 0.958 (n 12) | 0.958 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t070 | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t070 | ndcg@5 | 0.968 (n 12) | 0.968 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t070 | token_recall | 0.474 (n 12) | 0.462 (n 12) | -0.013 | -0.037 to +0.014 | 12, 8 differing | within-baseline-spread |
| dedupe-t070 | rouge_l | 0.256 (n 12) | 0.265 (n 12) | +0.009 | -0.025 to +0.048 | 12, 12 differing | within-baseline-spread |
| mmr | recall@5 | 0.958 (n 12) | 0.958 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| mmr | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| mmr | ndcg@5 | 0.968 (n 12) | 0.961 (n 12) | -0.007 | -0.020 to +0.000 | 12, 1 differing | outside-baseline-spread (zero-width) |
| mmr | token_recall | 0.474 (n 12) | 0.468 (n 12) | -0.006 | -0.060 to +0.048 | 12, 11 differing | within-baseline-spread |
| mmr | rouge_l | 0.256 (n 12) | 0.235 (n 12) | -0.020 | -0.076 to +0.025 | 12, 12 differing | outside-baseline-spread |
| mmr-w030 | recall@5 | 0.958 (n 12) | 1.000 (n 12) | +0.042 | +0.000 to +0.125 | 12, 1 differing | outside-baseline-spread (zero-width) |
| mmr-w030 | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| mmr-w030 | ndcg@5 | 0.968 (n 12) | 0.983 (n 12) | +0.015 | -0.031 to +0.077 | 12, 2 differing | outside-baseline-spread (zero-width) |
| mmr-w030 | token_recall | 0.474 (n 12) | 0.425 (n 12) | -0.049 | -0.106 to +0.005 | 12, 12 differing | outside-baseline-spread |
| mmr-w030 | rouge_l | 0.256 (n 12) | 0.225 (n 12) | -0.031 | -0.089 to +0.024 | 12, 12 differing | outside-baseline-spread |
| mmr-w100 | recall@5 | 0.958 (n 12) | 0.958 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | mrr@5 | 1.000 (n 12) | 1.000 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | ndcg@5 | 0.968 (n 12) | 0.968 (n 12) | +0.000 | +0.000 to +0.000 | 12, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | token_recall | 0.474 (n 12) | 0.481 (n 12) | +0.006 | -0.047 to +0.051 | 12, 11 differing | within-baseline-spread |
| mmr-w100 | rouge_l | 0.256 (n 12) | 0.248 (n 12) | -0.008 | -0.039 to +0.021 | 12, 12 differing | within-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 2.750 | 4.526 | embed: 33.9, generate: 1654.9 |
| dedupe | 2.520 | 4.007 | embed: 33.9, generate: 1637.6 |
| dedupe-t030 | 2.482 | 4.221 | embed: 33.9, generate: 1663.8 |
| dedupe-t070 | 2.573 | 4.142 | embed: 33.9, generate: 1633.6 |
| mmr | 3.407 | 4.379 | embed: 67.8, generate: 1625.7 |
| mmr-w030 | 3.291 | 5.253 | embed: 67.8, generate: 1606.5 |
| mmr-w100 | 3.160 | 4.448 | embed: 67.8, generate: 1639.1 |
