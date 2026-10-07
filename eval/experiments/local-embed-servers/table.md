# Evidence — local-embed-servers

experiment digest: 7edb4f2bf5f1… · invocation: 7dd37b5d7e8143baa936def7329f42a0 · repetitions: ollama 1, tei 1
corpus: ../../corpus/techqa (edd4c17801e7…)
minimum detectable effect: 0.02
interval and paired Δ: arm minus 'ollama', pooled over the repetitions both ran, each paired with the same repetition of 'ollama'; 95% bootstrap interval resampling questions
spread verdict: that Δ against the between-repetition spread of arm 'ollama'
the minimum detectable effect is not applied to either verdict above: the paired difference's bootstrap interval and the spread verdict each read only the record's own numbers, never a chosen threshold.

| arm | metric | ollama | arm | 95% CI | paired Δ | n | spread verdict |
|---|---|---|---|---|---|---|---|
| tei | mrr@5 | 0.526 (n 610) | 0.528 (n 610) | -0.001 to +0.005 | +0.002 | 610, 7 differing | unjudgeable |
| tei | recall@5 | 0.657 (n 610) | 0.657 (n 610) | -0.005 to +0.005 | +0.000 | 610, 2 differing | unjudgeable |
| tei | ndcg@5 | 0.559 (n 610) | 0.560 (n 610) | -0.001 to +0.005 | +0.001 | 610, 7 differing | unjudgeable |

| arm | latency p50 (s) | latency p95 (s) | tokens per query |
|---|---|---|---|
| ollama | 0.792 | 0.907 | embed: 92.1 |
| tei | 0.673 | 0.782 | embed: 94.1 |
