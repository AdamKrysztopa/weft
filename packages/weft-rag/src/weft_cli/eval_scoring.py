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

**This module reads `weft_eval.question_set.Question` — task 38.11.** It used to define its own,
JSON-only `Question`; that model is retired, and every question `score_pipeline` scores — whether
read from a curated TOML set, a legacy JSON file converted at the boundary, or a graph bridge —
arrives through the one model. `document_labels` is the manifest-id path: `eval/questions/*.toml`
names documents by manifest id rather than by corpus-relative path, and a caller holding the
manifest's own id-to-path mapping passes it here so `resolve_labels` still receives the paths it
has always matched against.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, Final, cast

from pydantic import BaseModel

from weft_cli.ask import run_ask
from weft_cli.route_ask import (
    PipelineDidNotProduceError,
    PreparedRunner,
    prepared_services,
    resolve_named_pipeline,
    run_named_ask,
    run_named_rerank,
    run_named_retrieve,
)
from weft_embed import Embedder
from weft_engine.llm_roles import LLMSection
from weft_engine.service_roles import RoleTable
from weft_engine.services import ServiceSelection
from weft_eval.aggregate import MetricAggregate
from weft_eval.contract import GenerationSample, RetrievalSample, RetrievedPassage
from weft_eval.harness import (
    SubsetScores,
    score_generation_gate_subset,
    score_retrieval_at_cutoffs,
    score_retrieval_gate_subset,
)
from weft_eval.pool import (
    LoadedPool,
    PoolChunk,
    PoolIntegrityError,
    PoolQuestion,
    PoolQuestionEntry,
    relevant_set_sha256,
    text_sha256,
)
from weft_eval.question_set import Question, question_set_digest
from weft_eval.run_record import (
    NoQueryRung,
    PerQuestionScores,
    PerQuestionSeconds,
    QueryRung,
    QuestionKey,
    QuestionOutcome,
    RoleTokens,
    ScoredQueryRung,
)
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Node, NodeId, Outcome
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution, ResolvedPipeline, ResolvedStage, pipeline_identity
from weft_llm.client import NullSink
from weft_llm.contract import TokenSink
from weft_llm.errors import LLMGenerationLoopError
from weft_llm.usage import UsageEntry, recording_usage
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store import NodeStore, Scored


class PipelineNotRetrievableError(WeftError):
    """`--questions` was given, but the resolved pipeline names no `Embedder`/`NodeStore` stage
    to retrieve against — there is nothing `run_ask` could query, so scoring refuses outright
    rather than silently reporting an empty `metrics` mapping that looks identical to "no
    `--questions` given at all."
    """

    def __init__(self, message: str, *, pipeline: str) -> None:
        super().__init__(message)
        self.pipeline = pipeline


class UnresolvableLabelError(WeftError, UnresolvedNameError):
    """A `relevant_documents` label names no document in the corpus that was scored.

    Refused rather than scored, which is this project's own scar: an early RAPTOR run read
    `0.000` at every cutoff because ground truth named manifest ids and hits are attributed by
    resolved path, and a `0.000` meaning *the harness is wrong* cannot be told from a `0.000`
    meaning *the architecture fails* (`docs/internal/build-ledger.md:5528 'an early run read'`).
    A question whose ground truth names nothing is a broken input, not a hard question.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], label: str) -> None:
        super().__init__(message)
        self.valid_options = valid_options
        self.label = label


class ForeignDocumentRetrievedError(WeftError):
    """`refuse_foreign_documents=True` and a retrieved passage names a document outside the
    corpus this run scored — task **38.0**'s own guard for `weft eval experiment`.

    An experiment's arms share one store: two arms pointed at two different corpora directories
    still both index into it, so a passage from a document the *other* arm indexed can surface
    for this one's questions. Scored as a normal miss, that reads as a worse pipeline rather than
    what it is — a foreign document nothing here judged at all — so this refuses outright the
    moment one is seen, before it ever reaches `_deduplicated_by_document`.
    """

    def __init__(self, message: str, *, document: str, corpus_documents: tuple[str, ...]) -> None:
        super().__init__(message)
        self.document = document
        self.corpus_documents = corpus_documents


class AmbiguousLabelError(WeftError, UnresolvedNameError):
    """A `relevant_documents` label names more than one document in the corpus.

    `weft_cli.ingest.AmbiguousExtractorError`'s own footing one surface over: a name matching
    too much is refused rather than resolved by picking, because whichever document the
    resolution happened to choose would score and the other would count as a miss for a
    question that named it.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], label: str) -> None:
        super().__init__(message)
        self.valid_options = valid_options
        self.label = label


def _label_matches(label_parts: tuple[str, ...], document_parts: tuple[str, ...]) -> bool:
    """Whether `label_parts` is a **suffix** of `document_parts`, compared component-wise —
    task 16.5. Comparing the joined strings instead would let `7717v2.pdf` match a path merely
    ending in that character sequence, which is the tail of a filename rather than a
    corpus-relative path; `pathlib` splits both sides on the separator first so a match can
    only land on a whole path component.
    """
    if len(label_parts) > len(document_parts):
        return False
    return document_parts[len(document_parts) - len(label_parts) :] == label_parts


def resolve_labels(
    labels: Iterable[str], *, corpus_document_ids: Sequence[str]
) -> Mapping[str, str]:
    """Each label, mapped to the corpus document id it names — task **16.5**.

    A label matches a document when the label's path components are a **suffix** of the
    document's, compared component-wise rather than as a string: `arxiv/1304.7717v2.pdf` names
    `/anywhere/corpus/arxiv/1304.7717v2.pdf` in every staging, and `7717v2.pdf` names nothing,
    because it is the tail of a filename rather than a path. A whole resolved path is its own
    suffix, so a questions file written before this task keeps working.

    Raises `UnresolvableLabelError` for a label matching no document and `AmbiguousLabelError`
    for one matching several, both naming the label and the documents — never a silent pick and
    never a miss that reads as a hard question.
    """
    valid_options = tuple(sorted(corpus_document_ids))
    resolved: dict[str, str] = {}
    for label in labels:
        label_parts = PurePath(label).parts
        matches = sorted(
            document_id
            for document_id in corpus_document_ids
            if _label_matches(label_parts, PurePath(document_id).parts)
        )
        if not matches:
            raise UnresolvableLabelError(
                f"relevant_documents label '{label}' names no document in the scored corpus. "
                f"Valid options: {', '.join(valid_options)}",
                valid_options=valid_options,
                label=label,
            )
        if len(matches) > 1:
            raise AmbiguousLabelError(
                f"relevant_documents label '{label}' names {len(matches)} documents in the "
                f"scored corpus: {', '.join(matches)}",
                valid_options=valid_options,
                label=label,
            )
        resolved[label] = matches[0]
    return resolved


def _labelled_by_manifest(
    entries: Iterable[str], document_labels: Mapping[str, str]
) -> Mapping[str, str]:
    """Each `relevant_documents` entry, as `document_labels` names it — task **38.11**'s
    manifest-id path. `document_labels` maps a manifest id (`eval/questions/*.toml`'s own
    ground-truth vocabulary) to the corpus-relative label `resolve_labels` already matches
    against, so this runs *before* that resolution rather than replacing it.

    Raises `UnresolvableLabelError` for an entry the mapping does not hold, naming it and every
    id the mapping does hold — `resolve_labels`'s own refusal shape, one stage earlier.
    """
    valid_options = tuple(sorted(document_labels))
    resolved: dict[str, str] = {}
    for entry in entries:
        if entry not in document_labels:
            raise UnresolvableLabelError(
                f"relevant_documents entry '{entry}' names no id in the given manifest. "
                f"Valid options: {', '.join(valid_options)}",
                valid_options=valid_options,
                label=entry,
            )
        resolved[entry] = document_labels[entry]
    return resolved


class AnswerCarriesNoUsedPassagesError(WeftError):
    """`passages_for_scoring` was handed something that is not a `weft_generate.payload.Answer`
    — or a stand-in shaped like one — so there is no `used` tuple to score a query rung over.

    Named rather than a bare `AttributeError`: `01` requirement 5's rule applies here exactly
    as it does to every other refusal in this module, even though there is no "valid option" to
    list — the caller passed the wrong *kind* of value, not an unrecognised name.
    """

    def __init__(self, message: str, *, answer_type: str) -> None:
        super().__init__(message)
        self.answer_type = answer_type


class CollidingScoreNameError(WeftError):
    """A retrieval metric and a generation metric both report the same name in one run — task
    **32.14**.

    `weft_eval.harness.CollidingMetricNameError` already refuses this within one contract
    (`score_retrieval_gate_subset` alone, `score_generation_gate_subset` alone); this is the
    identical refusal one contract boundary up, because `score_pipeline` merges the two
    `SubsetScores` into one `ScoredRun.metrics`/`question_scores` mapping and a name both sides
    claim would silently replace one with the other exactly as it would within either function
    alone. Names both the reported name and the fact that it crossed contracts, because a
    generation metric colliding with a retrieval metric is a different fault from two
    generation metrics colliding with each other.
    """

    def __init__(self, message: str, *, name: str) -> None:
        super().__init__(message)
        self.name = name


def passages_for_scoring(answer: object) -> tuple[Passage, ...]:
    """The passages a query rung's own answer is scored over — `answer.used`, and nothing else.

    **Why `used` and not the ranking.** `weft_generate.payload.Answer.used`'s own docstring is
    the authority: "exactly the passages that entered the prompt — not the ranking, not the
    candidates... what a reader needs to judge the answer without re-running the pipeline."
    Scoring `Candidates`/`Ranking` instead would measure what a `Retriever` or `Fuser` handed
    back, which is not necessarily what the `ContextPacker` kept or the `Generator` actually
    read — exactly the gap this module's own docstring names as Phase 8's finding.

    `answer` is typed `object` rather than `Answer` deliberately: this is read at the seam a
    real `weft_generate.payload.Answer` and a test's duck-typed stand-in both cross, and a
    stand-in that carries `used` but is not literally an `Answer` instance must not be turned
    away by a type check this function has no need to make — `getattr` decides, not
    `isinstance`. **The return type is `tuple[Any, ...]` for the identical reason, not
    `tuple[weft_retrieve.payload.Passage, ...]`**: a caller resolving a *real* `Answer` reads
    genuine `Passage`s back (see `score_pipeline`'s own `.scored` access), but a declared
    `Passage` return would bind the test's duck-typed stand-in to that same concrete type at
    every call site, including one that never imports `weft_retrieve` at all — turning a
    seam this function deliberately keeps untyped on the way in into one that is typed on the
    way out. Raises `AnswerCarriesNoUsedPassagesError` for anything that carries no `used` at
    all, rather than an `AttributeError` a caller has to already know this module's internals
    to make sense of.
    """
    used = getattr(answer, "used", None)
    if used is None:
        raise AnswerCarriesNoUsedPassagesError(
            f"{type(answer).__name__} carries no 'used' passages to score a query rung over — "
            "expected an Answer (or a stand-in shaped like one) with a 'used' tuple.",
            answer_type=type(answer).__name__,
        )
    return cast("tuple[Any, ...]", used)


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


def _refuse_foreign_documents(
    hits: Sequence[Scored[Node]], *, corpus_document_ids: Sequence[str]
) -> None:
    """`refuse_foreign_documents=True`'s own check — see `ForeignDocumentRetrievedError`'s own
    docstring. Checked before deduplication or scoring, over every hit a question retrieved,
    whichever branch (`run_ask` or a named `query_pipeline`) produced them.
    """
    known = frozenset(corpus_document_ids)
    for hit in hits:
        document = _document_id_of(hit)
        if document not in known:
            raise ForeignDocumentRetrievedError(
                f"a retrieved passage names document '{document}', which the store holds but "
                f"the scored corpus does not ({len(known)} document(s)).",
                document=document,
                corpus_documents=tuple(sorted(known)),
            )


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


def _ranked_by_score(hits: Sequence[Scored[Node]]) -> tuple[Scored[Node], ...]:
    """`hits`, ordered by `Scored.score` descending — task **16.7**, `12` §3's second defect.

    **`Answer.used` stays the right set; only its order is disregarded here, and task 7.5's
    settlement is untouched.** On the `--query-pipeline` path `hits` comes from
    `passages_for_scoring(answer)`, i.e. `Answer.used` — the passages the generator actually
    saw, which is exactly what task 7.5 settled it should be. But `weft_retrieve.repack`'s
    default method is `reverse` (best hit last, immediately before the question), so `used`'s
    own tuple order is the *packer's* order, not retrieval's — a rank metric reading it
    unsorted was scoring the inversion of the ranking retrieval produced. `Scored.score` is a
    similarity (`weft_cli.ask.run_ask`'s own docstring: pgvector's `1 - cosine distance`), so
    descending is best-first. On the plain `run_ask` path `hits` already arrives in that order,
    so this is a no-op there — sorted unconditionally rather than only on the branch that needs
    it, because one rule stated once is worth more than a branch whose two sides a reader has
    to compare. `sorted` is stable, so hits already tied on score keep the order they arrived in.
    """
    return tuple(sorted(hits, key=lambda hit: hit.score, reverse=True))


def _scored_in_ranking_order(passages: Sequence[Passage]) -> list[Scored[Node]]:
    """Packed passages as `Scored`, best-first with ties in the ranking's order (`R40.0`).

    `_ranked_by_score`'s sort is stable, so a tie reaches it in whatever order arrives here; a
    packed passage's `rank` is its position in the ranking before packing, and `reverse` has
    inverted the tuple.
    """
    return [p.scored for p in sorted(passages, key=lambda p: (-p.score, p.rank))]


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


#: `ScoredRun.question_scores`'s own default — a bare `{}` default infers `dict[Unknown,
#: Unknown]` under pyright strict, the same reason `weft_eval.run_record` keeps a typed,
#: shared empty mapping rather than a bare `{}` at every default site.
_NO_QUESTION_SCORES: Final[Mapping[str, PerQuestionScores]] = MappingProxyType({})

#: `ScoredRun.token_usage`'s own default — `role_tokens`'s own reasoning one level up: a run
#: that asked no model has `{}`, never `None` (`None` is `RunRecord.token_usage`'s own,
#: different claim: *not recorded at all*).
_NO_TOKEN_USAGE: Final[Mapping[str, RoleTokens]] = MappingProxyType({})


def role_tokens(entries: Sequence[UsageEntry]) -> Mapping[str, RoleTokens]:
    """`entries`, folded to one `RoleTokens` per `UsageEntry.role` — task **33.7**.

    `calls` counts every entry for the role, whether or not its provider reported usage;
    `calls_not_reporting` counts the ones whose `usage` is `None`. Token sums are taken only
    over entries that did report — the module docstring's own rule: a role a provider cannot
    meter is a call not reporting, never a call that cost zero tokens.
    """
    totals: dict[str, dict[str, int]] = {}
    for entry in entries:
        bucket = totals.setdefault(
            entry.role,
            {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "calls_not_reporting": 0},
        )
        bucket["calls"] += 1
        if entry.usage is None:
            bucket["calls_not_reporting"] += 1
        else:
            bucket["prompt_tokens"] += entry.usage.prompt_tokens
            bucket["completion_tokens"] += entry.usage.completion_tokens
    return {role: RoleTokens(**counts) for role, counts in totals.items()}


@dataclass(frozen=True)
class ScoredRun:
    """What `score_pipeline` measured, and the query rung it measured it with — task 16.1.

    Three facts rather than one return value, because a record needs all three and deriving
    any of them anywhere else would mean re-deriving what this function already computed once.
    `question_scores` — task 16.4 — is keyed identically to `metrics`: one `PerQuestionScores`
    per metric name, built from the same `harness.score_retrieval_gate_subset` call `metrics`
    already comes from.
    """

    metrics: Mapping[str, Outcome[MetricAggregate]]
    query_rung: ScoredQueryRung
    #: Defaulted to `{}` — every construction site written before this task named only
    #: `metrics`/`query_rung`, and `{}` is the honest reading for a fake collaborator that
    #: never scored a real question (`tests/unit/weft_cli/test_eval_commands.py`'s own
    #: `_fake_score_pipeline`), the same posture `RunRecord.metrics` already takes for a run
    #: given no `--questions` at all.
    question_scores: Mapping[str, PerQuestionScores] = _NO_QUESTION_SCORES
    #: Repair **R38.1** — each question's own axes, keyed identically to `question_scores`:
    #: `{**question.axes}` plus `"kind": question.kind.value` when the question stated one.
    #: `None` only for a construction site written before this repair — `score_pipeline` always
    #: fills it, the identical posture `question_seconds` already takes one field below.
    question_axes: Mapping[str, Mapping[str, str]] | None = None
    #: Task **39.2** — each question's own `Passages.contributors`, keyed identically to
    #: `question_scores`; `None` when the run scored no retrieval rung (a generating rung's
    #: `Answer` and the hardwired `run_ask` search state no arm) or predates this task.
    question_contributors: Mapping[str, tuple[str, ...]] | None = None
    #: Task **16.6** — the identity of the question set these scores are over, `""` when no
    #: questions were scored at all. `""` rather than `None` because a `ScoredRun` that scored
    #: nothing has no question set, and `RunRecord.question_set_digest` is where the *record's*
    #: three-state absence lives; two nullable layers would say the same thing twice.
    question_set: str = ""
    #: Task **33.7** — each question's own retrieval latency, keyed identically to
    #: `question_scores`. `score_pipeline` always measures, so this is `None` only for a
    #: construction site written before this task (`ScoredRun.question_seconds`'s own,
    #: different absence claim lives on `RunRecord`, one layer up).
    question_seconds: PerQuestionSeconds | None = None
    #: Task **33.7** — what each model role spent across the run. `{}` for a run that asked
    #: no model, `role_tokens`'s own default one level up.
    token_usage: Mapping[str, RoleTokens] = _NO_TOKEN_USAGE
    #: Task **40.2** — every packed chunk `score_pipeline` retrieved for each question, best-first,
    #: when `capture_pool=True` on the retrieval-rung path. `None` when capture was not asked for.
    question_pools: Mapping[str, tuple[PoolChunk, ...]] | None = None
    #: Task **40.2** — the store's own row count at capture time, read once after the question
    #: loop. `None` when capture was not asked for.
    store_rows: int | None = None


def _merge_generation_scores(
    generation_scores: SubsetScores,
    *,
    metrics: dict[str, Outcome[MetricAggregate]],
    per_question: dict[str, Mapping[str, QuestionOutcome]],
) -> None:
    """Fold `score_generation_gate_subset`'s own `SubsetScores` into `score_pipeline`'s
    retrieval-side `metrics`/`per_question`, in place — task **32.14**.

    `ctx` reaches `score_generation_gate_subset` exactly as `score_pipeline` received it:
    `embedding-similarity`'s own `ctx.require(Embedder)` finds nothing on it, because FF22
    (`docs/internal/build-ledger.md` task 9.0) pins every `ServiceRegistry` a shipped run
    assembles to three named assemblers, and `score_pipeline` is deliberately not a fourth. That
    metric's `evaluate` raises `UnresolvedServiceError`, which `score_generation_gate_subset`
    already catches and reports as `Failed` for itself alone, naming why — visible in the
    record, never a crash and never a silent absence indistinguishable from "this run has no
    reference answers." Wiring a real `Embedder` onto this path is unbuilt, and belongs in
    `weft_engine.run_services` if it is ever done, not here.

    Raises `CollidingScoreNameError` for a name a retrieval metric already reported — see that
    error's own docstring for why one contract's own collision guard is not enough once the two
    are merged into one `ScoredRun`.
    """
    for name, aggregate_outcome in generation_scores.metrics.items():
        if name in metrics:
            raise CollidingScoreNameError(
                f"a retrieval metric and a generation metric both report '{name}' in this "
                f"run. A scored run keys both its aggregates and its per-question scores "
                f"by the name a metric computes, so one would silently replace the other. "
                f"Have one pack's metric report a name of its own.",
                name=name,
            )
        metrics[name] = aggregate_outcome
        per_question[name] = generation_scores.per_question[name]


def _resolved_cutoffs(cutoffs: tuple[int, ...] | None, *, top_k: int) -> tuple[int, ...]:
    """`cutoffs`, defaulted to `(top_k,)` — ledger task 40.1. `top_k` is always the depth the
    ranking is collapsed to, so a caller naming a largest cutoff that disagrees with it is
    asking for a depth no ranking was ever collapsed to.
    """
    resolved = cutoffs if cutoffs is not None else (top_k,)
    if max(resolved) != top_k:
        raise ValueError(
            f"cutoffs {resolved} name a largest cutoff of {max(resolved)}, which does not "
            f"match top_k={top_k} — top_k is the depth the ranking is collapsed to."
        )
    return resolved


def _require_capturable_rung(capture_pool: bool, *, is_retrieval_rung: bool) -> None:
    """`capture_pool=True`'s own pre-flight — ledger task 40.2. A pool is what a retrieval rung
    packed; neither a generating rung nor the no-query-rung path has one to keep.
    """
    if capture_pool and not is_retrieval_rung:
        raise ValueError(
            "capture_pool=True requires a retrieval rung (a query_pipeline ending in something "
            "other than a Generator) — a pool is what a retrieval rung packed, and neither a "
            "generating rung nor the no-query-rung path has one."
        )


async def _captured_store_rows(
    capture_pool: bool, retrieval_services: PreparedRunner | None
) -> int | None:
    """`retrieval_services.store`'s own row count, read once after the question loop, only when
    `capture_pool` asked for it — task **40.2**. `retrieval_services` is never `None` when
    `capture_pool` is `True`: `_require_capturable_rung` already refused any other case, and
    `retrieval_services` is set on exactly the branch that check requires.
    """
    if not capture_pool:
        return None
    prepared = cast("PreparedRunner", retrieval_services)
    return await cast("NodeStore", prepared.store).count()


def _pool_chunks_of(hits: Sequence[Scored[Node]]) -> tuple[PoolChunk, ...]:
    """`hits`, already in ranking order (`_scored_in_ranking_order`), as `PoolChunk`s — task
    **40.2**. Never re-derives an order; the caller's own order is kept exactly.
    """
    return tuple(
        PoolChunk(
            node_id=str(hit.value.id),
            document_id=_document_id_of(hit),
            content_sha256=hashlib.sha256(hit.value.content.encode("utf-8")).hexdigest(),
            score=hit.score,
        )
        for hit in hits
    )


def _record_captured_chunks(
    pools: dict[str, tuple[PoolChunk, ...]],
    question_key: str,
    hits: Sequence[Scored[Node]],
    *,
    capture_pool: bool,
) -> None:
    """Record `question_key`'s pool into `pools`, in place, when `capture_pool` asked for it."""
    if capture_pool:
        pools[question_key] = _pool_chunks_of(hits)


def _require_replayable_rung(pool: LoadedPool | None, *, is_retrieval_rung: bool) -> None:
    """`pool=...`'s own pre-flight — ledger task **40.2**'s second half, `_require_capturable_
    rung`'s own shape one clause down. A pool is captured from a retrieval rung, so it can only
    be replayed through one: neither a generating rung nor the no-query-rung path has a rung it
    could rerank through.
    """
    if pool is not None and not is_retrieval_rung:
        raise ValueError(
            "pool=... requires a retrieval rung (a query_pipeline ending in something other "
            "than a Generator) — a pool is captured from a retrieval rung, and neither a "
            "generating rung nor the no-query-rung path has one to replay it through."
        )


async def _check_pool_before_loop(
    pool: LoadedPool, questions: Sequence[Question], store: NodeStore
) -> Mapping[str, PoolQuestion]:
    """Every fact `pool` and `questions` must agree on before a single question replays — see
    `weft_eval.pool.PoolIntegrityError`'s own docstring. Returns each asked question's own
    `PoolQuestion`, keyed by id, so the question loop below looks it up once rather than
    re-searching `pool.manifest.questions` per question.

    Raises `PoolIntegrityError` naming the first offending question id for a question the
    manifest does not hold, a manifest question this run does not ask, a question whose text or
    relevant-document set has drifted since capture, or a store whose row count no longer
    matches what the pool was captured against.
    """
    manifest_by_id = {entry.id: entry for entry in pool.manifest.questions}
    asked_ids = {question.id for question in questions}
    for question in questions:
        if question.id not in manifest_by_id:
            raise PoolIntegrityError(
                f"question '{question.id}' is asked here but is not in the captured pool — a "
                f"replay can only score the questions its capture run asked.",
                question=question.id,
            )
    for entry in pool.manifest.questions:
        if entry.id not in asked_ids:
            raise PoolIntegrityError(
                f"the captured pool holds question '{entry.id}', which this replay's own "
                f"question file does not ask — a replay must ask exactly the questions it "
                f"captured, no more and no fewer.",
                question=entry.id,
            )
    for question in questions:
        entry = manifest_by_id[question.id]
        if text_sha256(question.text) != entry.text_sha256:
            raise PoolIntegrityError(
                f"question '{question.id}' text has changed since capture — it no longer "
                f"hashes to the text the pool was captured against.",
                question=question.id,
            )
        if relevant_set_sha256(question.relevant_documents) != entry.relevant_sha256:
            raise PoolIntegrityError(
                f"question '{question.id}' relevant document set has changed since capture — "
                f"it no longer hashes to the relevant set the pool was captured against.",
                question=question.id,
            )
    actual_rows = await store.count()
    if actual_rows != pool.manifest.store_rows:
        raise PoolIntegrityError(
            f"the store now holds {actual_rows} row(s), but the pool was captured against a "
            f"store holding {pool.manifest.store_rows} row(s) — a replay must hydrate chunks "
            f"from the identical store it was captured from."
        )
    return manifest_by_id


async def _check_pool_after_loop(pool: LoadedPool, store: NodeStore) -> None:
    """The store's row count, checked once more after every question replayed — see
    `_check_pool_before_loop`'s own docstring for the identical check one call earlier.
    """
    actual_rows = await store.count()
    if actual_rows != pool.manifest.store_rows:
        raise PoolIntegrityError(
            f"the store now holds {actual_rows} row(s), but the pool was captured against a "
            f"store holding {pool.manifest.store_rows} row(s) — something changed the store "
            f"while this replay ran."
        )


async def _hydrated_ranking(
    question: Question, entry: PoolQuestion, *, store: NodeStore, corpus_digest: str
) -> Ranking:
    """`entry`'s own captured chunks, hydrated from `store` by id and rebuilt into a `Ranking` a
    reranking rung can run — ledger task **40.2**'s second half. Never searches: every chunk is
    read back by the node id the capture run recorded, in the capture's own order, so `rank`
    below is that order and never a re-derived one.

    Raises `PoolIntegrityError` naming `question.id` and the chunk's node id for a chunk the
    store no longer holds, or whose content no longer hashes to what was captured.
    """
    nodes = await store.get([NodeId(chunk.node_id) for chunk in entry.chunks])
    node_by_id = {str(node.id): node for node in nodes}
    hits: list[Passage] = []
    for rank, chunk in enumerate(entry.chunks):
        node = node_by_id.get(chunk.node_id)
        if node is None:
            raise PoolIntegrityError(
                f"question '{question.id}' names chunk '{chunk.node_id}', which the store no "
                f"longer holds.",
                question=question.id,
                chunk=chunk.node_id,
            )
        actual_hash = hashlib.sha256(node.content.encode("utf-8")).hexdigest()
        if actual_hash != chunk.content_sha256:
            raise PoolIntegrityError(
                f"question '{question.id}' names chunk '{chunk.node_id}', whose content no "
                f"longer hashes to what the pool captured.",
                question=question.id,
                chunk=chunk.node_id,
            )
        hits.append(
            Passage(scored=Scored(value=node, score=chunk.score), rank=rank, retrieved_by="pool")
        )
    return Ranking(
        origin=Query(text=question.text),
        hits=tuple(hits),
        ext={
            PoolQuestionEntry.__namespace__: PoolQuestionEntry(
                corpus_digest=corpus_digest,
                question_id=question.id,
                text_sha256=entry.text_sha256,
            )
        },
    )


async def _generating_question_hits(
    question: Question,
    *,
    query_pipeline: str,
    registry: Registry,
    reports: Sequence[PackReport],
    ctx: Context,
    llm: LLMSection | None,
    services: ServiceSelection | None,
    roles: RoleTable | None,
    sink: TokenSink | None,
    contributions: tuple[Contribution, ...],
    generation_samples: list[tuple[str, GenerationSample]],
) -> Sequence[Scored[Node]]:
    """One question's own hits, on a generating rung — `run_named_ask`, and the `GenerationSample`
    `score_pipeline`'s own docstring says every answered question builds. Lifted out of the
    per-question loop so that loop's own branching stays inside `score_pipeline`'s complexity
    budget; raises `PipelineDidNotProduceError`/`weft_llm.errors.LLMGenerationLoopError`
    unchanged, for the caller's own per-question exclusion.
    """
    answer = await run_named_ask(
        question.text,
        pipeline_name=query_pipeline,
        registry=registry,
        reports=reports,
        ctx=ctx,
        llm=llm if llm is not None else LLMSection(),
        services=services if services is not None else ServiceSelection(),
        roles=roles if roles is not None else RoleTable(),
        sink=sink if sink is not None else NullSink(),
        contributions=contributions,
    )
    used_passages = passages_for_scoring(answer)
    hits = _scored_in_ranking_order(used_passages)
    generation_samples.append(
        (
            question.id,
            GenerationSample(
                query=question.text,
                # `getattr`, not `answer.text` — the identical seam `passages_for_scoring`'s
                # own docstring argues for `used`: a test's duck-typed stand-in carrying no
                # `text` is "no prediction to evaluate" (`GenerationSample.prediction`'s own
                # `None` state), never a crash reading an attribute it never promised to carry.
                prediction=getattr(answer, "text", None),
                reference=question.reference_answer or "",
                contexts=tuple(passage.node.content for passage in used_passages),
                language=question.language,
            ),
        )
    )
    return hits


async def _pool_question_hits(
    question: Question,
    entry: PoolQuestion,
    *,
    query_pipeline: str,
    pool: LoadedPool,
    registry: Registry,
    reports: Sequence[PackReport],
    ctx: Context,
    llm: LLMSection | None,
    services: ServiceSelection | None,
    roles: RoleTable | None,
    sink: TokenSink | None,
    contributions: tuple[Contribution, ...],
    retrieval_services: PreparedRunner | None,
    contributors: dict[str, tuple[str, ...]],
) -> Sequence[Scored[Node]]:
    """One question's own hits, replayed from a captured pool — `_hydrated_ranking` reads the
    manifest's own chunks back by id, and `run_named_rerank` runs them through the rerank
    document `query_pipeline` names. Raises `PoolIntegrityError` for a chunk the store no longer
    holds or agrees with (never caught by the caller's own per-question exclusion — see that
    error's own docstring), and `PipelineDidNotProduceError`/`LLMGenerationLoopError` unchanged,
    for the caller's own per-question exclusion.
    """
    ranking = await _hydrated_ranking(
        question,
        entry,
        store=cast("NodeStore", cast("PreparedRunner", retrieval_services).store),
        corpus_digest=pool.manifest.corpus_digest,
    )
    passages = await run_named_rerank(
        ranking,
        pipeline_name=query_pipeline,
        registry=registry,
        reports=reports,
        ctx=ctx,
        llm=llm if llm is not None else LLMSection(),
        services=services if services is not None else ServiceSelection(),
        roles=roles if roles is not None else RoleTable(),
        sink=sink if sink is not None else NullSink(),
        contributions=contributions,
        prepared=retrieval_services,
    )
    contributors[question.id] = tuple(passages.contributors)
    return _scored_in_ranking_order(passages.passages)


async def _retrieval_question_hits(
    question_text: str,
    *,
    question_key: str,
    query_pipeline: str,
    registry: Registry,
    reports: Sequence[PackReport],
    ctx: Context,
    llm: LLMSection | None,
    services: ServiceSelection | None,
    roles: RoleTable | None,
    sink: TokenSink | None,
    contributions: tuple[Contribution, ...],
    retrieval_services: PreparedRunner | None,
    contributors: dict[str, tuple[str, ...]],
    question_pools: dict[str, tuple[PoolChunk, ...]],
    capture_pool: bool,
) -> Sequence[Scored[Node]]:
    """One question's own hits, on an ordinary retrieval rung — `run_named_retrieve`, unchanged
    from before this function was lifted out of `score_pipeline`'s own per-question loop.
    """
    passages = await run_named_retrieve(
        question_text,
        pipeline_name=query_pipeline,
        registry=registry,
        reports=reports,
        ctx=ctx,
        llm=llm if llm is not None else LLMSection(),
        services=services if services is not None else ServiceSelection(),
        roles=roles if roles is not None else RoleTable(),
        sink=sink if sink is not None else NullSink(),
        contributions=contributions,
        prepared=retrieval_services,
    )
    contributors[question_key] = tuple(passages.contributors)
    hits = _scored_in_ranking_order(passages.passages)
    _record_captured_chunks(question_pools, question_key, hits, capture_pool=capture_pool)
    return hits


def _resolved_query_rung(
    query_pipeline: str | None,
    *,
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...],
    embed_stage: ResolvedStage,
    store_stage: ResolvedStage,
) -> tuple[ScoredQueryRung, bool]:
    """`query_pipeline`, resolved to the `ScoredQueryRung` a `RunRecord` persists, and whether it
    generates — task **16.1**'s own resolution, lifted out of `score_pipeline` so its own
    branching stays inside that function's complexity budget.
    """
    if query_pipeline is None:
        return (
            NoQueryRung(
                reason=(
                    "no query rung was named — retrieval ran against the ingest pipeline's own "
                    f"Embedder ('{embed_stage.use}') and NodeStore ('{store_stage.use}') stages"
                )
            ),
            False,
        )
    resolved_rung = resolve_named_pipeline(
        query_pipeline, registry=registry, reports=reports, contributions=contributions
    )
    generates = bool(resolved_rung.stages) and resolved_rung.stages[-1].contract == "Generator"
    return QueryRung(name=query_pipeline, identity=pipeline_identity(resolved_rung)), generates


def _document_id_resolver(
    questions: tuple[Question, ...],
    *,
    document_labels: Mapping[str, str] | None,
    corpus_document_ids: Sequence[str],
) -> Callable[[str], str]:
    """A `question.relevant_documents` entry, resolved to the corpus document id it names —
    task **16.5**/**38.11**'s own two-stage resolution, lifted out of `score_pipeline` so its own
    branching stays inside that function's complexity budget. See `score_pipeline`'s own
    docstring for what `document_labels` does.
    """
    all_labels = {label for question in questions for label in question.relevant_documents}
    manifest_labelled = (
        _labelled_by_manifest(all_labels, document_labels) if document_labels is not None else None
    )
    labels_to_resolve = (
        set(manifest_labelled.values()) if manifest_labelled is not None else all_labels
    )
    resolved_labels = resolve_labels(labels_to_resolve, corpus_document_ids=corpus_document_ids)

    def _resolved(entry: str) -> str:
        label = manifest_labelled[entry] if manifest_labelled is not None else entry
        return resolved_labels[label]

    return _resolved


async def _prepared_retrieval(
    stack: AsyncExitStack,
    *,
    query_pipeline: str | None,
    generates: bool,
    pool: LoadedPool | None,
    questions: tuple[Question, ...],
    registry: Registry,
    reports: Sequence[PackReport],
    ctx: Context,
    llm: LLMSection | None,
    services: ServiceSelection | None,
    sink: TokenSink | None,
    roles: RoleTable | None,
) -> tuple[PreparedRunner | None, Mapping[str, PoolQuestion] | None]:
    """The `PreparedRunner` a retrieval rung or a replay needs, and — only for a replay — every
    asked question's own `PoolQuestion`, checked once against `pool` and the store before the
    first question runs. Lifted out of `score_pipeline` so its own branching stays inside that
    function's complexity budget; see `_check_pool_before_loop`'s own docstring for what a
    replay refuses here.
    """
    retrieval_services: PreparedRunner | None = None
    if query_pipeline is not None and not generates:
        retrieval_services = await stack.enter_async_context(
            prepared_services(
                registry=registry,
                reports=reports,
                ctx=ctx,
                llm=llm if llm is not None else LLMSection(),
                services=services if services is not None else ServiceSelection(),
                sink=sink if sink is not None else NullSink(),
                roles=roles if roles is not None else RoleTable(),
            )
        )
    pool_questions_by_id: Mapping[str, PoolQuestion] | None = None
    if pool is not None:
        pool_questions_by_id = await _check_pool_before_loop(
            pool, questions, cast("NodeStore", cast("PreparedRunner", retrieval_services).store)
        )
    return retrieval_services, pool_questions_by_id


def _question_axes(
    question: Question, pool_questions_by_id: Mapping[str, PoolQuestion] | None
) -> Mapping[str, str]:
    """One question's own axes — its stated axes, plus `"kind"` when it named one, plus
    `"rule-fires"` when this is a pool replay (`weft_eval.pool.PoolQuestion.rule_fires`). Lifted
    out of `score_pipeline`'s own per-question loop for the identical, complexity-budget reason.
    """
    axes = (
        {**question.axes, "kind": question.kind.value}
        if question.kind is not None
        else dict(question.axes)
    )
    if pool_questions_by_id is not None:
        axes["rule-fires"] = "true" if pool_questions_by_id[question.id].rule_fires else "false"
    return axes


async def _score_retrieval(
    registry: Registry,
    samples: Sequence[RetrievalSample],
    *,
    cutoffs: tuple[int, ...],
    ctx: Context,
    failed_questions: Mapping[str, str],
) -> SubsetScores:
    """One cutoff is today's single `score_retrieval_gate_subset` call; several go through
    `weft_eval.harness.score_retrieval_at_cutoffs`, which gives the same result for one."""
    if len(cutoffs) == 1:
        return await score_retrieval_gate_subset(
            registry, samples, top_k=cutoffs[0], ctx=ctx, failed_questions=failed_questions
        )
    return await score_retrieval_at_cutoffs(
        registry, samples, cutoffs=cutoffs, ctx=ctx, failed_questions=failed_questions
    )


async def score_pipeline(
    *,
    registry: Registry,
    resolved_pipeline: ResolvedPipeline,
    questions: tuple[Question, ...],
    top_k: int,
    cutoffs: tuple[int, ...] | None = None,
    ctx: Context,
    corpus_document_ids: Sequence[str],
    query_pipeline: str | None = None,
    reports: Sequence[PackReport] = (),
    llm: LLMSection | None = None,
    services: ServiceSelection | None = None,
    roles: RoleTable | None = None,
    sink: TokenSink | None = None,
    contributions: tuple[Contribution, ...] = (),
    document_labels: Mapping[str, str] | None = None,
    refuse_foreign_documents: bool = False,
    capture_pool: bool = False,
    pool: LoadedPool | None = None,
) -> ScoredRun:
    """Retrieve for every one of `questions` and score the gate-safe `RetrievalMetric` subset
    over the result. Returns a `ScoredRun`: the scores, and the query rung they were scored
    with.

    **`refuse_foreign_documents`, task 38.0.** `False` (the default) is exactly today's
    behaviour, unchanged: `weft eval run` scores whatever a hit names. `True` — asked only by
    `weft eval experiment`, whose arms share one store — raises `ForeignDocumentRetrievedError`
    the moment a retrieved hit's own document is not in `corpus_document_ids`, before it ever
    reaches `_deduplicated_by_document`: see that error's own docstring for why a hit from
    another arm's corpus must not silently score as a miss.

    **`query_pipeline`, ledger task 7.5 — the query rung Phase 8's exit needed measurable.**
    `None` (the default) is exactly today's behaviour, unchanged: `run_ask`, plain vector
    top-k, against `resolved_pipeline`'s own `Embedder`/`NodeStore` stages. Given a name
    instead, `query_pipeline` is resolved once (below) and *what it ends in* decides how every
    question runs through it — task **R38.0**: a rung whose last stage is a `Generator` is asked
    through `weft_cli.route_ask.run_named_ask`, exactly as before, and scored over
    `passages_for_scoring(answer)` — the passages that entered the prompt, never the ranking
    underneath it. Any other rung is run through `weft_cli.route_ask.run_named_retrieve` and
    scored over the passages it packed, calling no model — which a rung ending in a
    `ContextPacker` produces; one ending in a `Retriever` or a `Fuser` produces `Candidates` or
    a `Ranking` and `run_named_retrieve` refuses it, the refusal `weft eval experiment` makes
    before any index for the same reason. `run_named_ask` requires an `Answer` and refused a
    packer-ending rung outright, which is what left an experiment's earlier arms with orphaned
    records once a later arm named one. `reports`/`llm`/`services`/`sink`/`contributions` are
    only read on this path — `weft_cli.eval_commands.EvalRunCommand.run` already has all five
    in scope from its own `Dependencies`, the identical set `run_named_ask`'s other caller,
    `AskCommand`, already threads through.

    **Task 16.1 — one resolution answers for both the run and the record.** When `query_pipeline`
    is given, it is resolved exactly once, before the question loop, through
    `weft_cli.route_ask.resolve_named_pipeline` — the same `resolve_in_catalogue` every
    per-question `run_named_ask` call below resolves through — and `ScoredRun.query_rung`
    carries `QueryRung(name=query_pipeline, identity=pipeline_identity(resolved))`. The
    per-question `run_named_ask` calls are unchanged: they resolve again internally, and
    `resolve` is pure, so the identity recorded is the identity each question actually ran
    under, never a second, possibly-divergent resolution's. When `query_pipeline` is `None`,
    `ScoredRun.query_rung` is a `NoQueryRung` naming what retrieved instead — the ingest
    pipeline's own `Embedder`/`NodeStore` stages — because that absence is itself a
    measurement, not a gap: see `weft_eval.run_record.NoQueryRung`'s own docstring.

    **A question a query rung raises on excludes it — repair R38.12.** `run_named_retrieve`/
    `run_named_ask` raising `PipelineDidNotProduceError` for one question no longer aborts the
    whole run: that question is caught, carries no `RetrievalSample` and no `question_seconds`
    entry, and is passed to `score_retrieval_gate_subset` as a `failed_questions` entry, which
    turns it into `NotScored` under every metric and counts it in `excluded` — `09` V4's "a
    failed metric is an error, never a zero" one level up. Repair R39.1 folds
    `LLMGenerationLoopError` into the same exclusion — the loop-breaker's verdict on one
    question's prompt, which retrying "is likely to loop again" — and nothing else from
    `weft_llm.errors`, because a credential or quota fault fails every question alike. Any
    other exception propagates.

    Raises `PipelineNotRetrievableError` if `resolved_pipeline` (the *ingest* pipeline
    `--questions` was corroborated over) names no `Embedder`/`NodeStore` stage — checked
    unconditionally, whether or not `query_pipeline` is given: a query rung has nothing to
    retrieve unless the corpus was actually indexed and stored first, so this refusal must
    not narrow just because a second pipeline is now doing the retrieving. An empty
    `questions` tuple still calls through — `weft_eval.harness.score_retrieval_gate_subset`
    already answers that honestly, one place rather than two.

    **`corpus_document_ids`, task 16.5 — resolved here, once, never inside a metric.**
    `question.relevant_documents` holds labels an author wrote by hand; a hit is attributed to
    a resolved absolute path (`_document_id_of`). `weft_cli.eval_scoring.resolve_labels` turns
    every label this run's questions use into the corpus document id it names, in one call
    *before* the question loop below — the label vocabulary is the same for every question, so
    resolving per question would raise the same refusal N times and redo the same work N times.
    Each `RetrievalSample.relevant_ids` is then the frozenset of *resolved document ids*, never
    of labels, so every metric downstream goes on doing exact set membership on document ids
    exactly as it does today. This lives here and not inside a metric for `weft_eval.baseline`'s
    own reason, one layer up: `Hit`'s docstring already argues "a metric that had to know about
    file paths would be a metric that stops working the day the corpus moves" — the identical
    argument against teaching a metric a path-matching rule instead of a plain set comparison.

    **`document_labels`, task 38.11 — the manifest-id path.** `eval/questions/*.toml` names a
    `relevant_documents` entry by manifest id, never by path, so a caller holding the manifest
    (`weft_eval.corpus_manifest.load_manifest`) passes `{doc.id: <corpus-relative path>, ...}`
    here and every entry is mapped through it, via `_labelled_by_manifest`, *before*
    `resolve_labels` ever sees it. `None` — every call site before this task — is unchanged:
    entries are labels exactly as `resolve_labels` has always read them.

    **A generating rung's own answer is scored against the reference answer too — task 32.14.**
    Before this task, a generating rung's `Answer.text` was read only for `passages_for_scoring`
    and then discarded, so no `GenerationMetric` — `token-recall`, `rouge-l`, every one of the
    32.0 catalogue's "generation-only" entries — was ever computed in a real run. Every gate-safe
    `GenerationMetric` is now scored beside the retrieval metrics, over one `GenerationSample`
    per successfully-answered question (`weft_eval.harness.score_generation_gate_subset`), and
    merged into this same `ScoredRun`. Only *gate-safe* metrics run here, unconditionally: a
    judge metric needs a model of its own and is priced and asked for separately, exactly as
    `score_retrieval_gate_subset` already restricts the retrieval side — this function invents
    no second rule for the generation half of the same contract split. A retrieval rung or the
    no-query-rung path builds no `GenerationSample` and computes no generation metric at all,
    because neither one ever calls a `Generator`. See `_merge_generation_scores`'s own docstring
    for why `ctx` reaches it unchanged, and what that costs `embedding-similarity` specifically.

    **`cutoffs`, ledger task 40.1.** `None` (the default) scores at `top_k` alone, exactly
    today's behaviour — and with one cutoff (`None`, or a one-member tuple) this calls
    `weft_eval.harness.score_retrieval_gate_subset` exactly as before, byte-for-byte the same
    call, so nothing that patches or reads that one call site changes. `top_k` stays the depth
    every ranking is collapsed to (`_deduplicated_by_document` below runs once, unchanged).
    Given a tuple of more than one cutoff, `weft_eval.harness.score_retrieval_at_cutoffs` scores
    the same collapsed samples once per declared cutoff, merging by what each metric's own name
    says about it. `max(cutoffs)` must equal `top_k`, since a cutoff no ranking was collapsed to
    could never be read from it.

    **`capture_pool`, ledger task 40.2.** `False` (the default) is unchanged. `True` is only
    honoured on the retrieval-rung path (`query_pipeline` given, ending in something other than a
    `Generator`) — a generating rung has no ranking beneath the passages it packed and the
    no-query-rung path retrieves through no named pipeline at all, so a pool captured from either
    would name a rung `weft_eval.experiment` never asked for; both raise `ValueError` immediately,
    before anything runs. On the retrieval-rung path, `ScoredRun.question_pools` carries every
    question's packed chunks in ranking order (`_scored_in_ranking_order`, not the document-
    deduplicated `top_k`), and `ScoredRun.store_rows` carries `retrieval_services.store`'s own
    `count()`, read once after the question loop.

    **`pool`, ledger task 40.2's second half.** `None` (the default) is unchanged. Given a
    `weft_eval.pool.LoadedPool` instead, every question is replayed rather than retrieved: no
    `run_named_retrieve`, no `run_ask`, no embedder call and no search. `_check_pool_before_loop`
    refuses, before the first question runs, a question the manifest does not hold, a manifest
    question this run does not ask, a question whose text or relevant set has drifted, or a
    store whose row count already disagrees with the manifest's own `store_rows`.
    `_hydrated_ranking` then reads each question's own captured chunks back from the store by id
    — never searches — and rebuilds them into a `Ranking` carrying a `weft_eval.pool.
    PoolQuestionEntry` under `ext`, so a stage downstream can tell which pool question it is
    looking at even when two questions share one text. That `Ranking` runs through
    `weft_cli.route_ask.run_named_rerank`, the rerank document `query_pipeline` names — which
    must end in a `ContextPacker`, the identical shape `run_named_retrieve` requires, since a
    pool is retrieval-rung data. `_check_pool_after_loop` repeats the row-count check once
    every question has run. Every one of these raises `weft_eval.pool.PoolIntegrityError`, which
    propagates out of this function whole — never a per-question exclusion, because it means the
    replay itself cannot be trusted, not that one question's stage refused. `capture_pool=True`
    together with `pool` raises `ValueError`: a replay reads a pool, it never writes one.
    """
    if capture_pool and pool is not None:
        raise ValueError(
            "capture_pool and pool are mutually exclusive — a replay reads a pool, it never "
            "writes one."
        )
    resolved_cutoffs = _resolved_cutoffs(cutoffs, top_k=top_k)

    embed_stage = _stage_for_contract(resolved_pipeline, Embedder.__name__)
    store_stage = _stage_for_contract(resolved_pipeline, NodeStore.__name__)
    if embed_stage is None or store_stage is None:
        missing = "Embedder" if embed_stage is None else "NodeStore"
        raise PipelineNotRetrievableError(
            f"pipeline '{resolved_pipeline.name}' has no stage registered under the "
            f"{missing} contract, so --questions has nothing to retrieve against.",
            pipeline=resolved_pipeline.name,
        )

    query_rung, generates = _resolved_query_rung(
        query_pipeline,
        registry=registry,
        reports=reports,
        contributions=contributions,
        embed_stage=embed_stage,
        store_stage=store_stage,
    )

    # Task 38.11 — `weft_eval.question_set.Question.id` is required, so every question has an
    # identity and keying is never by position.
    keyed_by = QuestionKey.QUESTION_ID

    _resolved_document_id = _document_id_resolver(
        questions, document_labels=document_labels, corpus_document_ids=corpus_document_ids
    )

    samples: list[RetrievalSample] = []
    generation_samples: list[tuple[str, GenerationSample]] = []
    seconds: dict[str, float] = {}
    axes: dict[str, Mapping[str, str]] = {}
    contributors: dict[str, tuple[str, ...]] = {}
    is_retrieval_rung = query_pipeline is not None and not generates
    is_generating_rung = query_pipeline is not None and generates
    _require_capturable_rung(capture_pool, is_retrieval_rung=is_retrieval_rung)
    _require_replayable_rung(pool, is_retrieval_rung=is_retrieval_rung)
    failed: dict[str, str] = {}
    question_pools: dict[str, tuple[PoolChunk, ...]] = {}
    store_rows: int | None = None
    # R38.6: one store for the run, so no question's seconds include a connection and its DDL.
    async with AsyncExitStack() as stack:
        retrieval_services, pool_questions_by_id = await _prepared_retrieval(
            stack,
            query_pipeline=query_pipeline,
            generates=generates,
            pool=pool,
            questions=questions,
            registry=registry,
            reports=reports,
            ctx=ctx,
            llm=llm,
            services=services,
            sink=sink,
            roles=roles,
        )
        with recording_usage() as tally:
            for question in questions:
                question_key = question.id
                question_text = question.text
                question_kind = (
                    question.kind.value
                    if question.kind is not None
                    else question.axes.get("kind", "")
                )
                axes[question_key] = _question_axes(question, pool_questions_by_id)
                hits: Sequence[Scored[Node]]
                started = time.monotonic()
                try:
                    if query_pipeline is not None and generates:
                        hits = await _generating_question_hits(
                            question,
                            query_pipeline=query_pipeline,
                            registry=registry,
                            reports=reports,
                            ctx=ctx,
                            llm=llm,
                            services=services,
                            roles=roles,
                            sink=sink,
                            contributions=contributions,
                            generation_samples=generation_samples,
                        )
                    elif pool is not None:
                        pool_entry = cast("Mapping[str, PoolQuestion]", pool_questions_by_id)[
                            question_key
                        ]
                        hits = await _pool_question_hits(
                            question,
                            pool_entry,
                            query_pipeline=cast("str", query_pipeline),
                            pool=pool,
                            registry=registry,
                            reports=reports,
                            ctx=ctx,
                            llm=llm,
                            services=services,
                            roles=roles,
                            sink=sink,
                            contributions=contributions,
                            retrieval_services=retrieval_services,
                            contributors=contributors,
                        )
                    elif query_pipeline is not None:
                        hits = await _retrieval_question_hits(
                            question_text,
                            question_key=question_key,
                            query_pipeline=query_pipeline,
                            registry=registry,
                            reports=reports,
                            ctx=ctx,
                            llm=llm,
                            services=services,
                            roles=roles,
                            sink=sink,
                            contributions=contributions,
                            retrieval_services=retrieval_services,
                            contributors=contributors,
                            question_pools=question_pools,
                            capture_pool=capture_pool,
                        )
                    else:
                        hits = await run_ask(
                            question_text,
                            registry=registry,
                            ctx=ctx,
                            top_k=top_k * _OVERSAMPLE_FACTOR,
                            embedder=embed_stage.use,
                            store=store_stage.use,
                            embedder_config=_factory_config(embed_stage.config),
                            store_config=_factory_config(store_stage.config),
                        )
                except (PipelineDidNotProduceError, LLMGenerationLoopError) as failure:
                    failed[question_key] = str(failure)
                    continue
                seconds[question_key] = time.monotonic() - started
                if refuse_foreign_documents:
                    _refuse_foreign_documents(hits, corpus_document_ids=corpus_document_ids)
                samples.append(
                    RetrievalSample(
                        query=question_text,
                        question_key=question_key,
                        retrieved=_deduplicated_by_document(_ranked_by_score(hits), top_k=top_k),
                        # A replay's own `hits` is whatever the capture run happened to pack for
                        # this one question, never a fresh search — the pool's `store_rows` is
                        # the honest depth a metric named `@k` should compare `k` against
                        # (`weft_eval.ir_metrics`'s own module docstring, R38.5): the corpus this
                        # rung was captured over, not how many of its chunks one question's own
                        # ranking happened to keep.
                        candidate_count=len(hits),
                        relevant_ids=frozenset(
                            _resolved_document_id(entry) for entry in question.relevant_documents
                        ),
                        modality=question.modality,
                        kind=question_kind,
                        axes=question.axes,
                    )
                )
        store_rows = await _captured_store_rows(capture_pool, retrieval_services)
        if pool is not None:
            await _check_pool_after_loop(
                pool, cast("NodeStore", cast("PreparedRunner", retrieval_services).store)
            )

    scores = await _score_retrieval(
        registry, samples, cutoffs=resolved_cutoffs, ctx=ctx, failed_questions=failed
    )
    metrics: dict[str, Outcome[MetricAggregate]] = dict(scores.metrics)
    per_question: dict[str, Mapping[str, QuestionOutcome]] = dict(scores.per_question)
    if is_generating_rung:
        generation_scores = await score_generation_gate_subset(
            registry, generation_samples, ctx=ctx, failed_questions=failed
        )
        _merge_generation_scores(generation_scores, metrics=metrics, per_question=per_question)
    question_scores = {
        name: PerQuestionScores(keyed_by=keyed_by, scores=outcomes)
        for name, outcomes in per_question.items()
    }
    return ScoredRun(
        metrics=metrics,
        query_rung=query_rung,
        question_scores=question_scores,
        question_axes=axes,
        question_contributors=contributors if is_retrieval_rung else None,
        question_set=question_set_digest(questions),
        question_seconds=PerQuestionSeconds(keyed_by=keyed_by, seconds=seconds),
        token_usage=role_tokens(tally.entries),
        question_pools=question_pools if capture_pool else None,
        store_rows=store_rows if capture_pool else None,
    )


__all__ = [
    "AmbiguousLabelError",
    "AnswerCarriesNoUsedPassagesError",
    "CollidingScoreNameError",
    "ForeignDocumentRetrievedError",
    "PipelineNotRetrievableError",
    "ScoredRun",
    "UnresolvableLabelError",
    "passages_for_scoring",
    "resolve_labels",
    "role_tokens",
    "score_pipeline",
]
