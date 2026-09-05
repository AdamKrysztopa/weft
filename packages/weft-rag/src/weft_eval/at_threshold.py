"""`OverlapAtThreshold` — the one demonstration metric task 4.1 ships.

Not one of the 21 catalogued metrics; `docs/build-ledger.md` task 4.2 owns that suite, "every
recorded defect fixed at the door rather than inherited." This one exists to make requirement
6's second clause real — "the same metric runs twice at two thresholds because its registration
carries a typed configuration model" — with a computation simple enough that the demonstration is
about the *contract mechanism*, not about the metric's own merit: no model download, no network
call, no credential, so it runs in `poe ci-checks` on a clean checkout the same way `weft-embed`'s
`hash` embedder does.

**What it measures, honestly stated.** Token overlap between `prediction` and `reference`, as a
fraction of `reference`'s own tokens, thresholded to a hit/miss — deliberately not `token_overlap`
or `token_recall`, the registered names task 4.2's own suite uses for a similar computation, so
nothing here is mistaken for one of the 21 arriving pre-fixed at task 4.2. This metric's own
empty-reference edge case is handled by returning `NothingToProduce` rather than an unconditional
`1.0` (`docs/09-release.md` §4.2) — the fix V4 asks for, demonstrated once here rather than
deferred to the metric that actually carries that name and the defect to fix.

**Updated for task 4.2's contract split** (`weft_eval.contract`'s own module docstring): `Sample`
is now `GenerationSample` and `Metric` is now `GenerationMetric` — this plugin's own shape (a
prediction scored against a reference) is exactly the generation half of that split, unchanged in
every other respect.
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_eval.contract import GenerationSample, MetricScore
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced


class AtThresholdConfig(BaseModel):
    """`OverlapAtThreshold`'s `with:` configuration — the typed model requirement 6 asks for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The minimum overlap fraction that counts as a hit. Required, not defaulted: a threshold
    #: silently defaulted is a threshold nobody chose, which is the accident a typed
    #: configuration model exists to make a caller state rather than inherit.
    threshold: float = Field(ge=0.0, le=1.0)


class OverlapAtThreshold:
    """Registered once as `"overlap-at-threshold"`; constructed twice, at two thresholds.

    Satisfies `weft_eval.contract.GenerationMetric` structurally — this class never imports it,
    the same path `docs/02-extension-model.md` describes for a third-party plugin. A stranger's
    own metric proves the identical structural conformance from entirely outside this workspace
    (fitness function 9(c)).
    """

    config_model: ClassVar[type[AtThresholdConfig]] = AtThresholdConfig
    #: Task 4.7, Q6: token overlap over strings already in the sample — no credential, no
    #: network, no model download.
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: AtThresholdConfig) -> None:
        self._config = config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx  # no service or locale this metric needs
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")

        reference_tokens = frozenset(payload.reference.split())
        if not reference_tokens:
            return NothingToProduce(reason="reference carries no tokens to compare against")

        prediction_tokens = frozenset(payload.prediction.split())
        overlap = len(reference_tokens & prediction_tokens) / len(reference_tokens)
        hit = 1.0 if overlap >= self._config.threshold else 0.0

        return Produced(
            value=MetricScore(
                metric_name=f"overlap_at_threshold@{self._config.threshold:g}", value=hit
            )
        )
