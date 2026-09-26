# Evidence — orb-retrieval-baseline

experiment digest: c2d4f62983d3… · invocation: 7017a15bea924619a66024d24b532b7d · repetitions: 3
corpus: ../../corpus/open-ragbench (1c4856181b61…)
minimum detectable effect: 0.03
interval and paired Δ: arm minus 'dense' on repetition 1, 95% bootstrap interval over questions
spread verdict: that Δ against the between-repetition spread of arm 'dense'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
at least one spread verdict below was judged against a zero-width baseline spread: these repetitions did not vary at all, which is a claim about them, not proof the system is deterministic.

| arm | metric | dense | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| lexical | recall@5 | 0.986 (n 1548) | 0.244 (n 1548) | -0.764 to -0.721 | -0.742 | 1548, 1151 differing | outside-baseline-spread (zero-width) |
| lexical | mrr@5 | 0.949 (n 1548) | 0.153 (n 1548) | -0.812 to -0.779 | -0.796 | 1548, 1366 differing | outside-baseline-spread (zero-width) |
| lexical | ndcg@5 | 0.958 (n 1548) | 0.176 (n 1548) | -0.801 to -0.765 | -0.783 | 1548, 1366 differing | outside-baseline-spread (zero-width) |
| hybrid | recall@5 | 0.986 (n 1548) | 0.983 (n 1548) | -0.006 to -0.001 | -0.003 | 1548, 5 differing | outside-baseline-spread (zero-width) |
| hybrid | mrr@5 | 0.949 (n 1548) | 0.928 (n 1548) | -0.028 to -0.014 | -0.021 | 1548, 119 differing | outside-baseline-spread (zero-width) |
| hybrid | ndcg@5 | 0.958 (n 1548) | 0.942 (n 1548) | -0.022 to -0.011 | -0.016 | 1548, 119 differing | outside-baseline-spread (zero-width) |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| dense | 0.327 | 0.453 | embed: 15.8 |
| lexical | 0.446 | 0.704 | — |
| hybrid | 0.711 | 1.000 | embed: 15.8 |
