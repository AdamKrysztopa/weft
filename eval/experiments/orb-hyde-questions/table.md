# Evidence — orb-hyde-questions

experiment digest: 7912b74644f1… · invocation: cbd9fc318b1e4d2eb11b95d346ee4b07 · repetitions: 3
corpus: ../../corpus/open-ragbench-cited-300 (e8bbb05a8955…)
minimum detectable effect: 0.05
interval and paired Δ: arm minus 'plain', pooled over the repetitions both ran, each paired with the same repetition of 'plain'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'plain'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
at least one spread verdict below was judged against a zero-width baseline spread: these repetitions did not vary at all, which is a claim about them, not proof the system is deterministic.

| arm | metric | plain | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| hyde | recall@5 | 0.997 (n 300) | 0.993 (n 300) | -0.003 to +0.000 | -0.001 | 900, 1 differing | outside-baseline-spread (zero-width) |
| hyde | mrr@5 | 0.988 (n 300) | 0.983 (n 300) | -0.015 to +0.002 | -0.006 | 900, 19 differing | outside-baseline-spread (zero-width) |
| hyde | ndcg@5 | 0.990 (n 300) | 0.986 (n 300) | -0.012 to +0.001 | -0.005 | 900, 19 differing | outside-baseline-spread (zero-width) |
| questions | recall@5 | 0.997 (n 300) | 1.000 (n 300) | +0.000 to +0.010 | +0.003 | 900, 3 differing | outside-baseline-spread (zero-width) |
| questions | mrr@5 | 0.988 (n 300) | 0.983 (n 300) | -0.016 to +0.006 | -0.005 | 900, 30 differing | outside-baseline-spread (zero-width) |
| questions | ndcg@5 | 0.990 (n 300) | 0.987 (n 300) | -0.012 to +0.006 | -0.003 | 900, 30 differing | outside-baseline-spread (zero-width) |
| questions-hyde | recall@5 | 0.997 (n 300) | 1.000 (n 299, 1 excluded) | -0.003 to +0.010 | +0.002 | 899, 4 differing | outside-baseline-spread (zero-width) |
| questions-hyde | mrr@5 | 0.988 (n 300) | 0.983 (n 299, 1 excluded) | -0.020 to +0.001 | -0.009 | 899, 34 differing | outside-baseline-spread (zero-width) |
| questions-hyde | ndcg@5 | 0.990 (n 300) | 0.987 (n 299, 1 excluded) | -0.015 to +0.002 | -0.006 | 899, 34 differing | outside-baseline-spread (zero-width) |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| plain | 0.239 | 0.326 | embed: 15.7 |
| hyde | 3.411 | 5.996 | embed: 151.1, hyde: 614.1 |
| questions | 0.261 | 0.347 | embed: 15.7 |
| questions-hyde | 3.277 | 6.072 | embed: 150.9, hyde: 616.2 |
