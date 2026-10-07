# Evidence — local-embed-orb

experiment digest: 8a0eb3dfdcb2… · invocation: a2e269c777e24cdbb1d0d12c1bfc44c7 · repetitions: bge-m3 1, openai-large 1
corpus: ../../corpus/open-ragbench (1c4856181b61…)
minimum detectable effect: 0.04
interval and paired Δ: arm minus 'bge-m3', pooled over the repetitions both ran, each paired with the same repetition of 'bge-m3'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'bge-m3'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'mrr@5', higher-is-better, margin 0.04 — the verdict column reads the paired interval against it

| arm | metric | bge-m3 | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| openai-large | mrr@5 | 0.934 (n 1548) | 0.952 (n 1548) | +0.007 to +0.029 | +0.018 | 1548, 194 differing | unjudgeable | benefit-ruled-out |
| openai-large | recall@5 | 0.977 (n 1548) | 0.989 (n 1548) | +0.005 to +0.019 | +0.012 | 1548, 35 differing | unjudgeable | — |
| openai-large | ndcg@5 | 0.945 (n 1548) | 0.961 (n 1548) | +0.007 to +0.025 | +0.016 | 1548, 194 differing | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| bge-m3 | 0.526 | 0.567 | embed: 19.3 |
| openai-large | 1.064 | 1.173 | embed: 15.8 |
