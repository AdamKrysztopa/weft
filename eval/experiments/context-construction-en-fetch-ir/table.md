# Evidence — context-construction-en-fetch-ir

experiment digest: cc4e90d533d3… · invocation: dcb801defdf5405b99c1b2daf9f4894a · repetitions: 2
corpus: ../../corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
paired Δ and its interval: arm minus 'baseline' on repetition 1, 95% bootstrap interval over questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
at least one spread verdict below was judged against a zero-width baseline spread: these repetitions did not vary at all, which is a claim about them, not proof the system is deterministic.

| arm | metric | baseline | arm | paired Δ | 95% CI | n | spread verdict |
|---|---|---|---|---|---|---|---|
| dedupe | recall@5 | 0.951 (n 54) | 0.951 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| dedupe | mrr@5 | 0.951 (n 54) | 0.951 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| dedupe | ndcg@5 | 0.934 (n 54) | 0.934 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| dedupe | token_recall | 0.467 (n 54) | 0.466 (n 54) | -0.000 | -0.018 to +0.017 | 54, 45 differing | within-baseline-spread |
| dedupe | rouge_l | 0.329 (n 54) | 0.328 (n 54) | -0.001 | -0.023 to +0.020 | 54, 51 differing | outside-baseline-spread |
| dedupe-t030 | recall@5 | 0.951 (n 54) | 0.951 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t030 | mrr@5 | 0.951 (n 54) | 0.951 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t030 | ndcg@5 | 0.934 (n 54) | 0.934 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t030 | token_recall | 0.467 (n 54) | 0.475 (n 54) | +0.008 | -0.008 to +0.025 | 54, 45 differing | within-baseline-spread |
| dedupe-t030 | rouge_l | 0.329 (n 54) | 0.336 (n 54) | +0.007 | -0.010 to +0.024 | 54, 52 differing | outside-baseline-spread |
| dedupe-t070 | recall@5 | 0.951 (n 54) | 0.951 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t070 | mrr@5 | 0.951 (n 54) | 0.951 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t070 | ndcg@5 | 0.934 (n 54) | 0.934 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t070 | token_recall | 0.467 (n 54) | 0.462 (n 54) | -0.004 | -0.018 to +0.012 | 54, 46 differing | within-baseline-spread |
| dedupe-t070 | rouge_l | 0.329 (n 54) | 0.331 (n 54) | +0.002 | -0.017 to +0.020 | 54, 53 differing | outside-baseline-spread |
| mmr | recall@5 | 0.951 (n 54) | 0.951 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| mmr | mrr@5 | 0.951 (n 54) | 0.954 (n 54) | +0.003 | +0.000 to +0.009 | 54, 1 differing | outside-baseline-spread (zero-width) |
| mmr | ndcg@5 | 0.934 (n 54) | 0.937 (n 54) | +0.002 | +0.000 to +0.007 | 54, 1 differing | outside-baseline-spread (zero-width) |
| mmr | token_recall | 0.467 (n 54) | 0.456 (n 54) | -0.011 | -0.034 to +0.011 | 54, 46 differing | within-baseline-spread |
| mmr | rouge_l | 0.329 (n 54) | 0.313 (n 54) | -0.016 | -0.038 to +0.006 | 54, 54 differing | outside-baseline-spread |
| mmr-w030 | recall@5 | 0.951 (n 54) | 0.951 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| mmr-w030 | mrr@5 | 0.951 (n 54) | 0.945 (n 54) | -0.006 | -0.017 to +0.000 | 54, 1 differing | outside-baseline-spread (zero-width) |
| mmr-w030 | ndcg@5 | 0.934 (n 54) | 0.930 (n 54) | -0.005 | -0.014 to +0.000 | 54, 1 differing | outside-baseline-spread (zero-width) |
| mmr-w030 | token_recall | 0.467 (n 54) | 0.437 (n 54) | -0.029 | -0.062 to +0.004 | 54, 51 differing | outside-baseline-spread |
| mmr-w030 | rouge_l | 0.329 (n 54) | 0.310 (n 54) | -0.019 | -0.046 to +0.008 | 54, 54 differing | outside-baseline-spread |
| mmr-w100 | recall@5 | 0.951 (n 54) | 0.951 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | mrr@5 | 0.951 (n 54) | 0.951 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | ndcg@5 | 0.934 (n 54) | 0.934 (n 54) | +0.000 | +0.000 to +0.000 | 54, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | token_recall | 0.467 (n 54) | 0.468 (n 54) | +0.001 | -0.016 to +0.019 | 54, 46 differing | within-baseline-spread |
| mmr-w100 | rouge_l | 0.329 (n 54) | 0.331 (n 54) | +0.002 | -0.015 to +0.019 | 54, 52 differing | outside-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 2.633 | 7.590 | embed: 36.0, generate: 1609.0 |
| dedupe | 2.934 | 6.494 | embed: 36.0, generate: 1605.3 |
| dedupe-t030 | 2.772 | 6.717 | embed: 36.0, generate: 1635.7 |
| dedupe-t070 | 2.675 | 6.054 | embed: 36.0, generate: 1590.2 |
| mmr | 3.109 | 8.994 | embed: 72.0, generate: 1597.0 |
| mmr-w030 | 3.593 | 9.482 | embed: 72.0, generate: 1691.8 |
| mmr-w100 | 3.277 | 7.165 | embed: 72.0, generate: 1601.7 |
