"""The four IR metrics — precision@k, recall@k, mean average precision, NDCG@k.

Task **4.2**, `docs/build-ledger.md`: the reference's metric suite, every recorded defect fixed at
the door. These four score a `RetrievalSample` — a ranked list of retrieved ids against a
ground-truth relevance set — and never read a passage's text, which is exactly why they are
`RetrievalMetric`s rather than `GenerationMetric`s under `weft_eval.contract`'s split.

**The `k`-in-the-name property, held where it is this task's to hold.** R5 in
`.phase4-reference-recon.md`: the reference's own `PrecisionAtK`/`RecallAtK`/`NDCG` build `metric_name`
from `self.k` correctly at the per-metric level, and the property breaks one layer up, in two
dataset-track runners that hardcode a literal `'precision_at_k'` string as a report key while the
real `k` is caller-supplied. That breakage is a *report's* defect, not this plugin's — `metric_
name` below is built from `self._config.k` exactly once, at the point of construction, so nothing
downstream can restate it wrong without reading it wrong first. Task 4.3 is what checks that a run
record's own display honours what this field already says.

**Empty relevant-id set is `NothingToProduce`, not a computed zero.** `weft_eval.contract`'s own
module docstring states the rule this suite applies uniformly: nothing to compare against is
nothing to compare against, independent of what the retrieval side carries. `MeanAveragePrecision`
has no `k` and no configuration at all — its own name promises none, so unlike the other three it
declares `config_model` as an empty frozen model rather than inventing a knob nobody asked for.
"""

import math
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_eval.contract import MetricScore, RetrievalSample
from weft_kernel.context import Context
from weft_kernel.payload import NothingToProduce, Outcome, Produced


class TopKConfig(BaseModel):
    """Shared `with:` shape for `PrecisionAtK`, `RecallAtK` and `NDCGAtK` — one tunable, `k`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: How many top-ranked results this metric considers. Required, not defaulted — an operator
    #: who does not state `k` has not chosen one, the same argument `AtThresholdConfig.threshold`
    #: already makes for its own required field.
    k: int = Field(ge=1)


class NoConfig(BaseModel):
    """The empty `with:` shape for a metric with nothing to tune — `MeanAveragePrecision`."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def _top_k_ids(payload: RetrievalSample, k: int) -> tuple[str, ...]:
    return tuple(passage.id for passage in payload.retrieved[:k])


class PrecisionAtK:
    """Of the top `k` retrieved ids, the fraction that are relevant.

    Standard textbook definition: the denominator is `k` itself, not `min(k, len(retrieved))` —
    an empty slot among the top `k` counts as a miss rather than being excused from the count,
    which is what makes precision comparable across samples with different retrieval depths.
    """

    config_model: ClassVar[type[TopKConfig]] = TopKConfig
    #: Task 4.7, Q6: pure arithmetic over ids already in the sample, no credential, no network,
    #: no model download — part of the deterministic gate subset.
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: TopKConfig) -> None:
        self._config = config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if not payload.relevant_ids:
            return NothingToProduce(reason="no relevant ids to score retrieval against")

        k = self._config.k
        hits = sum(1 for doc_id in _top_k_ids(payload, k) if doc_id in payload.relevant_ids)
        return Produced(value=MetricScore(metric_name=f"precision@{k}", value=hits / k))


class RecallAtK:
    """Of every relevant id, the fraction found somewhere in the top `k` retrieved."""

    config_model: ClassVar[type[TopKConfig]] = TopKConfig
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: TopKConfig) -> None:
        self._config = config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if not payload.relevant_ids:
            return NothingToProduce(reason="no relevant ids to score retrieval against")

        k = self._config.k
        found = sum(1 for doc_id in _top_k_ids(payload, k) if doc_id in payload.relevant_ids)
        return Produced(
            value=MetricScore(metric_name=f"recall@{k}", value=found / len(payload.relevant_ids))
        )


class MeanAveragePrecision:
    """The mean, over every relevant id found, of precision measured at its own rank.

    No `k` — the whole ranked list is considered, which is what the name promises and `PrecisionAt
    K`/`RecallAtK` deliberately do not: those two are windowed by construction, this one is not.
    """

    config_model: ClassVar[type[NoConfig]] = NoConfig
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: NoConfig | None = None) -> None:
        del config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if not payload.relevant_ids:
            return NothingToProduce(reason="no relevant ids to score retrieval against")

        hits = 0
        precision_sum = 0.0
        for rank, passage in enumerate(payload.retrieved, start=1):
            if passage.id in payload.relevant_ids:
                hits += 1
                precision_sum += hits / rank

        return Produced(
            value=MetricScore(
                metric_name="mean_average_precision",
                value=precision_sum / len(payload.relevant_ids),
            )
        )


class NDCGAtK:
    """Normalized discounted cumulative gain over the top `k`, binary relevance.

    `relevant_ids` carries no grade, so gain is 1.0 for a relevant id and 0.0 otherwise — the
    ideal ordering places every relevant id first, which is what `idcg` computes without needing
    to re-sort `payload.retrieved` itself.
    """

    config_model: ClassVar[type[TopKConfig]] = TopKConfig
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: TopKConfig) -> None:
        self._config = config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if not payload.relevant_ids:
            return NothingToProduce(reason="no relevant ids to score retrieval against")

        k = self._config.k
        dcg = sum(
            1.0 / math.log2(rank + 1)
            for rank, doc_id in enumerate(_top_k_ids(payload, k), start=1)
            if doc_id in payload.relevant_ids
        )
        ideal_hits = min(k, len(payload.relevant_ids))
        idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))

        return Produced(value=MetricScore(metric_name=f"ndcg@{k}", value=dcg / idcg))
