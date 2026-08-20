"""`weft eval run --questions` — task **4.9**, the orchestration half of closing
`.phase4-design.md` §7's gap: retrieve real passages through a resolved pipeline's own
embed/store stages, for a caller-supplied set of queries, so `weft_eval.harness.
score_retrieval_gate_subset` has real `RetrievalSample`s to score rather than none.

**Ground truth is named by document, never by node id.** A `Question.relevant_documents` entry
names a `SourceDoc.source_id` — the same string `weft_cli.ingest.IndexResult.document_ids`
carries, and for the default text extractor that is a resolved, absolute file path
(`weft_extract.text.discover_source_docs`'s own docstring). A node id is a content-addressed
digest an author writing this file ahead of a run cannot predict; a document a corpus already
holds, they can name. So `_document_id_of` below reads a hit's own `lineage.sources` — the
identical field `weft_cli.ask.AskHit.sources` already surfaces to a human — rather than the
node's own id, and scores retrieval at the granularity a fixture can actually be authored at.

**Retrieval reuses `weft_cli.ask.run_ask`, widened rather than duplicated.** `run_ask`'s own
embed-then-search walk is exactly what scoring needs, once it is told which plugin and
configuration to use — this module never re-derives it. Task 4.9 widened `run_ask` with two
optional parameters (`embedder_config`/`store_config`) precisely so this module could hand back
a resolved stage's own configuration instead of `[services]`' default, which Q3 (task 4.0) says a
named pipeline never reads anyway.

**`--questions` is optional, and `RunRecord.metrics` stays `{}` when it is omitted** — the same
honesty `weft_cli.eval_commands`'s own module docstring already argues for `model_versions`
before task 4.7: a gap named rather than filled with a fabricated number.

**Retrieved passages are deduplicated to one entry per document before scoring — a real defect,
found running the binary against a real chunked corpus, fixed here.** `weft_eval.ir_metrics.
RecallAtK` sums one hit per *retrieved* position that names a relevant id; that is the correct,
standard definition when each position is a distinct candidate, which is exactly what stops
being true once ground truth is named by *document* (this module's own choice, above) over a
corpus chunked into several passages per document — several ranks in `run_ask`'s own top-`k` can
legitimately be different chunks of the *same* document, and scoring each one as a separate hit
against a one-document `relevant_ids` set produced a measured recall **above 1.0**, which is not
a number V4's own contract can mean anything by. `_deduplicated_by_document` retrieves a larger
raw pool than `top_k` (`_OVERSAMPLE_FACTOR`) and keeps only each document's first, best-ranked
occurrence, so `RetrievalSample.retrieved` never repeats an id — the identical granularity
`relevant_ids` is already named at.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from weft_cli.ask import run_ask
from weft_embed import Embedder
from weft_eval.aggregate import MetricAggregate
from weft_eval.contract import RetrievalSample, RetrievedPassage
from weft_eval.harness import score_retrieval_gate_subset
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, Outcome
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_store import NodeStore, Scored


class QuestionsFileError(WeftError):
    """`--questions <path>` names a file that does not exist, is not valid JSON, or is not a
    well-formed list of questions — a caller-input problem, not a name-resolution failure, so
    it carries no `valid_options` and is not a member of `NAME_RESOLUTION_FAMILY`.
    """

    def __init__(self, message: str, *, path: str) -> None:
        super().__init__(message)
        self.path = path


class PipelineNotRetrievableError(WeftError):
    """`--questions` was given, but the resolved pipeline names no `Embedder`/`NodeStore` stage
    to retrieve against — there is nothing `run_ask` could query, so scoring refuses outright
    rather than silently reporting an empty `metrics` mapping that looks identical to "no
    `--questions` given at all."
    """

    def __init__(self, message: str, *, pipeline: str) -> None:
        super().__init__(message)
        self.pipeline = pipeline


class Question(BaseModel):
    """One (query, relevant document ids) judgement `weft eval run --questions` scores
    retrieval against. See the module docstring for why `relevant_documents` names documents,
    never node ids.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1)
    relevant_documents: tuple[str, ...] = ()


def load_questions(path: Path) -> tuple[Question, ...]:
    """Every `Question` `path` holds — a JSON list of `{"query": ..., "relevant_documents": [...]}`.

    Raises `QuestionsFileError` for a file that cannot be read, is not valid JSON, is not a JSON
    list, or holds an entry `Question` refuses — one refusal for every way this input can be
    malformed, rather than a bare `OSError`/`JSONDecodeError`/`ValidationError` a caller has to
    already know this module's internals to make sense of.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise QuestionsFileError(f"could not read '{path}': {exc}", path=str(path)) from exc

    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QuestionsFileError(f"'{path}' is not valid JSON: {exc}", path=str(path)) from exc

    if not isinstance(parsed, list):
        raise QuestionsFileError(
            f"'{path}' must hold a JSON list of questions, found {type(parsed).__name__}",
            path=str(path),
        )
    items = cast("list[object]", parsed)

    try:
        return tuple(Question.model_validate(item) for item in items)
    except ValidationError as exc:
        raise QuestionsFileError(
            f"'{path}' holds a malformed question: {exc}", path=str(path)
        ) from exc


def _stage_for_contract(resolved: ResolvedPipeline, contract_name: str) -> ResolvedStage | None:
    """The one stage in `resolved.stages` registered under `contract_name`, or `None`.

    `ResolvedStage.contract` is the contract's own printable name (`weft_kernel.resolution`'s
    own docstring), never a Python type — the identical string `Embedder.__name__`/
    `NodeStore.__name__` already are.
    """
    for stage in resolved.stages:
        if stage.contract == contract_name:
            return stage
    return None


def _document_id_of(hit: Scored[Node]) -> str:
    """The document a retrieved hit is attributed to — sorted first of its own `lineage.
    sources`, `weft_cli.ask.AskHit.sources`' own construction, or the node's own id when a hit
    carries no source at all (a synthetic node, which never happens for a real indexed passage).
    """
    sources = sorted(str(source) for source in hit.value.lineage.sources)
    return sources[0] if sources else str(hit.value.id)


def _factory_config(config: object) -> object:
    """`config` narrowed to what a plugin's own factory actually expects — a real defect,
    found running the binary and not by any unit test, fixed here: `ResolvedStage.config`
    holds one of two shapes (a validated `config_model` instance, or an empty read-only
    mapping for a plugin declaring none), but every plugin in this tree is documented and
    written to accept `config: XConfig | None = None` — never a bare mapping. Passing the
    empty-mapping shape straight through crashes the first plugin that reads an attribute off
    it (`HashEmbedder._config.dimension`, here). `weft_cli.compile.to_specs` already carries
    the identical narrowing for the exact identical reason (its own docstring: "handing it a
    mapping where it expects `None` would give every no-configuration plugin in the tree an
    argument it..."); this is that established rule, applied at `run_ask`'s own boundary
    rather than a second, divergent normalisation invented here.
    """
    return config if isinstance(config, BaseModel) else None


#: How much deeper than `top_k` `score_pipeline` retrieves before deduplicating to distinct
#: documents — see the module docstring's paragraph on why deduplication is necessary at all.
#: Generous rather than exact: a corpus chunked finely enough that `top_k` distinct documents
#: do not appear in `top_k * _OVERSAMPLE_FACTOR` raw hits is scored on however many did, never
#: an error — the identical "best effort over what is actually there" `run_ask` itself already
#: gives a search with fewer than `top_k` results in the store.
_OVERSAMPLE_FACTOR = 8


def _deduplicated_by_document(
    hits: Sequence[Scored[Node]], *, top_k: int
) -> tuple[RetrievedPassage, ...]:
    """`hits`, ranked, collapsed to at most `top_k` entries — one per distinct document, kept at
    its first (best-ranked) occurrence. See the module docstring's own paragraph for why.
    """
    passages: list[RetrievedPassage] = []
    seen: set[str] = set()
    for hit in hits:
        document_id = _document_id_of(hit)
        if document_id in seen:
            continue
        seen.add(document_id)
        passages.append(RetrievedPassage(id=document_id, text=hit.value.content))
        if len(passages) == top_k:
            break
    return tuple(passages)


async def score_pipeline(
    *,
    registry: Registry,
    resolved_pipeline: ResolvedPipeline,
    questions: tuple[Question, ...],
    top_k: int,
    ctx: Context,
) -> Mapping[str, Outcome[MetricAggregate]]:
    """Retrieve for every one of `questions` through `resolved_pipeline`'s own embed/store
    stages, and score the gate-safe `RetrievalMetric` subset over the result.

    Raises `PipelineNotRetrievableError` if `resolved_pipeline` names no `Embedder`/`NodeStore`
    stage. An empty `questions` tuple still calls through — `weft_eval.harness.
    score_retrieval_gate_subset` already answers that honestly, one place rather than two.
    """
    embed_stage = _stage_for_contract(resolved_pipeline, Embedder.__name__)
    store_stage = _stage_for_contract(resolved_pipeline, NodeStore.__name__)
    if embed_stage is None or store_stage is None:
        missing = "Embedder" if embed_stage is None else "NodeStore"
        raise PipelineNotRetrievableError(
            f"pipeline '{resolved_pipeline.name}' has no stage registered under the "
            f"{missing} contract, so --questions has nothing to retrieve against.",
            pipeline=resolved_pipeline.name,
        )

    samples: list[RetrievalSample] = []
    for question in questions:
        hits = await run_ask(
            question.query,
            registry=registry,
            ctx=ctx,
            top_k=top_k * _OVERSAMPLE_FACTOR,
            embedder=embed_stage.use,
            store=store_stage.use,
            embedder_config=_factory_config(embed_stage.config),
            store_config=_factory_config(store_stage.config),
        )
        samples.append(
            RetrievalSample(
                query=question.query,
                retrieved=_deduplicated_by_document(hits, top_k=top_k),
                relevant_ids=frozenset(question.relevant_documents),
            )
        )

    return await score_retrieval_gate_subset(registry, samples, top_k=top_k, ctx=ctx)


__all__ = [
    "PipelineNotRetrievableError",
    "Question",
    "QuestionsFileError",
    "load_questions",
    "score_pipeline",
]
