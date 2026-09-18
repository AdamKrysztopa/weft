# Evidence — context-construction-en-operator-ir

experiment digest: f71544fda41f… · invocation: f911ae886554442a86874417e42affa0 · repetitions: 2
corpus: ../../corpus/validation-en (fa62239f0e1a…)
minimum detectable effect: 0.08
paired Δ and its interval: arm minus 'baseline' on repetition 1, 95% bootstrap interval over questions
spread verdict: that Δ against the between-repetition spread of arm 'baseline'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
at least one spread verdict below was judged against a zero-width baseline spread: these repetitions did not vary at all, which is a claim about them, not proof the system is deterministic.

| arm | metric | baseline | arm | paired Δ | 95% CI | n | spread verdict |
|---|---|---|---|---|---|---|---|
| dedupe | recall@5 | 0.903 (n 53) | 0.903 (n 53) | +0.000 | +0.000 to +0.000 | 53, 0 differing | within-baseline-spread (zero-width) |
| dedupe | mrr@5 | 0.833 (n 53) | 0.830 (n 53) | -0.003 | -0.009 to +0.000 | 53, 1 differing | outside-baseline-spread (zero-width) |
| dedupe | ndcg@5 | 0.838 (n 53) | 0.836 (n 53) | -0.002 | -0.007 to +0.000 | 53, 1 differing | outside-baseline-spread (zero-width) |
| dedupe | token_recall | 0.516 (n 53) | 0.523 (n 53) | +0.006 | -0.011 to +0.024 | 53, 43 differing | within-baseline-spread |
| dedupe | rouge_l | 0.333 (n 53) | 0.335 (n 53) | +0.002 | -0.014 to +0.019 | 53, 50 differing | outside-baseline-spread |
| dedupe-t030 | recall@5 | 0.903 (n 53) | 0.921 (n 53) | +0.019 | +0.000 to +0.057 | 53, 1 differing | outside-baseline-spread (zero-width) |
| dedupe-t030 | mrr@5 | 0.833 (n 53) | 0.836 (n 53) | +0.003 | -0.009 to +0.019 | 53, 2 differing | outside-baseline-spread (zero-width) |
| dedupe-t030 | ndcg@5 | 0.838 (n 53) | 0.845 (n 53) | +0.007 | -0.007 to +0.028 | 53, 2 differing | outside-baseline-spread (zero-width) |
| dedupe-t030 | token_recall | 0.516 (n 53) | 0.530 (n 53) | +0.013 | -0.002 to +0.030 | 53, 40 differing | outside-baseline-spread |
| dedupe-t030 | rouge_l | 0.333 (n 53) | 0.333 (n 53) | +0.000 | -0.016 to +0.015 | 53, 50 differing | within-baseline-spread |
| dedupe-t070 | recall@5 | 0.903 (n 53) | 0.903 (n 53) | +0.000 | +0.000 to +0.000 | 53, 0 differing | within-baseline-spread (zero-width) |
| dedupe-t070 | mrr@5 | 0.833 (n 53) | 0.830 (n 53) | -0.003 | -0.009 to +0.000 | 53, 1 differing | outside-baseline-spread (zero-width) |
| dedupe-t070 | ndcg@5 | 0.838 (n 53) | 0.836 (n 53) | -0.002 | -0.007 to +0.000 | 53, 1 differing | outside-baseline-spread (zero-width) |
| dedupe-t070 | token_recall | 0.516 (n 53) | 0.522 (n 53) | +0.006 | -0.011 to +0.024 | 53, 40 differing | within-baseline-spread |
| dedupe-t070 | rouge_l | 0.333 (n 53) | 0.334 (n 53) | +0.001 | -0.011 to +0.015 | 53, 51 differing | within-baseline-spread |
| mmr | recall@5 | 0.903 (n 53) | 0.984 (n 53) | +0.082 | +0.025 to +0.157 | 53, 6 differing | outside-baseline-spread (zero-width) |
| mmr | mrr@5 | 0.833 (n 53) | 0.874 (n 53) | +0.041 | +0.013 to +0.075 | 53, 7 differing | outside-baseline-spread (zero-width) |
| mmr | ndcg@5 | 0.838 (n 53) | 0.894 (n 53) | +0.056 | +0.018 to +0.100 | 53, 8 differing | outside-baseline-spread (zero-width) |
| mmr | token_recall | 0.516 (n 53) | 0.530 (n 53) | +0.014 | -0.009 to +0.037 | 53, 44 differing | outside-baseline-spread |
| mmr | rouge_l | 0.333 (n 53) | 0.349 (n 53) | +0.016 | -0.005 to +0.038 | 53, 52 differing | outside-baseline-spread |
| mmr-w030 | recall@5 | 0.903 (n 53) | 0.965 (n 53) | +0.063 | +0.012 to +0.132 | 53, 4 differing | outside-baseline-spread (zero-width) |
| mmr-w030 | mrr@5 | 0.833 (n 53) | 0.872 (n 53) | +0.038 | +0.013 to +0.071 | 53, 7 differing | outside-baseline-spread (zero-width) |
| mmr-w030 | ndcg@5 | 0.838 (n 53) | 0.882 (n 53) | +0.044 | +0.011 to +0.085 | 53, 8 differing | outside-baseline-spread (zero-width) |
| mmr-w030 | token_recall | 0.516 (n 53) | 0.483 (n 53) | -0.034 | -0.062 to -0.007 | 53, 43 differing | outside-baseline-spread |
| mmr-w030 | rouge_l | 0.333 (n 53) | 0.316 (n 53) | -0.017 | -0.043 to +0.009 | 53, 50 differing | outside-baseline-spread |
| mmr-w100 | recall@5 | 0.903 (n 53) | 0.903 (n 53) | +0.000 | +0.000 to +0.000 | 53, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | mrr@5 | 0.833 (n 53) | 0.833 (n 53) | +0.000 | +0.000 to +0.000 | 53, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | ndcg@5 | 0.838 (n 53) | 0.838 (n 53) | +0.000 | +0.000 to +0.000 | 53, 0 differing | within-baseline-spread (zero-width) |
| mmr-w100 | token_recall | 0.516 (n 53) | 0.507 (n 53) | -0.009 | -0.031 to +0.010 | 53, 42 differing | within-baseline-spread |
| mmr-w100 | rouge_l | 0.333 (n 53) | 0.336 (n 53) | +0.003 | -0.013 to +0.017 | 53, 51 differing | outside-baseline-spread |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| baseline | 2.477 | 5.919 | embed: 29.0, generate: 1466.0 |
| dedupe | 2.713 | 6.130 | embed: 29.0, generate: 1474.2 |
| dedupe-t030 | 2.580 | 7.399 | embed: 29.0, generate: 1485.2 |
| dedupe-t070 | 2.574 | 5.783 | embed: 29.0, generate: 1466.4 |
| mmr | 2.858 | 5.393 | embed: 58.0, generate: 1441.5 |
| mmr-w030 | 3.018 | 5.704 | embed: 58.0, generate: 1486.5 |
| mmr-w100 | 2.991 | 6.252 | embed: 58.0, generate: 1457.1 |
