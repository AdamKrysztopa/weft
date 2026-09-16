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

import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, Final, cast

from pydantic import BaseModel

from weft_cli.ask import run_ask
from weft_cli.route_ask import resolve_named_pipeline, run_named_ask, run_named_retrieve
from weft_embed import Embedder
from weft_engine.llm_roles import LLMSection
from weft_engine.service_roles import RoleTable
from weft_engine.services import ServiceSelection
from weft_eval.aggregate import MetricAggregate
from weft_eval.contract import RetrievalSample, RetrievedPassage
from weft_eval.harness import score_retrieval_gate_subset
from weft_eval.question_set import Question, question_set_digest
from weft_eval.run_record import (
    NoQueryRung,
    PerQuestionScores,
    PerQuestionSeconds,
    QueryRung,
    QuestionKey,
    RoleTokens,
    ScoredQueryRung,
)
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Node, Outcome
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution, ResolvedPipeline, ResolvedStage, pipeline_identity
from weft_llm.client import NullSink
from weft_llm.contract import TokenSink
from weft_llm.usage import UsageEntry, recording_usage
from weft_retrieve.payload import Passage
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


async def score_pipeline(
    *,
    registry: Registry,
    resolved_pipeline: ResolvedPipeline,
    questions: tuple[Question, ...],
    top_k: int,
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

    query_rung: ScoredQueryRung
    generates = False
    if query_pipeline is not None:
        resolved_rung = resolve_named_pipeline(
            query_pipeline,
            registry=registry,
            reports=reports,
            contributions=contributions,
        )
        generates = bool(resolved_rung.stages) and resolved_rung.stages[-1].contract == "Generator"
        query_rung = QueryRung(name=query_pipeline, identity=pipeline_identity(resolved_rung))
    else:
        query_rung = NoQueryRung(
            reason=(
                "no query rung was named — retrieval ran against the ingest pipeline's own "
                f"Embedder ('{embed_stage.use}') and NodeStore ('{store_stage.use}') stages"
            )
        )

    # Task 38.11 — `weft_eval.question_set.Question.id` is required, so every question has an
    # identity and keying is never by position.
    keyed_by = QuestionKey.QUESTION_ID

    all_labels = {label for question in questions for label in question.relevant_documents}
    manifest_labelled = (
        _labelled_by_manifest(all_labels, document_labels) if document_labels is not None else None
    )
    labels_to_resolve = (
        set(manifest_labelled.values()) if manifest_labelled is not None else all_labels
    )
    resolved_labels = resolve_labels(labels_to_resolve, corpus_document_ids=corpus_document_ids)

    def _resolved_document_id(entry: str) -> str:
        label = manifest_labelled[entry] if manifest_labelled is not None else entry
        return resolved_labels[label]

    samples: list[RetrievalSample] = []
    seconds: dict[str, float] = {}
    axes: dict[str, Mapping[str, str]] = {}
    with recording_usage() as tally:
        for question in questions:
            question_key = question.id
            question_text = question.text
            question_kind = (
                question.kind.value if question.kind is not None else question.axes.get("kind", "")
            )
            axes[question_key] = (
                {**question.axes, "kind": question.kind.value}
                if question.kind is not None
                else {**question.axes}
            )
            hits: Sequence[Scored[Node]]
            started = time.monotonic()
            if query_pipeline is not None and generates:
                answer = await run_named_ask(
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
                )
                seconds[question_key] = time.monotonic() - started
                hits = [passage.scored for passage in passages_for_scoring(answer)]
            elif query_pipeline is not None:
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
                )
                seconds[question_key] = time.monotonic() - started
                hits = [passage.scored for passage in passages.passages]
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
                seconds[question_key] = time.monotonic() - started
            if refuse_foreign_documents:
                _refuse_foreign_documents(hits, corpus_document_ids=corpus_document_ids)
            samples.append(
                RetrievalSample(
                    query=question_text,
                    question_key=question_key,
                    retrieved=_deduplicated_by_document(_ranked_by_score(hits), top_k=top_k),
                    candidate_count=len(hits),
                    relevant_ids=frozenset(
                        _resolved_document_id(entry) for entry in question.relevant_documents
                    ),
                    modality=question.modality,
                    kind=question_kind,
                    axes=question.axes,
                )
            )

    scores = await score_retrieval_gate_subset(registry, samples, top_k=top_k, ctx=ctx)
    question_scores = {
        name: PerQuestionScores(keyed_by=keyed_by, scores=outcomes)
        for name, outcomes in scores.per_question.items()
    }
    return ScoredRun(
        metrics=scores.metrics,
        query_rung=query_rung,
        question_scores=question_scores,
        question_axes=axes,
        question_set=question_set_digest(questions),
        question_seconds=PerQuestionSeconds(keyed_by=keyed_by, seconds=seconds),
        token_usage=role_tokens(tally.entries),
    )


__all__ = [
    "AmbiguousLabelError",
    "AnswerCarriesNoUsedPassagesError",
    "ForeignDocumentRetrievedError",
    "PipelineNotRetrievableError",
    "ScoredRun",
    "UnresolvableLabelError",
    "passages_for_scoring",
    "resolve_labels",
    "role_tokens",
    "score_pipeline",
]
