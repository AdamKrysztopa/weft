"""The six LLM-judge metrics — every one of them derives its own ratio in code.

Task **4.2**. A judge that reads a ratio straight off a `score` field the model itself divided,
while the counts that would let the *code* compute it sit unused two lines below, is a recurring
LLM-judge failure mode worth naming outright — and there are at least three different ways to
avoid it, worth naming separately rather than flattening into one: dividing a judge-reported
count by a code-computed total; never asking the model for a number at all, and instead scoring
by embedding similarity over judge-generated text; or extracting a full confusion-matrix term set
from the judge and deriving F1 in code — the richest of the three, and the one this module's
`AnswerCorrectness` and `AnswerRelevance` are built to match, not the single-division shape.
**Every judge below follows one of these three code-computes-the-ratio shapes. None reads a
score field, because none of the six output models this module's prompts ask for *has* one**
(`weft_eval.prompts`'s own module docstring).

**Every call goes through `weft_prompts.cascade.execute`** — R2: a synchronous judge-predict call
is not something inherited and then fixed here; Weft's async provider call is `CLAUDE.md`'s
async-only rule applied from the start. `weft_retrieve.rerank.
LlmRerank` is the worked example this module follows: `ctx.require(LLM)`, one `Prompt` instance
this pack owns directly (no `StageLookup` — that service is for a *pipeline stage* reaching a
sibling stage, and a `Metric` is explicitly not a pipeline position, per `weft_eval.contract`'s own
docstring), and a `role: str` config field so an operator can point judging at a different model
than generation without this code caring which.

**Every judge treats "nothing to judge" as `NothingToProduce`, matching the rest of the suite** —
an empty context, an empty reference, or a judge that decomposed its input into zero checkable
items are all the same shape as an empty reference elsewhere in this pack: nothing to score,
never a computed zero.
"""

import re
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_embed.contract import Embedder
from weft_eval.contract import (
    GenerationSample,
    MetricScore,
    RetrievalSample,
)
from weft_eval.embedding_support import cosine_similarity, embed_texts
from weft_eval.prompts import (
    AnswerCompletenessJudgePrompt,
    AnswerCompletenessRequest,
    AnswerCorrectnessJudgePrompt,
    AnswerCorrectnessRequest,
    AnswerRelevanceJudgePrompt,
    AnswerRelevanceRequest,
    CompletenessJudgement,
    ContextRecallJudgement,
    ContextRecallJudgePrompt,
    ContextRecallRequest,
    ContextRelevanceJudgement,
    ContextRelevanceJudgePrompt,
    ContextRelevanceRequest,
    FactualClassification,
    FaithfulnessJudgement,
    FaithfulnessJudgePrompt,
    FaithfulnessRequest,
    GeneratedQuestions,
)
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced
from weft_llm.contract import LLM
from weft_prompts.cascade import execute


class JudgeConfig(BaseModel):
    """Shared `with:` shape for every judge below but `AnswerCorrectness`, which extends it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Which `[llm.roles]` mapping answers this judge's questions. Default `"grade"`, the same
    #: default `weft_retrieve.rerank.LlmRerankConfig.role` uses for the identical reason: judging
    #: is a different job from generating, and an operator may want a cheaper or stricter model
    #: for it without this plugin's code knowing or caring which.
    role: str = Field(default="grade", min_length=1)


#: Task 4.7, Q6: every judge in this file constructs no `LLMJudge` of its own — it reaches
#: `ctx.require(LLM)` at call time — so the derivable fact is not "does the constructor import
#: a package" (`embedding_metrics.BERT_SCORE_AVAILABLE`'s shape) but "does this class need a
#: real, judging-capable model behind that service". The offline default (`weft_llm.scripted.
#: ScriptedProvider`) resolves the service without error, but its canned, non-judging text
#: cannot satisfy `weft_prompts.cascade.execute`'s structured-output contract — a judge asked
#: to run against it fails the cascade's own tier 3, not this declaration, which is why the
#: declaration is a flat `False` rather than something derived per-call: whether a *specific*
#: configured provider is good enough is a runtime fact `execute` already discovers and reports
#: on its own, not one this class can predict from its own definition.
_NEEDS_A_JUDGE_MODEL = (
    "needs a real judge model behind '[llm.roles]' — the deterministic 'scripted' provider "
    "resolves the service but cannot produce a usable structured judgement, so this metric "
    "is excluded from the gate's offline subset regardless of whether an operator configures "
    "a role for it. Configure '[llm.roles]' to map this metric's role (default 'grade') to a "
    "real provider such as 'openai' to run it outside the gate."
)


def _numbered(items: tuple[str, ...]) -> str:
    return "\n".join(f"[{index}] {item}" for index, item in enumerate(items))


def _split_sentences(text: str) -> tuple[str, ...]:
    """A plain, dependency-free sentence split — good enough for offering numbered candidates.

    Splits on `.`/`!`/`?` followed by whitespace, keeping non-empty fragments. Not linguistically
    exact; the point is a stable, code-computed denominator for `ContextRelevance` to divide by,
    not a general-purpose sentence tokenizer.
    """

    fragments = re.split(r"(?<=[.!?])\s+", text.strip())
    return tuple(fragment for fragment in fragments if fragment)


class Faithfulness:
    """Fraction of the answer's own standalone statements that the retrieved context supports."""

    config_model: ClassVar[type[JudgeConfig]] = JudgeConfig
    runs_in_gate: ClassVar[bool] = False
    gate_unsafe_reason: ClassVar[str] = _NEEDS_A_JUDGE_MODEL

    def __init__(self, config: JudgeConfig | None = None) -> None:
        self._config = config if config is not None else JudgeConfig()

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        if not payload.contexts:
            return NothingToProduce(reason="no retrieved context to check groundedness against")

        llm = ctx.require(LLM)
        outcome = await execute(
            llm=llm,
            prompt=FaithfulnessJudgePrompt(),
            values=FaithfulnessRequest(
                answer=payload.prediction, contexts=_numbered(payload.contexts)
            ),
            output=FaithfulnessJudgement,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(outcome, Produced):
            return outcome

        statements = outcome.value.value.statements
        if not statements:
            return NothingToProduce(reason="the judge found no checkable statements in the answer")

        supported = sum(1 for statement in statements if statement.supported)
        return Produced(
            value=MetricScore(metric_name="faithfulness", value=supported / len(statements))
        )


class ContextRecall:
    """Fraction of the reference answer's own claims that the retrieved context supports."""

    config_model: ClassVar[type[JudgeConfig]] = JudgeConfig
    runs_in_gate: ClassVar[bool] = False
    gate_unsafe_reason: ClassVar[str] = _NEEDS_A_JUDGE_MODEL

    def __init__(self, config: JudgeConfig | None = None) -> None:
        self._config = config if config is not None else JudgeConfig()

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        if not payload.reference:
            return NothingToProduce(reason="no reference answer to check context recall against")
        if not payload.retrieved:
            return NothingToProduce(reason="nothing retrieved to check for support")

        llm = ctx.require(LLM)
        contexts = _numbered(tuple(passage.text for passage in payload.retrieved))
        outcome = await execute(
            llm=llm,
            prompt=ContextRecallJudgePrompt(),
            values=ContextRecallRequest(reference=payload.reference, contexts=contexts),
            output=ContextRecallJudgement,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(outcome, Produced):
            return outcome

        claims = outcome.value.value.claims
        if not claims:
            return NothingToProduce(
                reason="the judge found no checkable claims in the reference answer"
            )

        supported = sum(1 for claim in claims if claim.supported)
        return Produced(
            value=MetricScore(metric_name="context_recall", value=supported / len(claims))
        )


class ContextRelevance:
    """Fraction of the retrieved context's own sentences that are relevant to the query.

    The denominator — how many sentences were offered — is computed in Weft's own code by
    `_split_sentences`, never asked of the model; only *which* of those sentences are relevant is
    the model's answer.
    """

    config_model: ClassVar[type[JudgeConfig]] = JudgeConfig
    runs_in_gate: ClassVar[bool] = False
    gate_unsafe_reason: ClassVar[str] = _NEEDS_A_JUDGE_MODEL

    def __init__(self, config: JudgeConfig | None = None) -> None:
        self._config = config if config is not None else JudgeConfig()

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        if not payload.retrieved:
            return NothingToProduce(reason="nothing retrieved to judge relevance of")

        sentences = tuple(
            sentence for passage in payload.retrieved for sentence in _split_sentences(passage.text)
        )
        if not sentences:
            return NothingToProduce(reason="the retrieved context carries no sentences to judge")

        llm = ctx.require(LLM)
        outcome = await execute(
            llm=llm,
            prompt=ContextRelevanceJudgePrompt(),
            values=ContextRelevanceRequest(question=payload.query, sentences=_numbered(sentences)),
            output=ContextRelevanceJudgement,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(outcome, Produced):
            return outcome

        offered = len(sentences)
        indices = frozenset(outcome.value.value.relevant_indices)
        invalid = sorted(index for index in indices if index >= offered or index < 0)
        if invalid:
            return Failed(
                reason=(
                    f"'context-relevance' offered {offered} sentence(s), and the judge marked "
                    f"index/indices {invalid} relevant — never offered. Scoring a partial or "
                    f"invented answer would mix a real judgement with a hallucinated one."
                )
            )

        return Produced(
            value=MetricScore(metric_name="context_relevance", value=len(indices) / offered)
        )


class AnswerRelevance:
    """How closely the questions this answer would address match the question actually asked.

    Never asks the model for a score — the judge only generates candidate questions;
    `weft_eval.embedding_support.embed_texts` embeds each one and the original query, and the
    average cosine similarity is the value.
    """

    config_model: ClassVar[type[JudgeConfig]] = JudgeConfig
    runs_in_gate: ClassVar[bool] = False
    gate_unsafe_reason: ClassVar[str] = _NEEDS_A_JUDGE_MODEL

    def __init__(self, config: JudgeConfig | None = None) -> None:
        self._config = config if config is not None else JudgeConfig()

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        if not payload.prediction.strip():
            return NothingToProduce(reason="prediction is empty — nothing to judge relevance of")

        llm = ctx.require(LLM)
        outcome = await execute(
            llm=llm,
            prompt=AnswerRelevanceJudgePrompt(),
            values=AnswerRelevanceRequest(answer=payload.prediction),
            output=GeneratedQuestions,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(outcome, Produced):
            return outcome

        questions = outcome.value.value.questions
        if not questions:
            return NothingToProduce(reason="the judge derived no question from the answer")

        embedder = ctx.require(Embedder)
        embedded = await embed_texts(embedder, (payload.query, *questions), ctx)
        if not isinstance(embedded, Produced):
            return embedded

        query_vector, *question_vectors = embedded.value
        similarities = [
            cosine_similarity(query_vector.values, vector.values) for vector in question_vectors
        ]
        return Produced(
            value=MetricScore(
                metric_name="answer_relevance", value=sum(similarities) / len(similarities)
            )
        )


class AnswerCorrectnessConfig(JudgeConfig):
    """`AnswerCorrectness`'s own `with:` shape — `role`, plus how much weight factual F1 gets."""

    #: Weight given to the factual F1 half; `1 - factual_weight` goes to semantic similarity.
    #: A weighted-F1-plus-semantic combination, made an operator's own typed choice rather than a
    #: constant buried in `__init__`.
    factual_weight: float = Field(default=0.75, ge=0.0, le=1.0)


class AnswerCorrectness:
    """Weighted average of a code-derived factual F1 and an embedding-based semantic similarity.

    The judge classifies statements into a true/false-positive/false-negative confusion matrix
    (`weft_eval.prompts.FactualClassification`), and F1 is computed from those three counts in
    this method, never read off a `score` field.
    """

    config_model: ClassVar[type[AnswerCorrectnessConfig]] = AnswerCorrectnessConfig
    runs_in_gate: ClassVar[bool] = False
    gate_unsafe_reason: ClassVar[str] = _NEEDS_A_JUDGE_MODEL

    def __init__(self, config: AnswerCorrectnessConfig | None = None) -> None:
        self._config = config if config is not None else AnswerCorrectnessConfig()

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        if not payload.reference.strip():
            return NothingToProduce(reason="reference is empty — nothing to compare against")

        llm = ctx.require(LLM)
        outcome = await execute(
            llm=llm,
            prompt=AnswerCorrectnessJudgePrompt(),
            values=AnswerCorrectnessRequest(
                question=payload.query, prediction=payload.prediction, reference=payload.reference
            ),
            output=FactualClassification,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(outcome, Produced):
            return outcome

        classification = outcome.value.value
        factual_f1 = _f1(classification)
        if factual_f1 is None:
            return NothingToProduce(reason="the judge classified no factual statements at all")

        embedder = ctx.require(Embedder)
        embedded = await embed_texts(embedder, (payload.prediction, payload.reference), ctx)
        if not isinstance(embedded, Produced):
            return embedded
        prediction_vector, reference_vector = embedded.value
        semantic = cosine_similarity(prediction_vector.values, reference_vector.values)

        weight = self._config.factual_weight
        value = weight * factual_f1 + (1 - weight) * semantic
        return Produced(value=MetricScore(metric_name="answer_correctness", value=value))


def _f1(classification: FactualClassification) -> float | None:
    true_positives = len(classification.true_positives)
    false_positives = len(classification.false_positives)
    false_negatives = len(classification.false_negatives)
    if true_positives == 0 and false_positives == 0 and false_negatives == 0:
        return None
    if true_positives == 0:
        return 0.0
    precision = true_positives / (true_positives + false_positives)
    recall = true_positives / (true_positives + false_negatives)
    return 2 * precision * recall / (precision + recall)


class AnswerCompleteness:
    """Fraction of the reference's own key points that the prediction actually covers.

    Not a RAGAS metric — see `weft_eval.prompts.AnswerCompletenessJudgePrompt`'s own docstring
    for why this plugin carries no `ragas_` prefix.
    """

    config_model: ClassVar[type[JudgeConfig]] = JudgeConfig
    runs_in_gate: ClassVar[bool] = False
    gate_unsafe_reason: ClassVar[str] = _NEEDS_A_JUDGE_MODEL

    def __init__(self, config: JudgeConfig | None = None) -> None:
        self._config = config if config is not None else JudgeConfig()

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        if not payload.reference.strip():
            return NothingToProduce(reason="reference is empty — nothing to compare against")

        llm = ctx.require(LLM)
        outcome = await execute(
            llm=llm,
            prompt=AnswerCompletenessJudgePrompt(),
            values=AnswerCompletenessRequest(
                prediction=payload.prediction, reference=payload.reference
            ),
            output=CompletenessJudgement,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(outcome, Produced):
            return outcome

        judgement = outcome.value.value
        total = len(judgement.covered) + len(judgement.missing)
        if total == 0:
            return NothingToProduce(reason="the judge found no key points in the reference")

        return Produced(
            value=MetricScore(
                metric_name="answer_completeness", value=len(judgement.covered) / total
            )
        )


__all__ = [
    "AnswerCompleteness",
    "AnswerCorrectness",
    "AnswerCorrectnessConfig",
    "AnswerRelevance",
    "ContextRecall",
    "ContextRelevance",
    "Faithfulness",
    "JudgeConfig",
]
