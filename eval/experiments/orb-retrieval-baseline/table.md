# Evidence — orb-retrieval-baseline

experiment digest: c2d4f62983d3… · invocation: 7017a15bea924619a66024d24b532b7d · repetitions: 3
minimum detectable effect: 0.03
paired Δ and its interval: arm minus 'dense' on repetition 1, 95% bootstrap interval over questions
spread verdict: that Δ against the between-repetition spread of arm 'dense'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
at least one spread verdict below was judged against a zero-width baseline spread: these repetitions did not vary at all, which is a claim about them, not proof the system is deterministic.

| arm | metric | dense | arm | paired Δ | 95% CI | n | spread verdict |
|---|---|---|---|---|---|---|---|
| lexical | recall@5 | 0.986 | 0.244 | -0.742 | -0.764 to -0.721 | 1548 | outside-baseline-spread (zero-width) |
| lexical | mrr@5 | 0.949 | 0.153 | -0.796 | -0.812 to -0.779 | 1548 | outside-baseline-spread (zero-width) |
| lexical | ndcg@5 | 0.958 | 0.176 | -0.783 | -0.801 to -0.765 | 1548 | outside-baseline-spread (zero-width) |
| hybrid | recall@5 | 0.986 | 0.983 | -0.003 | -0.006 to -0.001 | 1548 | outside-baseline-spread (zero-width) |
| hybrid | mrr@5 | 0.949 | 0.928 | -0.021 | -0.028 to -0.014 | 1548 | outside-baseline-spread (zero-width) |
| hybrid | ndcg@5 | 0.958 | 0.942 | -0.016 | -0.022 to -0.011 | 1548 | outside-baseline-spread (zero-width) |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| dense | 0.327 | 0.453 | embed: 15.8 |
| lexical | 0.446 | 0.704 | — |
| hybrid | 0.711 | 1.000 | embed: 15.8 |
