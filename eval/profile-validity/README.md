# E5 — profile feature validity
## musique-control

| feature | label | train precision | train recall | held-out precision | held-out recall | routable |
| --- | --- | --- | --- | --- | --- | --- |
| query.cue.aggregation | multi-hop (142 train / 158 held-out) | 1.000 (≥ 0.510) | 0.028 | 1.000 (≥ 0.646) | 0.044 | no |
| query.cue.aggregation | single-hop (161 train / 139 held-out) | 0.000 (≥ 0.000) | 0.000 | 0.000 (≥ 0.000) | 0.000 | no |
| query.cue.comparison | multi-hop (142 train / 158 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.comparison | single-hop (161 train / 139 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.cross-document | multi-hop (142 train / 158 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.cross-document | single-hop (161 train / 139 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.global | multi-hop (142 train / 158 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.global | single-hop (161 train / 139 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.temporal | multi-hop (142 train / 158 held-out) | 0.909 (≥ 0.722) | 0.141 | 1.000 (≥ 0.796) | 0.095 | no |
| query.cue.temporal | single-hop (161 train / 139 held-out) | 0.091 (≥ 0.025) | 0.012 | 0.000 (≥ -0.000) | 0.000 | no |
| query.locale_fallback | multi-hop (142 train / 158 held-out) | — | 0.000 | — | 0.000 | no |
| query.locale_fallback | single-hop (161 train / 139 held-out) | — | 0.000 | — | 0.000 | no |

## musique-hops

| feature | label | train precision | train recall | held-out precision | held-out recall | routable |
| --- | --- | --- | --- | --- | --- | --- |
| query.cue.aggregation | 1 (161 train / 139 held-out) | 0.000 (≥ 0.000) | 0.000 | 0.000 (≥ 0.000) | 0.000 | no |
| query.cue.aggregation | 2 (52 train / 48 held-out) | 0.750 (≥ 0.301) | 0.058 | 0.429 (≥ 0.158) | 0.062 | no |
| query.cue.aggregation | 3 (41 train / 59 held-out) | 0.250 (≥ 0.046) | 0.024 | 0.429 (≥ 0.158) | 0.051 | no |
| query.cue.aggregation | 4 (49 train / 51 held-out) | 0.000 (≥ 0.000) | 0.000 | 0.143 (≥ 0.026) | 0.020 | no |
| query.cue.comparison | 1 (161 train / 139 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.comparison | 2 (52 train / 48 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.comparison | 3 (41 train / 59 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.comparison | 4 (49 train / 51 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.cross-document | 1 (161 train / 139 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.cross-document | 2 (52 train / 48 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.cross-document | 3 (41 train / 59 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.cross-document | 4 (49 train / 51 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.global | 1 (161 train / 139 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.global | 2 (52 train / 48 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.global | 3 (41 train / 59 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.global | 4 (49 train / 51 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.temporal | 1 (161 train / 139 held-out) | 0.091 (≥ 0.025) | 0.012 | 0.000 (≥ -0.000) | 0.000 | no |
| query.cue.temporal | 2 (52 train / 48 held-out) | 0.091 (≥ 0.025) | 0.038 | 0.133 (≥ 0.037) | 0.042 | no |
| query.cue.temporal | 3 (41 train / 59 held-out) | 0.136 (≥ 0.047) | 0.073 | 0.400 (≥ 0.198) | 0.102 | no |
| query.cue.temporal | 4 (49 train / 51 held-out) | 0.682 (≥ 0.473) | 0.306 | 0.467 (≥ 0.248) | 0.137 | no |
| query.locale_fallback | 1 (161 train / 139 held-out) | — | 0.000 | — | 0.000 | no |
| query.locale_fallback | 2 (52 train / 48 held-out) | — | 0.000 | — | 0.000 | no |
| query.locale_fallback | 3 (41 train / 59 held-out) | — | 0.000 | — | 0.000 | no |
| query.locale_fallback | 4 (49 train / 51 held-out) | — | 0.000 | — | 0.000 | no |

## qasper-answer-type

| feature | label | train precision | train recall | held-out precision | held-out recall | routable |
| --- | --- | --- | --- | --- | --- | --- |
| query.cue.aggregation | abstractive (134 train / 130 held-out) | 0.429 (≥ 0.214) | 0.045 | 0.200 (≥ 0.070) | 0.023 | no |
| query.cue.aggregation | boolean (49 train / 67 held-out) | 0.000 (≥ 0.000) | 0.000 | 0.000 (≥ -0.000) | 0.000 | no |
| query.cue.aggregation | extractive (241 train / 289 held-out) | 0.571 (≥ 0.326) | 0.033 | 0.800 (≥ 0.548) | 0.042 | no |
| query.cue.comparison | abstractive (134 train / 130 held-out) | 0.364 (≥ 0.152) | 0.030 | 0.231 (≥ 0.082) | 0.023 | no |
| query.cue.comparison | boolean (49 train / 67 held-out) | 0.000 (≥ 0.000) | 0.000 | 0.231 (≥ 0.082) | 0.045 | no |
| query.cue.comparison | extractive (241 train / 289 held-out) | 0.636 (≥ 0.354) | 0.029 | 0.538 (≥ 0.291) | 0.024 | no |
| query.cue.cross-document | abstractive (134 train / 130 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.cross-document | boolean (49 train / 67 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.cross-document | extractive (241 train / 289 held-out) | — | 0.000 | — | 0.000 | no |
| query.cue.global | abstractive (134 train / 130 held-out) | 0.000 (≥ 0.000) | 0.000 | 0.000 (≥ 0.000) | 0.000 | no |
| query.cue.global | boolean (49 train / 67 held-out) | 1.000 (≥ 0.342) | 0.041 | 0.000 (≥ 0.000) | 0.000 | no |
| query.cue.global | extractive (241 train / 289 held-out) | 0.000 (≥ 0.000) | 0.000 | 1.000 (≥ 0.207) | 0.003 | no |
| query.cue.temporal | abstractive (134 train / 130 held-out) | 0.200 (≥ 0.036) | 0.007 | 0.000 (≥ 0.000) | 0.000 | no |
| query.cue.temporal | boolean (49 train / 67 held-out) | 0.400 (≥ 0.118) | 0.041 | 0.000 (≥ 0.000) | 0.000 | no |
| query.cue.temporal | extractive (241 train / 289 held-out) | 0.400 (≥ 0.118) | 0.008 | 1.000 (≥ 0.342) | 0.007 | no |
| query.locale_fallback | abstractive (134 train / 130 held-out) | — | 0.000 | — | 0.000 | no |
| query.locale_fallback | boolean (49 train / 67 held-out) | — | 0.000 | — | 0.000 | no |
| query.locale_fallback | extractive (241 train / 289 held-out) | — | 0.000 | — | 0.000 | no |

