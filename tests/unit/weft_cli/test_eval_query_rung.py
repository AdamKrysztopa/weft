"""`weft eval` can judge a **query** rung — ledger task **7.5**, discharging Phase 8's exit.

Phase 8's Exit asks that `weft eval` report whether the difference between two of *those rungs* —
the query rungs of the clause above it — falls outside the interval a published baseline recorded.
Re-checking that exit on a real wheel install found four clauses of five are facts and the fifth is
not. Every box under Phase 8 was honestly ticked and both halves are individually demonstrable; the
word that failed is the conjunction (`docs/internal/lessons.md` `L8.29`).

**Two things blocked it, and only the second is interesting.** `weft eval run` refuses a query
pipeline outright — *"has no stage registered under the Extractor contract"* — which is a
reasonable thing for a command that also indexes. The real one is underneath:
`weft_cli.eval_scoring.score_retrieval` pulls the `Embedder` and `NodeStore` stages out of the
pipeline it was given and calls `run_ask`, which is **plain vector top-k, every time**. So no
`Retriever`, `Fuser`, `ContextPacker` or `Generator` choice has ever been the thing measured, and
`hybrid-then-generate` and `retrieve-then-generate` would have scored identically because neither
was ever run.

**What a query rung is scored over is `Answer.used`**, and that is not a convenience — it is what
that field's own docstring already says it is for: *"exactly the passages that entered the prompt …
what a reader needs to judge the answer without re-running the pipeline"*. Scoring the ranking
instead would measure something the generator never saw.

**This is the honest subject and it is narrower than "run the rung".** The retrieval metrics judge
what came back; whether the *answer* is good is `GenerationMetric`'s question and needs a real
model, which `09` §4.4 deliberately keeps out of the gate. So this task makes a query rung
*measurable*, which is what Phase 8's exit asks, and does not claim the generation half.

**Ledger task 16.1 corrects one sentence below.** `test_eval_run_can_name_a_query_rung`'s own
docstring said *"the ingest pipeline … is what a baseline is keyed on; the query rung is what is
being compared"* — true of the command surface and false of the persisted record, which carried no
query rung at all, so `weft eval compare --baseline` counted two runs of two different query rungs
as repetitions of each other. A rung the record does not name is a rung no comparison can tell
apart, and the tests at the foot of this file are that gap closed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from pydantic import BaseModel

from weft_cli import eval_scoring as eval_scoring_module
from weft_cli import route_ask as route_ask_module
from weft_cli.eval_commands import EvalRunArgs
from weft_cli.eval_scoring import score_pipeline
from weft_cli.route_ask import resolve_named_pipeline, run_named_ask, run_named_retrieve
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_engine.llm_roles import LLMSection
from weft_engine.services import ServiceSelection
from weft_eval.harness import SubsetScores
from weft_eval.question_set import Question, QuestionField
from weft_eval.run_record import NoQueryRung, QueryRung
from weft_generate import CitedAnswer, Generator
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt
from weft_kernel.context import Context
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage, pipeline_identity
from weft_llm.client import NullSink
from weft_prompts.contract import Prompt
from weft_retrieve import ContextPacker, Fuser, NoRetrieval, Repack, Retriever, SingleList
from weft_store import NodeStore


def _question(identifier: str, text: str, relevant_documents: tuple[str, ...] = ()) -> Question:
    """The one question model, stating absent every field this fixture does not need."""
    return Question.model_validate(
        {
            "id": identifier,
            "text": text,
            "language": "en",
            "relevant_documents": relevant_documents,
            "absent": frozenset(QuestionField),
            "absent_reason": "a scoring fixture",
        }
    )


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _stub_catalogue(catalogue: dict[str, Pipeline]) -> Callable[..., dict[str, Pipeline]]:
    def _full_catalogue(
        *, directory: Path = Path("pipelines"), reports: Sequence[object] = ()
    ) -> dict[str, Pipeline]:
        del directory, reports
        return catalogue

    return _full_catalogue


def _ingest_resolved() -> ResolvedPipeline:
    """The *ingest* pipeline a run was corroborated over — it must carry an `Embedder` and a
    `NodeStore`, because `score_pipeline` refuses one that does not.
    """
    return ResolvedPipeline(
        name="index-text",
        stages=(
            ResolvedStage(
                id="embed",
                contract=Embedder.__name__,
                use="hash",
                distribution="weft-rag",
                provenance="index-text",
            ),
            ResolvedStage(
                id="store",
                contract=NodeStore.__name__,
                use="pgvector",
                distribution="weft-rag",
                provenance="index-text",
            ),
        ),
    )


class _FakeAnswer(BaseModel):
    """Shaped like what `passages_for_scoring` reads, and nothing more."""

    used: tuple[object, ...] = ()


async def _no_metrics(*_args: object, **_kwargs: object) -> SubsetScores:
    """`score_retrieval_gate_subset` stubbed out: these tests are about the rung, not the score.

    It returns the real `SubsetScores`, not a bare mapping — task 16.4 changed that function's
    return type, and a stub still answering the old shape is a double narrower than the thing
    it stands in for in exactly the dimension nobody was looking at.
    """
    return SubsetScores(metrics={}, per_question={})


async def _no_hits(*_args: object, **_kwargs: object) -> Sequence[object]:
    return ()


def test_eval_run_can_name_a_query_rung() -> None:
    """The command surface half — a query pipeline is a subject the command accepts.

    A separate field rather than overloading `pipeline`: the two are different roles in one run.
    The ingest pipeline says what was indexed; the query rung is what is being compared. Folding
    them into one positional would make *"which of these two did I change?"* unanswerable from a
    persisted record — which it was anyway until task **16.1**, because only the ingest half
    reached the record.
    """
    fields = EvalRunArgs.model_fields

    assert "query_pipeline" in fields, (
        "weft eval run cannot name a query rung, so Phase 8's exit clause has no subject"
    )
    assert fields["query_pipeline"].default is None, (
        "a query rung must be optional — every baseline taken before this task named none, and "
        "they stay readable"
    )
    assert fields["pipeline"].is_required(), "the ingest pipeline is still what a run indexes with"


@pytest.mark.asyncio
async def test_a_query_rung_is_scored_over_what_it_actually_used() -> None:
    """The half that matters: the rung runs, and what *it* retrieved is what is judged.

    Asserted through the seam rather than end-to-end, because an end-to-end run needs a container
    and a model and this property needs neither: the question is whether the passages handed to the
    metrics came from the rung's own `Answer.used` or from a plain vector search underneath it.
    """
    from weft_cli.eval_scoring import passages_for_scoring

    # `retrieved_by` rather than an invented field: the stand-in is duck-typed, but the
    # *return* type is the real `Passage`, so an assertion on a field `Passage` does not have
    # would force the function to widen to `Any` and give up saying what it hands back.
    class _Passage(BaseModel):
        retrieved_by: str

    class _Answer(BaseModel):
        used: tuple[_Passage, ...]

    answer = _Answer(used=(_Passage(retrieved_by="vector-top-k"), _Passage(retrieved_by="hybrid")))

    scored = passages_for_scoring(answer)

    assert [passage.retrieved_by for passage in scored] == ["vector-top-k", "hybrid"], (
        "the rung's own used passages are not what reaches the metrics, so a query rung would be "
        "scored on something it did not produce"
    )


def test_the_scorer_still_refuses_a_pipeline_it_cannot_retrieve_with() -> None:
    # The existing refusal is unchanged: an ingest pipeline with no Embedder/NodeStore still has
    # nothing to retrieve against, and that message names the missing contract. A new capability
    # must not quietly widen what an old failure accepts.
    from weft_cli.eval_scoring import PipelineNotRetrievableError

    assert issubclass(PipelineNotRetrievableError, Exception)


# --- Task 16.1 — the rung reaches the record, and one resolution answers for both.


class _SentinelError(Exception):
    """Raised by a stubbed `resolve_in_catalogue` so a caller that reached it can be seen."""


def _query_document(*, name: str = "rung-a", top_n: int | None = None) -> Pipeline:
    """`retrieve-then-generate`'s own four stages — the shipped query rung's shape.

    **Four stages, not two, and that is a repair.** This began as `retrieve` → `generate`,
    which `weft_kernel.resolution._check_composition` refuses unconditionally: `Retriever` is
    `Stage[QuerySet, Candidates]` and `Generator` is `Stage[Passages, Answer]`, so a `Fuser`
    and a `ContextPacker` have to bridge them. It was written from the contracts' prose instead
    of from `tests/unit/weft_cli/test_route_ask.py:108 "def _registry"`, the existing double of
    this exact seam — `docs/internal/lessons.md` `L11.17`. It was the implementer refusing to
    edit a test to clear its own path that surfaced it.
    """
    pack = (
        StageDeclaration(id="pack", use="repack")
        if top_n is None
        else StageDeclaration(id="pack", use="repack", config={"top_n": top_n})
    )
    return Pipeline(
        name=name,
        stages=(
            StageDeclaration(id="retrieve", use="no-retrieval"),
            StageDeclaration(id="fuse", use="single-list"),
            pack,
            StageDeclaration(id="generate", use="cited-answer"),
        ),
    )


class _FakeStore:
    """A `NodeStore` stand-in.

    `no-retrieval`, `single-list`, `repack` and `cited-answer` call no store method at all — copied
    from `test_route_ask.py`'s double of the same seam rather than written from `NodeStore`'s prose.
    """


def _fake_store_factory(config: object) -> _FakeStore:
    del config
    return _FakeStore()


def _query_registry() -> Registry:
    """`test_route_ask.py:108 "def _registry"`'s registry, minus the routing plugins these reach.

    The `Embedder` and `NodeStore` are here because `run_named_ask` assembles services before it
    resolves anything, so a registry without them fails inside `build_services` rather than at the
    resolution these tests are about.
    """
    registry = Registry()
    registry.add(Embedder, "fake-embed", HashEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "fake-store", _fake_store_factory, distribution="weft-store")
    registry.add(Retriever, "no-retrieval", NoRetrieval, distribution="weft-retrieve")
    registry.add(Fuser, "single-list", SingleList, distribution="weft-retrieve")
    registry.add(ContextPacker, "repack", Repack, distribution="weft-retrieve")
    registry.add(Generator, "cited-answer", CitedAnswer, distribution="weft-generate")
    registry.add(
        Prompt, ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt, distribution="weft-generate"
    )
    return registry


async def test_one_resolution_answers_both_the_run_and_the_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identity a record carries must come from the resolution the questions ran under.

    Asserted behaviourally rather than by reading the source: the shared resolution is stubbed to
    raise, and **both** the path that answers *"what is this rung's identity"* and the path that
    actually runs a question must fail with it. A second, independent resolution would sail past.
    `L9.79` is the rule — where a value's whole job is to travel, one test watches it travel.
    """

    # Arrange
    def _explode(*_args: object, **_kwargs: object) -> object:
        raise _SentinelError

    monkeypatch.setattr(route_ask_module, "resolve_in_catalogue", _explode)
    monkeypatch.setattr(
        route_ask_module, "full_catalogue", _stub_catalogue({"rung-a": _query_document()})
    )
    registry = _query_registry()

    # Act / Assert — the identity path.
    with pytest.raises(_SentinelError):
        resolve_named_pipeline("rung-a", registry=registry, reports=())

    # Act / Assert — the path a question takes.
    with pytest.raises(_SentinelError):
        await run_named_ask(
            "why",
            pipeline_name="rung-a",
            registry=registry,
            reports=(),
            ctx=_ctx(),
            llm=LLMSection(),
            # The names this registry actually holds — `test_route_ask.py`'s own selection.
            # A default `ServiceSelection()` asks for `pgvector`, and the run then fails in
            # service assembly before it reaches any resolution at all.
            services=ServiceSelection(embed="fake-embed", store="fake-store"),
            sink=NullSink(),
        )


async def test_a_named_rung_is_recorded_by_name_and_by_an_identity_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rung's identity is the rung's, never the ingest pipeline's.

    The confusion a naive implementation makes is to stamp the identity already in scope — the
    *ingest* pipeline's, which `weft index` records on every `SourceRecord`. Asserting only that
    the field is non-empty would pass against that, so the assertion is that the two differ.
    """
    # Arrange
    monkeypatch.setattr(
        route_ask_module, "full_catalogue", _stub_catalogue({"rung-a": _query_document()})
    )
    registry = _query_registry()
    ingest = _ingest_resolved()

    async def _answer(*_args: object, **_kwargs: object) -> object:
        return _FakeAnswer(used=())

    monkeypatch.setattr(eval_scoring_module, "run_named_ask", _answer)
    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _no_metrics)

    # Act
    scored = await score_pipeline(
        registry=registry,
        resolved_pipeline=ingest,
        questions=(_question("q-1", "why"),),
        top_k=3,
        ctx=_ctx(),
        query_pipeline="rung-a",
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert isinstance(scored.query_rung, QueryRung)
    assert scored.query_rung.name == "rung-a"
    assert scored.query_rung.identity != pipeline_identity(ingest), (
        "the record carries the ingest pipeline's identity under the query rung's name, so two "
        "runs of two different rungs over one index would be indistinguishable"
    )


async def test_naming_no_rung_is_recorded_as_a_measurement_not_as_an_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--query-pipeline` absent means plain vector top-k against the ingest pipeline's own
    stages — a thing that ran, and the thing every baseline taken so far ran. It must not
    persist as the same value a record written before 16.1 carries.
    """
    # Arrange
    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _no_metrics)
    monkeypatch.setattr(eval_scoring_module, "run_ask", _no_hits)

    # Act
    scored = await score_pipeline(
        registry=_query_registry(),
        resolved_pipeline=_ingest_resolved(),
        questions=(_question("q-1", "why"),),
        top_k=3,
        ctx=_ctx(),
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert isinstance(scored.query_rung, NoQueryRung)
    assert scored.query_rung.reason, "a run that named no rung must say what retrieved instead"


async def test_two_rungs_differing_only_in_configuration_are_not_one_rung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name is not an identity: two documents can carry one name across two projects, and one
    document can change under its own name. The identity is what `--baseline` will key on.
    """
    # Arrange — the same four stages, one `with:` value apart.
    plain = _query_document()
    configured = _query_document(top_n=3)
    registry = _query_registry()

    # Act
    monkeypatch.setattr(route_ask_module, "full_catalogue", _stub_catalogue({"rung-a": plain}))
    first = resolve_named_pipeline("rung-a", registry=registry, reports=())
    monkeypatch.setattr(route_ask_module, "full_catalogue", _stub_catalogue({"rung-a": configured}))
    second = resolve_named_pipeline("rung-a", registry=registry, reports=())

    # Assert
    assert pipeline_identity(first) != pipeline_identity(second)


# --- Repair R38.6 — what a query rung's services open, the run closes.


class _CountedStores:
    """A `NodeStore` factory that counts what it built and what was closed.

    `PgVectorStore` opens one Postgres connection per instance and releases it only in `aclose`;
    `38.5`'s hybrid arm built one per question, closed none, and exhausted a 100-connection server
    part-way through its first record. A store that holds no socket is the right double: the defect
    is the lifetime, not the connection.
    """

    def __init__(self) -> None:
        self.built = 0
        self.closed = 0

    def factory(self, config: object) -> _ClosableStore:
        del config
        self.built += 1
        return _ClosableStore(self)


class _ClosableStore:
    def __init__(self, counts: _CountedStores) -> None:
        self._counts = counts

    async def aclose(self) -> None:
        self._counts.closed += 1


def _retrieval_document(name: str = "rung-r") -> Pipeline:
    """`_query_document` without its `Generator`: a rung ending in a `ContextPacker`, the shape
    `weft eval experiment`'s arms run through `run_named_retrieve`.
    """
    return Pipeline(
        name=name,
        stages=(
            StageDeclaration(id="retrieve", use="no-retrieval"),
            StageDeclaration(id="fuse", use="single-list"),
            StageDeclaration(id="pack", use="repack"),
        ),
    )


def _counted_registry(counts: _CountedStores) -> Registry:
    registry = Registry()
    registry.add(Embedder, "fake-embed", HashEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "counted-store", counts.factory, distribution="weft-store")
    registry.add(Retriever, "no-retrieval", NoRetrieval, distribution="weft-retrieve")
    registry.add(Fuser, "single-list", SingleList, distribution="weft-retrieve")
    registry.add(ContextPacker, "repack", Repack, distribution="weft-retrieve")
    return registry


async def test_a_named_retrieval_closes_every_store_it_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`weft ask --retrieve-only --pipeline` and every REPL turn go through this function, so a
    store it builds and never closes is a connection held until the garbage collector happens by.
    """
    # Arrange
    counts = _CountedStores()
    monkeypatch.setattr(
        route_ask_module, "full_catalogue", _stub_catalogue({"rung-r": _retrieval_document()})
    )
    registry = _counted_registry(counts)

    # Act
    for _ in range(2):
        await run_named_retrieve(
            "why",
            pipeline_name="rung-r",
            registry=registry,
            reports=(),
            ctx=_ctx(),
            llm=LLMSection(),
            services=ServiceSelection(embed="fake-embed", store="counted-store"),
            sink=NullSink(),
        )

    # Assert
    assert counts.built > 0
    assert counts.closed == counts.built, (
        f"built {counts.built} stores and closed {counts.closed}: each unclosed pgvector store "
        "holds a Postgres connection past the call that opened it"
    )


async def test_scoring_a_retrieval_rung_builds_its_store_once_and_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One store for the whole run, not one per question: a store's first search provisions its
    schema, so a per-question store puts that DDL and a connection handshake inside every
    question's recorded seconds, and 1,548 of them is what reached the connection limit.
    """
    # Arrange
    counts = _CountedStores()
    monkeypatch.setattr(
        route_ask_module, "full_catalogue", _stub_catalogue({"rung-r": _retrieval_document()})
    )
    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _no_metrics)
    questions = tuple(_question(f"q-{index}", "why") for index in range(3))

    # Act
    await score_pipeline(
        registry=_counted_registry(counts),
        resolved_pipeline=_ingest_resolved(),
        questions=questions,
        top_k=3,
        ctx=_ctx(),
        query_pipeline="rung-r",
        services=ServiceSelection(embed="fake-embed", store="counted-store"),
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert counts.built == 1, f"built {counts.built} stores for {len(questions)} questions"
    assert counts.closed == 1
