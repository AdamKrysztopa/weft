"""Unit tests for `weft_cli.eval_scoring`.

Mirrors `packages/weft-rag/src/weft_cli/eval_scoring.py`. Reading a question file is
`weft_eval.question_set`'s, since task 38.11 moved the binary onto that one model, and is tested in
`tests/unit/weft_eval/test_question_set_model.py`. `score_pipeline` is exercised against fakes for
`Embedder`/`NodeStore` — `weft_cli.ask`'s own `test_ask.py`'s convention, since the property under
test is that this module retrieves through the *resolved pipeline's own* stages (never `[services]`)
and folds the result into a real `weft_eval.harness.score_retrieval_gate_subset` report — plus the
edge case (a pipeline naming no `Embedder`/`NodeStore` stage refuses outright rather than silently
reporting empty metrics indistinguishable from "no --questions given").
"""

import hashlib
from collections.abc import Sequence

import pytest

from weft_cli import eval_scoring as eval_scoring_module
from weft_cli.eval_scoring import (
    AmbiguousLabelError,
    ForeignDocumentRetrievedError,
    PipelineNotRetrievableError,
    UnresolvableLabelError,
    resolve_labels,
    score_pipeline,
)
from weft_cli.route_ask import PipelineDidNotProduceError
from weft_embed import Embedder
from weft_eval import Settings, register
from weft_eval.contract import RetrievalSample
from weft_eval.harness import SubsetScores
from weft_eval.question_set import Kind, Question, QuestionField, question_set_digest
from weft_eval.run_record import NotScored, QuestionKey
from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import (
    Lineage,
    MediaType,
    Node,
    Outcome,
    Produced,
    SourceId,
    Vector,
)
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_llm.errors import LLMAuthenticationError, LLMGenerationLoopError
from weft_retrieve.payload import Passage, Passages, Query
from weft_store import Filter, NodeStore, Scored


class _FakeEmbedder:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=[node.with_embedding(Vector(values=(1.0,))) for node in payload])


class _FakeVectorSearchStore:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del vector, top_k, filter
        found = Node.synthetic(
            content="a stored passage", media_type=MediaType.TEXT, reason="fixture"
        ).model_copy(
            update={"lineage": Lineage.derived(parents=(), sources=frozenset({SourceId("doc-a")}))}
        )
        return [Scored(value=found, score=0.9)]

    async def count(self) -> int:
        return 7


def _registry() -> Registry:
    registry = Registry()
    registry.add(Embedder, "hash", _FakeEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _FakeVectorSearchStore, distribution="weft-store")
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


def _resolved_pipeline(*, with_stages: bool = True) -> ResolvedPipeline:
    stages = (
        (
            ResolvedStage(
                id="embed",
                contract="Embedder",
                use="hash",
                distribution="weft-embed",
                provenance="index",
            ),
            ResolvedStage(
                id="store",
                contract="NodeStore",
                use="pgvector",
                distribution="weft-store",
                provenance="index",
            ),
        )
        if with_stages
        else ()
    )
    return ResolvedPipeline(name="index", stages=stages)


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


_ABSENT_BUT_KIND: frozenset[QuestionField] = frozenset(
    {
        QuestionField.DIFFICULTY,
        QuestionField.QUOTE,
        QuestionField.REFERENCE_ANSWER,
        QuestionField.NOTES,
    }
)


def _question(
    identifier: str = "q-1",
    *,
    text: str = "q",
    relevant_documents: tuple[str, ...] = ("doc-a",),
    kind_axis: str | None = None,
) -> Question:
    """A `weft_eval.question_set.Question` stating every field a scoring fixture does not need
    absent — the one model `score_pipeline` reads since task 38.11."""
    return Question.model_validate(
        {
            "id": identifier,
            "text": text,
            "language": "en",
            "relevant_documents": relevant_documents,
            "absent": _ABSENT_BUT_KIND | {QuestionField.KIND},
            "absent_reason": "a scoring fixture",
            "axes": {} if kind_axis is None else {"kind": kind_axis},
        }
    )


# --- score_pipeline --------------------------------------------------------------------------


async def test_score_pipeline_retrieves_and_scores_against_the_resolved_stages() -> None:
    # Arrange — one question whose relevant document is exactly what the fake store returns.
    questions = (_question(),)

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a", "doc-b"),
    )

    # Assert — the one retrieved passage is the one relevant document: precision@1 = 1.0.
    # Task 16.1 moved the metrics behind `ScoredRun.metrics`: this function now answers for the
    # query rung it scored with as well as for the scores, because the record needs both.
    assert "precision@1" in report.metrics
    outcome = report.metrics["precision@1"]
    assert isinstance(outcome, Produced)
    assert outcome.value.mean == 1.0


async def test_score_pipeline_refuses_a_pipeline_with_no_store_stage() -> None:
    # Arrange
    questions = (_question(),)

    # Act / Assert
    with pytest.raises(PipelineNotRetrievableError) as excinfo:
        await score_pipeline(
            registry=_registry(),
            resolved_pipeline=_resolved_pipeline(with_stages=False),
            questions=questions,
            top_k=1,
            ctx=_ctx(),
            corpus_document_ids=("doc-a", "doc-b"),
        )
    assert excinfo.value.pipeline == "index"


# --- Task 16.4 — a question has an identity, or its position is named as such.


async def test_scores_are_keyed_by_question_id_when_the_file_carries_them() -> None:
    # Arrange
    questions = (
        _question("fetch-001"),
        _question("fetch-002", text="q2"),
    )

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a", "doc-b"),
    )

    # Assert
    scores = report.question_scores
    assert scores is not None
    precision = scores["precision@1"]
    assert precision.keyed_by is QuestionKey.QUESTION_ID
    assert set(precision.scores) == {"fetch-001", "fetch-002"}


# --- Task 16.5 — a label written in the tree finds its document on any machine.


def _corpus() -> tuple[str, ...]:
    """A staged corpus, as `IndexResult.document_ids` reports it: resolved absolute paths."""
    return (
        "/somewhere/corpus/arxiv/1304.7717v2.pdf",
        "/somewhere/corpus/arxiv/1411.2331v1.pdf",
        "/somewhere/corpus/pl-wiki/kraków.txt",
    )


def test_a_corpus_relative_label_finds_its_document_wherever_it_is_staged() -> None:
    """The property, and it is about two machines rather than one.

    Ground truth is written once and read wherever the corpus is staged, so a label cannot
    carry a root. `weft_eval.baseline.Hit`'s own docstring states the principle this resolves
    under: *"a metric that had to know about file paths would be a metric that stops working
    the day the corpus moves"* — so the resolution happens once, here, and every metric goes on
    comparing document ids exactly.
    """
    # Arrange — the same corpus staged under two different roots.
    here = _corpus()
    there = tuple(path.replace("/somewhere", "/elsewhere/checkout") for path in here)

    # Act
    resolved_here = resolve_labels(("arxiv/1304.7717v2.pdf",), corpus_document_ids=here)
    resolved_there = resolve_labels(("arxiv/1304.7717v2.pdf",), corpus_document_ids=there)

    # Assert — one label, two stagings, and in each it names that staging's own document.
    assert resolved_here["arxiv/1304.7717v2.pdf"] == here[0]
    assert resolved_there["arxiv/1304.7717v2.pdf"] == there[0]


def test_a_label_matches_only_at_a_path_component_boundary() -> None:
    """`7717v2.pdf` is not a corpus-relative path, it is the tail of a filename. Matching it
    would make `.pdf` match every PDF in the corpus, which is the failure mode a suffix rule
    has and a component-wise one does not.
    """
    # Act / Assert
    with pytest.raises(UnresolvableLabelError):
        resolve_labels(("7717v2.pdf",), corpus_document_ids=_corpus())


def test_a_bare_filename_still_resolves_when_it_names_one_document() -> None:
    """A filename *is* a corpus-relative path when the corpus is flat, and most are. The rule
    is about component boundaries, not about requiring a directory.
    """
    # Act
    resolved = resolve_labels(("1411.2331v1.pdf",), corpus_document_ids=_corpus())

    # Assert
    assert resolved["1411.2331v1.pdf"] == "/somewhere/corpus/arxiv/1411.2331v1.pdf"


def test_a_label_naming_no_document_is_refused_rather_than_scored_zero() -> None:
    """The defect this rule exists for, and the ledger records it as a scar
    (`docs/internal/build-ledger.md:5528 "an early run read"`): *"an early run read `0.000` at
    every cutoff and was not reported as a finding — ground truth names a `SourceDoc.source_id`,
    and bare filenames match nothing."* A `0.000` meaning *the harness is wrong* and a `0.000`
    meaning *the architecture fails* are indistinguishable in a report.
    """
    # Act / Assert
    with pytest.raises(UnresolvableLabelError) as excinfo:
        resolve_labels(("ax-1304.7717v2",), corpus_document_ids=_corpus())
    message = str(excinfo.value)
    assert "ax-1304.7717v2" in message, "the refusal does not name the label that failed"
    assert "arxiv/1304.7717v2.pdf" in message, (
        "`01` requirement 5: a name that does not resolve says what the valid options are"
    )


def test_a_label_matching_two_documents_is_refused_naming_both() -> None:
    """Ambiguity is silent otherwise: whichever document the resolution happened to pick would
    score, and the other would count as a miss for a question that named it.
    """
    # Arrange — the same filename under two directories, which a staged corpus can hold.
    corpus = (
        "/somewhere/corpus/a/notes.txt",
        "/somewhere/corpus/b/notes.txt",
    )

    # Act / Assert
    with pytest.raises(AmbiguousLabelError) as excinfo:
        resolve_labels(("notes.txt",), corpus_document_ids=corpus)
    message = str(excinfo.value)
    assert "a/notes.txt" in message
    assert "b/notes.txt" in message


def test_a_label_that_is_the_whole_resolved_path_still_resolves() -> None:
    """Every questions file written before this task names absolute paths, because that is
    what `SourceId` is. They keep working — the rule is a suffix rule and a whole path is its
    own suffix.
    """
    # Act
    resolved = resolve_labels(
        ("/somewhere/corpus/pl-wiki/kraków.txt",), corpus_document_ids=_corpus()
    )

    # Assert
    assert resolved["/somewhere/corpus/pl-wiki/kraków.txt"] == _corpus()[2]


async def test_a_question_is_scored_against_the_document_its_label_resolved_to() -> None:
    """The wire: the resolution reaches the metric, so a hit on the labelled document counts.

    Before this task the label and the hit id were compared as raw strings — a manifest id
    against a resolved absolute path — and every question scored `0.000`.
    """
    # Arrange
    questions = (_question(),)

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a", "doc-b"),
    )

    # Assert
    outcome = report.metrics["precision@1"]
    assert isinstance(outcome, Produced)
    assert outcome.value.mean == 1.0


# --- Task 16.7 — a rank metric scores a ranking the packer did not reverse.


async def test_a_rank_metric_sees_retrieval_order_not_the_packers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`12` §3: *"Rank metrics are scored over `repack: reverse`'s deliberately inverted
    order."* `Answer.used` is the right **set** — task 7.5 settled that, and it is what the
    generator actually saw — but it is not a ranking once the packer has reversed it. `repack`'s
    default *is* `reverse` (best hit last, immediately before the question), so every rank
    metric on the named-rung path scored the inversion of the ranking retrieval produced.

    Fixed where the sample is built, not in the metrics: a metric that had to know about packing
    order would be a metric that breaks the day a new packer ships.
    """
    # Arrange — the rung answers worst-first, exactly as `repack: reverse` leaves it.
    captured: list[RetrievalSample] = []

    def _passage(source: str, score: float, rank: int) -> Passage:
        """A real `Passage`, because that is what `passages_for_scoring` hands back — the
        existing double of this seam rather than one written from the contract (`L11.17`).
        """
        node = Node.synthetic(
            content=source, media_type=MediaType.TEXT, reason="fixture"
        ).model_copy(
            update={"lineage": Lineage.derived(parents=(), sources=frozenset({SourceId(source)}))}
        )
        return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by="fixture")

    async def _reversed_answer(*_args: object, **_kwargs: object) -> Answer:
        return Answer(
            text="an answer",
            origin=Query(text="q"),
            answered_by="fixture",
            used=(
                _passage("doc-worst", 0.1, 2),
                _passage("doc-middle", 0.5, 1),
                _passage("doc-best", 0.9, 0),
            ),
        )

    async def _capture(_registry: object, samples: Sequence[RetrievalSample], **_kw: object):
        captured.extend(samples)
        return SubsetScores(metrics={}, per_question={})

    monkeypatch.setattr(eval_scoring_module, "run_named_ask", _reversed_answer)
    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _capture)

    # Task 16.1 resolves the named rung once before the question loop, so a test naming a rung
    # has to get past that call. Stubbed rather than satisfied with a real catalogue and a
    # registry carrying the whole query side: *that* resolution is
    # `test_eval_query_rung.py`'s property, asserted there against the real plugins, and this
    # test is about the order the metrics see. Stubbing `run_named_ask` alone left the earlier
    # call to refuse `'some-rung'` before anything under test ran.
    def _resolved_rung(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        # Repair R38.0: a rung is asked for an answer only when it ends in a `Generator`, so the
        # stub states that last stage rather than resolving to no stages at all.
        return _rung("Retriever", "Fuser", "ContextPacker", "Generator")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved_rung)

    # Act
    await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(_question(relevant_documents=("doc-best",)),),
        top_k=3,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-best", "doc-middle", "doc-worst"),
    )

    # Repair R38.5 — the sample says how many candidates the ranking was collapsed from.
    assert captured[0].candidate_count == 3
    # Assert — best first, which is what `mrr`, `ndcg` and `mean_average_precision` all read.
    assert [passage.id for passage in captured[0].retrieved] == [
        "doc-best",
        "doc-middle",
        "doc-worst",
    ]


# --- Task 38.11 — one question model reaches the scorer.


async def test_a_manifest_id_is_scored_against_the_document_its_manifest_names() -> None:
    """`eval/questions/*.toml` names documents by manifest id, and a corpus is staged by path. The
    manifest is the one place that says which path an id is, so `document_labels` carries that
    mapping to the label resolution every other question already goes through."""
    # Arrange
    questions = (_question(relevant_documents=("ax-a",)),)

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a", "doc-b"),
        document_labels={"ax-a": "doc-a", "ax-b": "doc-b"},
    )

    # Assert
    outcome = report.metrics["precision@1"]
    assert isinstance(outcome, Produced)
    assert outcome.value.mean == 1.0


async def test_an_id_the_manifest_does_not_hold_is_refused_naming_it_and_the_ids_it_does() -> None:
    # Arrange
    questions = (_question(relevant_documents=("ax-missing",)),)

    # Act
    with pytest.raises(UnresolvableLabelError) as excinfo:
        await score_pipeline(
            registry=_registry(),
            resolved_pipeline=_resolved_pipeline(),
            questions=questions,
            top_k=1,
            ctx=_ctx(),
            corpus_document_ids=("doc-a", "doc-b"),
            document_labels={"ax-a": "doc-a", "ax-b": "doc-b"},
        )

    # Assert
    message = str(excinfo.value)
    assert "ax-missing" in message
    assert "ax-a" in message


async def test_a_sample_carries_the_questions_kind_or_the_axis_standing_in_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`weft eval compare --kind requires-graph-hop` slices on `RetrievalSample.kind`. A bridge
    question states `kind` absent and carries the label as `axes["kind"]`; a curated question
    carries a `Kind`. Both have to reach the sample, or one of the two sets stops being
    sliceable."""
    # Arrange
    captured: list[RetrievalSample] = []

    async def _capture(_registry: object, samples: Sequence[RetrievalSample], **_kw: object):
        captured.extend(samples)
        return SubsetScores(metrics={}, per_question={})

    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _capture)
    curated = Question.model_validate(
        {
            "id": "curated-1",
            "text": "What is it?",
            "language": "en",
            "kind": Kind.DEFINITIONAL,
            "difficulty": "easy",
            "relevant_documents": ("doc-a",),
            "reference_answer": "That.",
            "notes": "written for this test",
            "quote": ({"document": "doc-a", "page": 0, "text": "That."},),
        }
    )
    bridge = _question("bridge-1", kind_axis="requires-graph-hop")

    # Act
    await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(curated, bridge),
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a", "doc-b"),
    )

    # Assert
    kinds = {sample.question_key: sample.kind for sample in captured}
    assert kinds == {"curated-1": "definitional", "bridge-1": "requires-graph-hop"}
    # Task 38.2 — a question's declared axes reach its sample as they are.
    axes = {sample.question_key: dict(sample.axes) for sample in captured}
    assert axes == {"curated-1": {}, "bridge-1": {"kind": "requires-graph-hop"}}


async def test_the_scored_run_names_its_question_set_by_the_one_models_digest() -> None:
    # Arrange
    questions = (_question("q-1"), _question("q-2", text="q2"))

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a", "doc-b"),
    )

    # Assert
    assert report.question_set == question_set_digest(questions)


# --- Task 38.0 — an experiment's arm refuses a passage its corpus does not hold.


async def test_a_passage_from_outside_the_corpus_is_refused_when_asked_naming_the_document() -> (
    None
):
    """The fake store answers from `doc-a`. Scored against a corpus of `doc-b` alone, that
    passage is a document no question judged, and counting it as a miss would make a store shared
    with another corpus read as a worse pipeline."""
    # Arrange
    questions = (_question(relevant_documents=("doc-b",)),)

    # Act
    with pytest.raises(ForeignDocumentRetrievedError) as excinfo:
        await score_pipeline(
            registry=_registry(),
            resolved_pipeline=_resolved_pipeline(),
            questions=questions,
            top_k=1,
            ctx=_ctx(),
            corpus_document_ids=("doc-b",),
            refuse_foreign_documents=True,
        )

    # Assert
    assert "doc-a" in str(excinfo.value)
    assert excinfo.value.document == "doc-a"


async def test_a_passage_from_outside_the_corpus_is_still_scored_when_not_asked() -> None:
    """`weft eval run`'s own behaviour, unchanged: only the experiment runner opts in."""
    # Arrange
    questions = (_question(relevant_documents=("doc-b",)),)

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-b",),
    )

    # Assert
    outcome = report.metrics["precision@1"]
    assert isinstance(outcome, Produced)
    assert outcome.value.mean == 0.0


# --- Repair R38.0 — a query rung that ends in retrieval is scored over what it packed.


def _labelled_passage(source: str, score: float, rank: int) -> Passage:
    node = Node.synthetic(content=source, media_type=MediaType.TEXT, reason="fixture").model_copy(
        update={"lineage": Lineage.derived(parents=(), sources=frozenset({SourceId(source)}))}
    )
    return Passage(
        scored=Scored(value=node, score=score),
        rank=rank,
        retrieved_by="fixture",
        label=str(rank + 1),
    )


def _rung(*contracts: str) -> ResolvedPipeline:
    return ResolvedPipeline(
        name="some-rung",
        stages=tuple(
            ResolvedStage(
                id=f"stage-{index}",
                contract=contract,
                use=f"plugin-{index}",
                distribution="weft-rag",
                provenance="some-rung",
            )
            for index, contract in enumerate(contracts)
        ),
    )


async def test_a_rung_ending_in_a_packer_is_scored_over_its_passages_and_calls_no_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`lexical-retrieve` ends in `repack` and produces `Passages`. `run_named_ask` requires an
    `Answer` and refused it, which is what left `38.0`'s experiment with orphaned records; a
    retrieval rung is scored through `run_named_retrieve` instead, the path `weft ask
    --retrieve-only --pipeline` already takes, and no answer is generated for it."""
    # Arrange
    captured: list[RetrievalSample] = []
    asked: list[object] = []

    async def _passages(*_args: object, **_kwargs: object) -> Passages:
        return Passages(
            origin=Query(text="q"),
            passages=(_labelled_passage("doc-b", 0.2, 1), _labelled_passage("doc-a", 0.9, 0)),
        )

    async def _ask(*args: object, **kwargs: object) -> Answer:
        asked.append((args, kwargs))
        raise AssertionError("a retrieval rung must not be asked for an answer")

    async def _capture(_registry: object, samples: Sequence[RetrievalSample], **_kw: object):
        captured.extend(samples)
        return SubsetScores(metrics={}, per_question={})

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Fuser", "ContextPacker")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _passages)
    monkeypatch.setattr(eval_scoring_module, "run_named_ask", _ask)
    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _capture)

    # Act
    await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(_question(relevant_documents=("doc-a",)),),
        top_k=2,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-a", "doc-b"),
    )

    # Assert
    assert asked == []
    assert [passage.id for passage in captured[0].retrieved] == ["doc-a", "doc-b"]


async def test_a_rung_ending_in_a_generator_is_still_scored_over_the_answers_passages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    retrieved: list[object] = []

    async def _answer(*_args: object, **_kwargs: object) -> Answer:
        return Answer(text="a", origin=Query(text="q"), answered_by="fixture", used=())

    async def _passages(*args: object, **kwargs: object) -> Passages:
        retrieved.append((args, kwargs))
        raise AssertionError("a generating rung is scored over its answer")

    async def _capture(_registry: object, samples: Sequence[RetrievalSample], **_kw: object):
        del samples
        return SubsetScores(metrics={}, per_question={})

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Fuser", "ContextPacker", "Generator")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _passages)
    monkeypatch.setattr(eval_scoring_module, "run_named_ask", _answer)
    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _capture)

    # Act
    await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(_question(),),
        top_k=2,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert retrieved == []


# --- Repair R38.1 — the scored run carries each question's axes for the record.


async def test_the_scored_run_carries_each_questions_axes_with_its_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A paired difference restricted to a slice has to know which questions were in it, after the
    question file is gone; `kind`, when a question states one, is recorded as the axis `--kind`
    reads, so `--kind X` and `--slice kind=X` restrict the same questions."""

    # Arrange
    async def _no_metrics(_registry: object, samples: Sequence[RetrievalSample], **_kw: object):
        del samples
        return SubsetScores(metrics={}, per_question={})

    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _no_metrics)
    curated = Question.model_validate(
        {
            "id": "curated-1",
            "text": "What is it?",
            "language": "en",
            "kind": Kind.DEFINITIONAL,
            "difficulty": "easy",
            "relevant_documents": ("doc-a",),
            "reference_answer": "That.",
            "notes": "written for this test",
            "quote": ({"document": "doc-a", "page": 0, "text": "That."},),
        }
    )
    bridge = _question("bridge-1", kind_axis="requires-graph-hop")

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(curated, bridge),
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a", "doc-b"),
    )

    # Assert
    assert report.question_axes is not None
    assert dict(report.question_axes["curated-1"]) == {"kind": "definitional"}
    assert dict(report.question_axes["bridge-1"]) == {"kind": "requires-graph-hop"}


# --- Repair R38.12 — a rung that fails on one question excludes that question, counted.


async def test_a_rung_failing_on_one_question_excludes_it_with_its_reason_and_scores_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`38.6`'s HyDE arm failed on one of 300 questions — a model's answer could not be parsed —
    and the exception left the question loop, so the arm wrote no record at all. `09` V4: a failed
    metric is an error, never a zero, and aggregates report how many were excluded. A question the
    rung could not answer is the same error one level up."""

    # Arrange
    async def _passages(question: str, *_args: object, **_kwargs: object) -> Passages:
        if question == "breaks":
            raise PipelineDidNotProduceError(
                "pipeline 'some-rung' did not produce: could not parse", pipeline="some-rung"
            )
        return Passages(origin=Query(text=question), passages=(_labelled_passage("doc-a", 0.9, 0),))

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Fuser", "ContextPacker")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _passages)
    questions = (
        _question("q-1", text="works"),
        _question("q-2", text="breaks"),
        _question("q-3", text="works too"),
    )

    # Act
    scored = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert scored.question_scores, "the run must still produce per-question scores"
    for name, per_question in scored.question_scores.items():
        outcome = per_question.scores["q-2"]
        assert isinstance(outcome, NotScored), name
        assert "could not parse" in outcome.reason
        assert isinstance(per_question.scores["q-1"], Produced), name
        aggregate = scored.metrics[name]
        assert isinstance(aggregate, Produced), name
        assert (aggregate.value.n, aggregate.value.excluded) == (2, 1), name


# --- Repair R39.1 — a model stuck in a repeating span on one question excludes that question.


async def test_a_model_looping_on_one_question_excludes_it_and_scores_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`39.5`'s `rfc-rerank` run: `llm-rerank` looped on one question's prompt, the loop-breaker
    stopped it, and its `LLMGenerationLoopError` left the question loop, so the arm wrote no
    record. The loop is a fact about that question's prompt — retrying it "is likely to loop
    again" — so it is `R38.12`'s per-question failure, not a fault of the run."""

    # Arrange
    async def _passages(question: str, *_args: object, **_kwargs: object) -> Passages:
        if question == "loops":
            raise LLMGenerationLoopError(
                "provider 'openai' (role 'rerank') was generating a repeating span",
                provider="openai",
                model="some-model",
            )
        return Passages(origin=Query(text=question), passages=(_labelled_passage("doc-a", 0.9, 0),))

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Fuser", "ContextPacker")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _passages)
    questions = (
        _question("q-1", text="works"),
        _question("q-2", text="loops"),
        _question("q-3", text="works too"),
    )

    # Act
    scored = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert scored.question_scores, "the run must still produce per-question scores"
    for name, per_question in scored.question_scores.items():
        outcome = per_question.scores["q-2"]
        assert isinstance(outcome, NotScored), name
        assert "repeating span" in outcome.reason
        aggregate = scored.metrics[name]
        assert isinstance(aggregate, Produced), name
        assert (aggregate.value.n, aggregate.value.excluded) == (2, 1), name


async def test_a_model_refusing_the_credential_still_aborts_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: a wrong key fails every question identically, so excluding them one by one
    would write a record of nothing but exclusions. Only the per-question failure is caught."""

    # Arrange
    async def _passages(question: str, *_args: object, **_kwargs: object) -> Passages:
        del question
        raise LLMAuthenticationError("invalid api key", provider="openai", model="some-model")

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Fuser", "ContextPacker")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _passages)

    # Act / Assert
    with pytest.raises(LLMAuthenticationError):
        await score_pipeline(
            registry=_registry(),
            resolved_pipeline=_resolved_pipeline(),
            questions=(_question("q-1", text="works"),),
            top_k=1,
            ctx=_ctx(),
            query_pipeline="some-rung",
            corpus_document_ids=("doc-a",),
        )


# --- Ledger task 39.2 — a retrieval rung's record says which arms answered each question.


async def test_a_retrieval_rung_records_which_arms_each_questions_passages_came_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G24: a question with no anchor contributes no lexical ranking, and the run records which
    branch it took. The passages a retrieval rung returns carry the labels of the lists they were
    fused from; the scored run keeps them per question, keyed as its scores are."""
    # Arrange
    answered_by = {
        "What is WRH123?": ("hybrid:vector", "hybrid:text"),
        "What is a good controller?": ("hybrid:vector",),
    }

    async def _passages(question: str, *_args: object, **_kwargs: object) -> Passages:
        return Passages(
            origin=Query(text=question),
            passages=(_labelled_passage("doc-a", 0.9, 0),),
            contributors=answered_by[question],
        )

    async def _no_metrics(_registry: object, samples: Sequence[RetrievalSample], **_kw: object):
        del samples
        return SubsetScores(metrics={}, per_question={})

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("QueryTransform", "Retriever", "Fuser", "ContextPacker")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _passages)
    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _no_metrics)
    anchored = _question("anchored", text="What is WRH123?")
    plain = _question("plain", text="What is a good controller?")

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(anchored, plain),
        top_k=1,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert report.question_contributors is not None
    assert set(report.question_contributors["anchored"]) == {"hybrid:vector", "hybrid:text"}
    assert tuple(report.question_contributors["plain"]) == ("hybrid:vector",)


async def test_a_run_with_no_query_rung_records_no_contributors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hardwired vector search returns hits, not passages, so nothing states an arm; the
    record says it does not know rather than inventing an answer."""

    # Arrange
    async def _no_metrics(_registry: object, samples: Sequence[RetrievalSample], **_kw: object):
        del samples
        return SubsetScores(metrics={}, per_question={})

    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _no_metrics)

    # Act
    report = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(_question(),),
        top_k=1,
        ctx=_ctx(),
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert report.question_contributors is None


# --- Ledger task 32.14 — a generating rung's answer is scored against the reference answer.


def _answered(reference: str | None, identifier: str = "q-1", text: str = "q") -> Question:
    fields: dict[str, object] = {
        "id": identifier,
        "text": text,
        "language": "en",
        "relevant_documents": ("doc-a",),
        "absent": _ABSENT_BUT_KIND | {QuestionField.KIND},
        "absent_reason": "a scoring fixture",
        "axes": {},
    }
    if reference is not None:
        fields["reference_answer"] = reference
        fields["absent"] = (_ABSENT_BUT_KIND - {QuestionField.REFERENCE_ANSWER}) | {
            QuestionField.KIND
        }
    return Question.model_validate(fields)


def _generating(monkeypatch: pytest.MonkeyPatch, answers: dict[str, str]) -> None:
    async def _answer(question: str, *_args: object, **_kwargs: object) -> Answer:
        return Answer(
            text=answers[question],
            origin=Query(text=question),
            answered_by="fixture",
            used=(_labelled_passage("doc-a", 0.9, 0),),
        )

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Fuser", "ContextPacker", "Generator")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_ask", _answer)


async def test_a_generating_rungs_answer_is_scored_against_the_reference_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`32.0` named `token-recall` and `rouge-l` as the metrics that can see `adjacent-chunks`;
    before this task the scored run kept only `Answer.used` and threw the text away, so no
    answer metric was ever computed in a real run."""
    # Arrange — `token_recall` splits on whitespace after lower-casing (`weft_eval/lexical.py`),
    # so both reference tokens appear in this answer and recall is 1.0.
    _generating(monkeypatch, {"what is it?": "It is forty two"})

    # Act
    scored = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(_answered("forty two", text="what is it?"),),
        top_k=1,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-a",),
    )

    # Assert
    recall = scored.metrics["token_recall"]
    assert isinstance(recall, Produced)
    assert recall.value.mean == 1.0
    assert "rouge_l" in scored.metrics
    assert scored.question_scores is not None
    assert "q-1" in scored.question_scores["token_recall"].scores


async def test_a_question_with_no_reference_answer_has_nothing_to_score_not_a_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _generating(monkeypatch, {"with": "forty two", "without": "anything"})
    questions = (
        _answered("forty two", identifier="with", text="with"),
        _answered(None, identifier="without", text="without"),
    )

    # Act
    scored = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-a",),
    )

    # Assert
    recall = scored.metrics["token_recall"]
    assert isinstance(recall, Produced)
    assert (recall.value.n, recall.value.nothing_to_produce) == (1, 1)


async def test_a_question_whose_model_looped_is_excluded_from_the_answer_metrics_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    async def _answer(question: str, *_args: object, **_kwargs: object) -> Answer:
        if question == "loops":
            raise LLMGenerationLoopError("repeating span", provider="scripted", model="some-model")
        return Answer(text="forty two", origin=Query(text=question), answered_by="fixture")

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Fuser", "ContextPacker", "Generator")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_ask", _answer)
    questions = (
        _answered("forty two", identifier="fine", text="fine"),
        _answered("forty two", identifier="looped", text="loops"),
    )

    # Act
    scored = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=questions,
        top_k=1,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-a",),
    )

    # Assert
    recall = scored.metrics["token_recall"]
    assert isinstance(recall, Produced)
    assert (recall.value.n, recall.value.excluded) == (1, 1)
    assert scored.question_scores is not None
    assert isinstance(scored.question_scores["token_recall"].scores["looped"], NotScored)


async def test_a_retrieval_rung_computes_no_answer_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    async def _passages(question: str, *_args: object, **_kwargs: object) -> Passages:
        return Passages(origin=Query(text=question), passages=(_labelled_passage("doc-a", 0.9, 0),))

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Fuser", "ContextPacker")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _passages)

    # Act
    scored = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(_answered("forty two"),),
        top_k=1,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-a",),
    )

    # Assert
    assert "token_recall" not in scored.metrics
    assert "rouge_l" not in scored.metrics


# --- Repair R40.0 — hits tied on score keep the order the ranking gave them, not the packer's.


@pytest.mark.parametrize("ends_in", ["ContextPacker", "Generator"])
async def test_hits_tied_on_score_are_ranked_in_the_order_the_ranking_gave_them(
    monkeypatch: pytest.MonkeyPatch, ends_in: str
) -> None:
    """`repack: reverse` packs the best hit last; two hits tied on score arrived at the stable
    sort in that inverted order, so `[relevant, irrelevant]` at 3.5 each scored RR ½."""
    # Arrange
    captured: list[RetrievalSample] = []
    packed = (_labelled_passage("doc-other", 3.5, 1), _labelled_passage("doc-best", 3.5, 0))

    async def _passages(*_args: object, **_kwargs: object) -> Passages:
        return Passages(origin=Query(text="q"), passages=packed)

    async def _answer(*_args: object, **_kwargs: object) -> Answer:
        return Answer(text="a", origin=Query(text="q"), answered_by="fixture", used=packed)

    async def _capture(_registry: object, samples: Sequence[RetrievalSample], **_kw: object):
        captured.extend(samples)
        return SubsetScores(metrics={}, per_question={})

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Reranker", ends_in)

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _passages)
    monkeypatch.setattr(eval_scoring_module, "run_named_ask", _answer)
    monkeypatch.setattr(eval_scoring_module, "score_retrieval_gate_subset", _capture)

    # Act
    await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(_question(relevant_documents=("doc-best",)),),
        top_k=2,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-best", "doc-other"),
    )

    # Assert
    assert [passage.id for passage in captured[0].retrieved] == ["doc-best", "doc-other"]


# --- Task 40.1 — the ranking is collapsed once and scored at every cutoff.


async def test_a_ranking_collapsed_once_is_scored_at_every_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — the relevant document is second, so recall@1 is 0 and recall@2 is 1.
    packed = (_labelled_passage("doc-first", 0.9, 0), _labelled_passage("doc-best", 0.5, 1))

    async def _passages(*_args: object, **_kwargs: object) -> Passages:
        return Passages(origin=Query(text="q"), passages=packed)

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Fuser", "ContextPacker")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _passages)

    # Act
    scored = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(_question(relevant_documents=("doc-best",)),),
        top_k=2,
        cutoffs=(1, 2),
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-best", "doc-first"),
    )

    # Assert
    at_one, at_two = scored.metrics["recall@1"], scored.metrics["recall@2"]
    assert isinstance(at_one, Produced) and isinstance(at_two, Produced)
    assert (at_one.value.mean, at_two.value.mean) == (0.0, 1.0)


# --- Task 40.2 — a retrieval rung's pool, captured in the order the ranking gave it.


@pytest.mark.parametrize("capture", [True, False])
async def test_a_captured_pool_holds_every_packed_chunk_in_ranking_order(
    monkeypatch: pytest.MonkeyPatch, capture: bool
) -> None:
    # Arrange — packed by `reverse`, so the tuple is worst-first; the pool must not be.
    packed = (
        _labelled_passage("doc-c", 0.2, 2),
        _labelled_passage("doc-b", 0.5, 1),
        _labelled_passage("doc-a", 0.9, 0),
    )

    async def _passages(*_args: object, **_kwargs: object) -> Passages:
        return Passages(origin=Query(text="q"), passages=packed)

    def _resolved(*_args: object, **_kwargs: object) -> ResolvedPipeline:
        return _rung("Retriever", "Fuser", "ContextPacker")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved)
    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _passages)

    # Act
    scored = await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(_question(relevant_documents=("doc-a",)),),
        top_k=1,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-a", "doc-b", "doc-c"),
        capture_pool=capture,
    )

    # Assert
    if not capture:
        assert (scored.question_pools, scored.store_rows) == (None, None)
        return
    assert scored.question_pools is not None
    chunks = scored.question_pools["q-1"]
    assert [(chunk.document_id, chunk.score) for chunk in chunks] == [
        ("doc-a", 0.9),
        ("doc-b", 0.5),
        ("doc-c", 0.2),
    ]
    assert chunks[0].node_id == str(packed[2].node.id)
    assert chunks[0].content_sha256 == hashlib.sha256(b"doc-a").hexdigest()
    assert scored.store_rows == 7
