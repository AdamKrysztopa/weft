"""Token-overlap metrics — `token-overlap`, `token-recall`, `key-terms-precision` — and ROUGE.

Task **4.2**. Six of the eleven traditional generation metrics: three plain token-set
computations with no external dependency, and the three ROUGE variants, which do carry one —
`rouge-score` — on `docs/04-reference-inventory.md`'s own instruction: the reference's `rouge_l` was a
hand-rolled, pure-Python O(m·n) longest-common-subsequence table, a performance liability the
correction block names for replacement rather than porting. `rouge-score` is Google Research's own
reference implementation, pure Python, no model download and no network call at runtime — `use_
stemmer=False` (the default this module keeps) never reaches for NLTK's downloaded corpora, only
its bundled, data-free Porter stemmer code path, so nothing here breaks `poe ci-checks` on a clean
checkout with no account and no cached model.

**Empty reference is `NothingToProduce`, everywhere in this file, unconditionally.**
`weft_eval.contract`'s own rule: nothing to compare against is nothing to compare against, no
matter what the prediction holds. This is where the reference's own `token_recall` defect
(`lexical_metrics.py:291`, an unconditional `1.0` on an empty reference) is fixed at the door — and
fixed identically for `key-terms-precision` and every ROUGE variant, which the reference never
special-cased for an empty reference at all (an empty reference against `rouge-score` computes a
real but meaningless `0.0`, indistinguishable from "the prediction shares nothing with a real,
non-empty reference" — precisely the accident `NothingToProduce` exists to name).
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict
from rouge_score import rouge_scorer

from weft_eval.contract import GenerationSample, MetricScore
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced

#: A short, closed stop-word list for `KeyTermsPrecision`'s content-word heuristic — not an
#: attempt at linguistic completeness, only enough to keep function words from counting as
#: "key" terms. English only, matching every other first-party prompt/heuristic's own fallback
#: locale (`weft_prompts.typed_prompt.FALLBACK_LOCALE`).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "by",
        "as",
        "it",
        "this",
        "that",
        "these",
        "those",
        "from",
        "into",
        "than",
        "then",
    }
)


class NoConfig(BaseModel):
    """The empty `with:` shape shared by every metric in this file — none of them take one."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def _tokens(text: str) -> frozenset[str]:
    return frozenset(text.lower().split())


class TokenOverlap:
    """Jaccard similarity between `prediction` and `reference`'s own token sets.

    Deliberately not a recall — `token-recall` is that; this one is symmetric, penalising a
    prediction that pads the reference's tokens with unrelated ones exactly as much as one that
    omits reference tokens.
    """

    config_model: ClassVar[type[NoConfig]] = NoConfig
    #: Task 4.7, Q6: token-set arithmetic over strings already in the sample.
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: NoConfig | None = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        reference_tokens = _tokens(payload.reference)
        if not reference_tokens:
            return NothingToProduce(reason="reference carries no tokens to compare against")

        prediction_tokens = _tokens(payload.prediction)
        union = reference_tokens | prediction_tokens
        overlap = len(reference_tokens & prediction_tokens) / len(union) if union else 0.0
        return Produced(value=MetricScore(metric_name="token_overlap", value=overlap))


class TokenRecall:
    """Fraction of `reference`'s own tokens that also appear in `prediction`.

    The reference's `token_recall` returned `1.0` unconditionally on an empty reference
    (`lexical_metrics.py:291`) — fixed here by the module-wide rule: empty reference is `Nothing
    ToProduce`, never a computed number.
    """

    config_model: ClassVar[type[NoConfig]] = NoConfig
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: NoConfig | None = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        reference_tokens = _tokens(payload.reference)
        if not reference_tokens:
            return NothingToProduce(reason="reference carries no tokens to compare against")

        prediction_tokens = _tokens(payload.prediction)
        recall = len(reference_tokens & prediction_tokens) / len(reference_tokens)
        return Produced(value=MetricScore(metric_name="token_recall", value=recall))


class KeyTermsPrecision:
    """Of `prediction`'s own tokens, the fraction that are one of `reference`'s content words.

    "Key terms" is a stop-word-filtered heuristic over `reference`'s own tokens — content words,
    never a claim about named-entity or keyphrase extraction. Precision, not recall: this asks
    how much of what the prediction said was actually load-bearing in the reference, not how much
    of the reference the prediction managed to restate.
    """

    config_model: ClassVar[type[NoConfig]] = NoConfig
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: NoConfig | None = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        key_terms = _tokens(payload.reference) - _STOPWORDS
        if not key_terms:
            return NothingToProduce(reason="reference carries no key terms to compare against")

        prediction_tokens = _tokens(payload.prediction)
        if not prediction_tokens:
            return Produced(value=MetricScore(metric_name="key_terms_precision", value=0.0))

        matched = len(prediction_tokens & key_terms)
        return Produced(
            value=MetricScore(
                metric_name="key_terms_precision", value=matched / len(prediction_tokens)
            )
        )


class _RougeConfig(BaseModel):
    """Shared `with:` shape for every ROUGE variant — `use_stemmer` is the one real knob."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Whether ROUGE stems both sides with the Porter algorithm before matching. Kept `False`
    #: by default: `True` still needs no network or downloaded corpus (Porter is pure code), but
    #: a default of `False` is the more conservative, exact-token comparison an operator has to
    #: opt into loosening rather than opt out of.
    use_stemmer: bool = False


def _rouge_fmeasure(
    rouge_type: str, *, reference: str, prediction: str, use_stemmer: bool
) -> float:
    scorer = rouge_scorer.RougeScorer([rouge_type], use_stemmer=use_stemmer)
    return scorer.score(reference, prediction)[rouge_type].fmeasure


class _RougeMetric:
    """Shared implementation for `RougeL`, `Rouge1` and `Rouge2` — only `_ROUGE_TYPE` differs.

    Reports the F-measure — the number ROUGE is conventionally reported as — computed fresh by
    `rouge-score` for every sample rather than the reference's own hand-rolled DP.
    """

    #: Set on each concrete subclass — `rouge1` / `rouge2` / `rougeL`, and the registered
    #: plugin name it reports under.
    _ROUGE_TYPE: ClassVar[str] = ""
    _METRIC_NAME: ClassVar[str] = ""

    config_model: ClassVar[type[_RougeConfig]] = _RougeConfig
    #: Task 4.7, Q6: `rouge-score`'s pure-Python implementation, no model download and no
    #: network call at `use_stemmer=False` — see the module docstring. Declared once here,
    #: inherited by `RougeL`/`Rouge1`/`Rouge2` rather than restated three times.
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: _RougeConfig | None = None) -> None:
        self._config = config if config is not None else _RougeConfig()

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        if not payload.reference.strip():
            return NothingToProduce(reason="reference is empty — nothing to compare against")

        fmeasure = _rouge_fmeasure(
            self._ROUGE_TYPE,
            reference=payload.reference,
            prediction=payload.prediction,
            use_stemmer=self._config.use_stemmer,
        )
        return Produced(value=MetricScore(metric_name=self._METRIC_NAME, value=fmeasure))


class RougeL(_RougeMetric):
    """Longest-common-subsequence ROUGE, via `rouge-score` rather than a hand-rolled DP table."""

    _ROUGE_TYPE = "rougeL"
    _METRIC_NAME = "rouge_l"


class Rouge1(_RougeMetric):
    """Unigram-overlap ROUGE."""

    _ROUGE_TYPE = "rouge1"
    _METRIC_NAME = "rouge_1"


class Rouge2(_RougeMetric):
    """Bigram-overlap ROUGE."""

    _ROUGE_TYPE = "rouge2"
    _METRIC_NAME = "rouge_2"


__all__ = [
    "KeyTermsPrecision",
    "NoConfig",
    "Rouge1",
    "Rouge2",
    "RougeL",
    "TokenOverlap",
    "TokenRecall",
]
