"""`ExactMatch` — a stranger's metric: does `prediction` equal `reference`, exactly?

Deliberately not `weft_eval.at_threshold.OverlapAtThreshold` with different numbers — a third
party has no reason to reimplement the built-in, so this one picks a genuinely different
computation to make the point that any implementation satisfying `weft_eval.contract.
GenerationMetric` structurally is usable, not only the shape the built-in happens to take.
`case_sensitive` is
this metric's own typed configuration — the identical mechanism, exercised from entirely outside
the `weft` workspace.

**`runs_in_gate`, task 4.7's Q6 — mandatory for a stranger exactly as it is for a built-in.**
`GenerationMetric.required_declarations = ("runs_in_gate",)` refuses registration for any class
that never states it, first-party or not; a plain string comparison over the sample already in
hand needs no credential, no network and no model download, so this one declares `True`.
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_eval.contract import GenerationSample, MetricScore
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced


class ExactMatchConfig(BaseModel):
    """`ExactMatch`'s `with:` configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_sensitive: bool = True


class ExactMatch:
    """Satisfies `weft_eval.contract.GenerationMetric` structurally — this class never imports
    it."""

    config_model: type[ExactMatchConfig] = ExactMatchConfig
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: ExactMatchConfig | None = None) -> None:
        self._config = config if config is not None else ExactMatchConfig()

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx  # no service or locale this metric needs
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        if not payload.reference:
            return NothingToProduce(reason="reference is empty — nothing to match against")

        prediction, reference = payload.prediction, payload.reference
        if not self._config.case_sensitive:
            prediction, reference = prediction.lower(), reference.lower()

        return Produced(
            value=MetricScore(
                metric_name="example_exact_match", value=1.0 if prediction == reference else 0.0
            )
        )
