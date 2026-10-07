# Evidence — local-embed-esci

experiment digest: abe5c8a72026… · invocation: 5378b3bc79424ecba52c3d826a3704ac · repetitions: bge-m3 1, openai-large 1
corpus: ../../corpus/esci (b389cca6598a…)
minimum detectable effect: 0.04
interval and paired Δ: arm minus 'bge-m3', pooled over the repetitions both ran, each paired with the same repetition of 'bge-m3'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'bge-m3'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'mrr@5', higher-is-better, margin 0.04 — the verdict column reads the paired interval against it

| arm | metric | bge-m3 | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| openai-large | mrr@5 | 0.728 (n 830) | 0.837 (n 830) | +0.087 to +0.132 | +0.109 | 830, 296 differing | unjudgeable | worthwhile |
| openai-large | recall@5 | 0.330 (n 830) | 0.398 (n 830) | +0.054 to +0.082 | +0.068 | 830, 452 differing | unjudgeable | — |
| openai-large | ndcg@5 | 0.614 (n 830) | 0.737 (n 830) | +0.105 to +0.141 | +0.122 | 830, 583 differing | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| bge-m3 | 0.220 | 0.241 | embed: 5.8 |
| openai-large | 0.833 | 0.912 | embed: 5.5 |
