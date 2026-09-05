"""QA-shaped generation metrics — `exact-match`, `f1-score`, `accuracy`.

Task **4.2**. Three of the eleven traditional generation metrics, all string- or token-level
comparisons with no external dependency.

**Why `accuracy` is not a second `exact-match`.** Registering two plugins that compute the
identical thing under different names would be a false name — `10`'s own naming rule 4: "never
take a name that promises more than the code does," read the other way round, a name that
promises *less* difference than there is would be just as dishonest to omit. `exact-match` is
strict normalized-string equality; `accuracy` is the looser, common QA convention — did the
correct answer appear in the response at all, substring-contained rather than requiring the whole
response to *be* the answer. A prediction that answers in a full sentence around a correct short
answer fails `exact-match` and passes `accuracy`, and that is the entire point of shipping both.

**Two "trailing" edge cases, deliberately flattened into one rule rather than left
inconsistent.** A recall-shaped metric returning `1.0` unconditionally on an empty reference, and
an F1-shaped metric returning `1.0` only when the *prediction* is also empty, are two different
shapes for what reads as one defect. Weft does not preserve that difference: every metric in this
suite treats an empty reference as
`NothingToProduce`, full stop, regardless of what the prediction holds. A caller asking "did the
prediction and reference agree on being empty" is asking a different, legitimate question, and
`exact-match` already answers it honestly — an empty prediction against an empty reference is a
real exact match, `1.0`, because both sides of *that* comparison are present and equal.
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_eval.contract import GenerationSample, MetricScore
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced


class NoConfig(BaseModel):
    """The empty `with:` shape shared by every metric in this file — none of them take one."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


class ExactMatch:
    """Whether `prediction` and `reference` agree exactly, after whitespace/case normalization.

    The one metric in this suite that scores an empty reference: an empty prediction against an
    empty reference is a genuine exact match, not a "nothing to compare" case — both sides of the
    comparison are present, they are simply both the empty string.
    """

    config_model: ClassVar[type[NoConfig]] = NoConfig
    #: Task 4.7, Q6: normalized string comparison over the sample's own strings.
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: NoConfig | None = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")

        matched = _normalize(payload.prediction) == _normalize(payload.reference)
        return Produced(value=MetricScore(metric_name="exact_match", value=1.0 if matched else 0.0))


class F1Score:
    """Token-level F1 between `prediction` and `reference` — the SQuAD-style span-overlap score."""

    config_model: ClassVar[type[NoConfig]] = NoConfig
    #: Task 4.7, Q6: normalized string comparison over the sample's own strings.
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: NoConfig | None = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        reference_tokens = _normalize(payload.reference).split()
        if not reference_tokens:
            return NothingToProduce(reason="reference carries no tokens to compare against")

        prediction_tokens = _normalize(payload.prediction).split()
        if not prediction_tokens:
            return Produced(value=MetricScore(metric_name="f1_score", value=0.0))

        overlap = 0
        remaining = list(reference_tokens)
        for token in prediction_tokens:
            if token in remaining:
                remaining.remove(token)
                overlap += 1
        if overlap == 0:
            return Produced(value=MetricScore(metric_name="f1_score", value=0.0))

        precision = overlap / len(prediction_tokens)
        recall = overlap / len(reference_tokens)
        f1 = 2 * precision * recall / (precision + recall)
        return Produced(value=MetricScore(metric_name="f1_score", value=f1))


class Accuracy:
    """Whether `reference` appears, verbatim, somewhere inside `prediction` — the loose QA check.

    Distinct from `exact-match`: a prediction that wraps the correct answer in a full sentence
    scores `1.0` here and `0.0` there. Both directions normalized (case, whitespace) the same way
    `exact-match` normalizes both sides.
    """

    config_model: ClassVar[type[NoConfig]] = NoConfig
    #: Task 4.7, Q6: normalized string comparison over the sample's own strings.
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: NoConfig | None = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        reference = _normalize(payload.reference)
        if not reference:
            return NothingToProduce(reason="reference is empty — nothing to compare against")

        contained = reference in _normalize(payload.prediction)
        return Produced(value=MetricScore(metric_name="accuracy", value=1.0 if contained else 0.0))
