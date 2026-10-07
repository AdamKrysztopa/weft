# Evidence — local-embed-techqa

experiment digest: 5f368d30124b… · invocation: e130f5a84c70449784653e1f669de0f3 · repetitions: bge-m3 1, openai-large 1
corpus: ../../corpus/techqa (edd4c17801e7…)
minimum detectable effect: 0.04
interval and paired Δ: arm minus 'bge-m3', pooled over the repetitions both ran, each paired with the same repetition of 'bge-m3'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'bge-m3'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.
pre-registered decision: 'mrr@5', higher-is-better, margin 0.04 — the verdict column reads the paired interval against it

| arm | metric | bge-m3 | arm | 95% CI | paired Δ | n | spread verdict | verdict |
|---|---|---|---|---|---|---|---|---|
| openai-large | mrr@5 | 0.526 (n 610) | 0.611 (n 610) | +0.059 to +0.112 | +0.085 | 610, 193 differing | unjudgeable | worthwhile |
| openai-large | recall@5 | 0.657 (n 610) | 0.720 (n 610) | +0.033 to +0.092 | +0.062 | 610, 88 differing | unjudgeable | — |
| openai-large | ndcg@5 | 0.559 (n 610) | 0.638 (n 610) | +0.053 to +0.104 | +0.079 | 610, 193 differing | unjudgeable | — |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| bge-m3 | 0.652 | 0.719 | embed: 92.1 |
| openai-large | 1.338 | 1.480 | embed: 83.5 |
