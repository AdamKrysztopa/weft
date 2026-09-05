"""`embedding-similarity` and `bertscore` — the two traditional metrics that need a model.

Task **4.2**. Both are gated behind a module-level `importlib.util.find_spec(...)` boolean,
computed once at import rather than hand-maintained in a table — the right *shape* for
declaring optional-dependency availability, independent of which package it happens to gate.
Weft already has a contract for "turn text into a vector":
`weft_embed.contract.Embedder`, resolved through `ctx.require(Embedder)` exactly the way
`weft_retrieve.rerank.LlmRerank` resolves `LLM`. **`embedding-similarity` uses it**, via
`weft_eval.embedding_support.embed_texts`, so this metric needs no new dependency at all —
whatever embedder a run has configured (`hash` for an offline gate, `openai` for a real one) is
the embedder this metric measures with, and `find_spec` has nothing to derive because there is no
optional import to gate.

**`bertscore` is the one metric in the whole suite that genuinely cannot be expressed this way.**
It scores token-level, contextual BERT embeddings — a different computation from "embed this
string once," which is what every `Embedder` in this tree does — so it keeps that same
derivation *pattern*: `BERT_SCORE_AVAILABLE` is computed once, at import, via `importlib.util.
find_spec("bert_score")`, never a hand-maintained flag. `bert-score` (which pulls in `transformers`
and a checkpoint download) is declared as an **optional extra** (`pyproject.toml`'s `[project.
optional-dependencies] bertscore`), not a base dependency of this pack — so a clean checkout with
no account and no cached model installs and runs `poe ci-checks` exactly as before, and `bertscore`
answers `Failed`, naming the missing extra, rather than crashing at import or silently vanishing
from the registry. Task **4.7** owns wiring "unavailable" into a run's official offline-subset
selection; this task only owns making the unavailability a derived, checkable fact rather than a
guess.
"""

import importlib.util
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_embed.contract import Embedder
from weft_eval.contract import GenerationSample, MetricScore
from weft_eval.embedding_support import cosine_similarity, embed_texts
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced

#: Derived once, at import — never a hand-maintained table. `True` iff the optional `bertscore`
#: extra is installed.
BERT_SCORE_AVAILABLE: bool = importlib.util.find_spec("bert_score") is not None


class NoConfig(BaseModel):
    """The empty `with:` shape both metrics in this file take — neither has a tunable."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EmbeddingSimilarity:
    """Cosine similarity between `prediction`'s and `reference`'s embeddings.

    Embeds through whatever `Embedder` the run has configured — see the module docstring for why
    this needs no dependency of its own, and satisfies `GenerationMetric` structurally without
    importing it.
    """

    config_model: ClassVar[type[NoConfig]] = NoConfig
    #: Task 4.7, Q6: whatever `Embedder` a run has configured — `hash` for an offline gate,
    #: which needs no credential, no network and no model download (see the module docstring).
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: NoConfig | None = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        if not payload.reference.strip() or not payload.prediction.strip():
            return NothingToProduce(reason="prediction or reference is empty — nothing to embed")

        embedder = ctx.require(Embedder)
        outcome = await embed_texts(embedder, (payload.prediction, payload.reference), ctx)
        if not isinstance(outcome, Produced):
            return outcome

        prediction_vector, reference_vector = outcome.value
        similarity = cosine_similarity(prediction_vector.values, reference_vector.values)
        return Produced(value=MetricScore(metric_name="embedding_similarity", value=similarity))


class BERTScore:
    """Greedy token-level matching over contextual BERT embeddings — the F-measure half.

    Answers `Failed`, naming the missing optional extra, when `bert_score` is not installed —
    never silently absent from the registry and never a crash at import time, since the class
    still constructs and registers; only `evaluate` needs the package.
    """

    config_model: ClassVar[type[NoConfig]] = NoConfig
    #: Task 4.7, Q6: `False` unconditionally — even with the optional extra installed, this
    #: metric downloads a BERT checkpoint on first use, which a clean gate checkout cannot do.
    runs_in_gate: ClassVar[bool] = False
    #: Read defensively by `weft_eval.offline`, the same convention-not-seam status `intact`
    #: already has — never required, only read when present.
    gate_unsafe_reason: ClassVar[str] = (
        "needs the optional 'bert_score' package and a downloaded BERT checkpoint on first "
        "use — install weft-eval's 'bertscore' extra to run this metric outside the gate"
    )

    def __init__(self, config: NoConfig | None = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if payload.prediction is None:
            return Failed(reason="no prediction to evaluate — the sample carries none")
        if not payload.reference.strip():
            return NothingToProduce(reason="reference is empty — nothing to compare against")
        if not BERT_SCORE_AVAILABLE:
            return Failed(
                reason="bertscore needs the optional 'bert_score' package, which is not "
                "installed — install weft-eval's 'bertscore' extra to run this metric"
            )

        import bert_score

        _, _, f1 = bert_score.score(
            [payload.prediction], [payload.reference], lang="en", verbose=False
        )
        return Produced(value=MetricScore(metric_name="bertscore", value=float(f1.mean())))


__all__ = ["BERT_SCORE_AVAILABLE", "BERTScore", "EmbeddingSimilarity", "NoConfig"]
