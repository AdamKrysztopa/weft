"""Unit tests for `weft_cli.eval_scoring`.

Mirrors `packages/weft-rag/src/weft_cli/eval_scoring.py`. `load_questions` is exercised against
real files on disk — the happy path (a well-formed JSON list round-trips into `Question`s) and
the error case (malformed JSON refuses naming the path, mirroring `weft_cli.ask`'s own tests'
convention of fake embedder/store stand-ins). `score_pipeline` is exercised against fakes for
`Embedder`/`NodeStore` — `weft_cli.ask`'s own `test_ask.py`'s convention, since the property
under test is that this module retrieves through the *resolved pipeline's own* stages (never
`[services]`) and folds the result into a real `weft_eval.harness.score_retrieval_gate_subset`
report — plus the edge case (a pipeline naming no `Embedder`/`NodeStore` stage refuses outright
rather than silently reporting empty metrics indistinguishable from "no --questions given").
"""

from collections.abc import Sequence
from pathlib import Path

import pytest

from weft_cli import eval_scoring as eval_scoring_module
from weft_cli.eval_scoring import (
    AmbiguousLabelError,
    PipelineNotRetrievableError,
    Question,
    QuestionsFileError,
    UnresolvableLabelError,
    load_questions,
    question_set_digest,
    resolve_labels,
    score_pipeline,
)
from weft_embed import Embedder
from weft_eval import Settings, register
from weft_eval.contract import RetrievalSample
from weft_eval.harness import SubsetScores
from weft_eval.run_record import QuestionKey
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
from weft_retrieve.payload import Passage, Query
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


# --- load_questions -------------------------------------------------------------------------


def test_load_questions_round_trips_a_well_formed_file(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "questions.json"
    path.write_text(
        '[{"query": "what is weft?", "relevant_documents": ["doc-a", "doc-b"]}]',
        encoding="utf-8",
    )

    # Act
    questions = load_questions(path)

    # Assert
    assert questions == (Question(query="what is weft?", relevant_documents=("doc-a", "doc-b")),)


def test_load_questions_refuses_malformed_json_naming_the_path(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "questions.json"
    path.write_text("not json", encoding="utf-8")

    # Act / Assert
    with pytest.raises(QuestionsFileError) as excinfo:
        load_questions(path)
    assert excinfo.value.path == str(path)


def test_load_questions_refuses_a_missing_file(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "does-not-exist.json"

    # Act / Assert
    with pytest.raises(QuestionsFileError) as excinfo:
        load_questions(path)
    assert excinfo.value.path == str(path)


# --- score_pipeline --------------------------------------------------------------------------


async def test_score_pipeline_retrieves_and_scores_against_the_resolved_stages() -> None:
    # Arrange — one question whose relevant document is exactly what the fake store returns.
    questions = (Question(query="q", relevant_documents=("doc-a",)),)

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
    questions = (Question(query="q", relevant_documents=("doc-a",)),)

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


def test_a_question_may_carry_an_id_and_a_file_without_one_still_loads(tmp_path: Path) -> None:
    """`id` is optional, because every `--questions` file written before this task has none.

    The ledger's own line for this task said the id was *"already carried and dropped"* by this
    loader. It was not: `eval/questions/*.toml` carries ids and is read by
    `eval/check_questions.py`'s own, separate `Question` into `eval/run_baseline.py`; this
    loader reads **JSON** and has `extra="forbid"`, so an `id` key would have been *refused*,
    not dropped. Two `Question` classes, two loaders, and they never meet (`L17.16`).
    """
    # Arrange
    with_id = tmp_path / "with-id.json"
    with_id.write_text('[{"id": "fetch-001", "query": "q", "relevant_documents": ["doc-a"]}]')
    without = tmp_path / "without.json"
    without.write_text('[{"query": "q", "relevant_documents": ["doc-a"]}]')

    # Act
    identified = load_questions(with_id)
    anonymous = load_questions(without)

    # Assert
    assert identified[0].id == "fetch-001"
    assert anonymous[0].id is None


def test_a_questions_file_repeating_an_id_is_refused_naming_it(tmp_path: Path) -> None:
    """Two questions under one id would silently collapse into one per-question score, so the
    file is refused where it is read rather than producing a record short of a question.
    """
    # Arrange
    path = tmp_path / "duplicate.json"
    path.write_text('[{"id": "fetch-001", "query": "a"}, {"id": "fetch-001", "query": "b"}]')

    # Act / Assert
    with pytest.raises(QuestionsFileError) as excinfo:
        load_questions(path)
    assert "fetch-001" in str(excinfo.value)


def test_a_questions_file_that_identifies_some_questions_and_not_others_is_refused(
    tmp_path: Path,
) -> None:
    """Either the file has identities or it has positions. A half-identified file would make
    `keyed_by` a lie whichever value it took, and the honest answer is to refuse the input
    rather than to pick a reading for it.
    """
    # Arrange
    path = tmp_path / "mixed.json"
    path.write_text('[{"id": "fetch-001", "query": "a"}, {"query": "b"}]')

    # Act / Assert
    with pytest.raises(QuestionsFileError) as excinfo:
        load_questions(path)
    assert "id" in str(excinfo.value)


async def test_scores_are_keyed_by_question_id_when_the_file_carries_them() -> None:
    # Arrange
    questions = (
        Question(id="fetch-001", query="q", relevant_documents=("doc-a",)),
        Question(id="fetch-002", query="q2", relevant_documents=("doc-a",)),
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


async def test_scores_are_keyed_by_position_when_the_file_carries_no_ids() -> None:
    """And the record says `POSITION`, so nobody reads `"0"` as an identity that survives a
    second questions file.
    """
    # Arrange
    questions = (
        Question(query="q", relevant_documents=("doc-a",)),
        Question(query="q2", relevant_documents=("doc-a",)),
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
    assert precision.keyed_by is QuestionKey.POSITION
    assert set(precision.scores) == {"0", "1"}


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
    carry a root. `eval/metrics.py`'s own `Hit` docstring states the principle this resolves
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
    questions = (Question(query="q", relevant_documents=("doc-a",)),)

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


# --- Task 16.6 — the identity of the question set a run was scored with.


def test_the_question_set_digest_is_order_independent() -> None:
    """*Nothing positional*, so two files holding the same questions in two orders are one
    question set. A digest over the list as written would make re-ordering a file look like a
    different measurement.
    """
    # Arrange
    first = Question(id="a", query="one", relevant_documents=("x.txt",))
    second = Question(id="b", query="two", relevant_documents=("y.txt",))

    # Act / Assert
    assert question_set_digest((first, second)) == question_set_digest((second, first))


def test_the_question_set_digest_moves_when_any_question_does() -> None:
    """Every field of `Question` is in the canonical form, derived from the model rather than
    from a hand-listed tuple — so a version that learns a scoring-relevant field produces a new
    digest, which is the honest answer rather than a gap. Task 16.8 adds `language` and will
    move this digest for exactly that reason.
    """
    # Arrange
    base = Question(id="a", query="one", relevant_documents=("x.txt",), kind="factual")

    # Act / Assert — one field at a time, each of which changes what was measured.
    assert question_set_digest((base,)) != question_set_digest(
        (Question(id="a", query="ONE", relevant_documents=("x.txt",), kind="factual"),)
    )
    assert question_set_digest((base,)) != question_set_digest(
        (Question(id="a", query="one", relevant_documents=("y.txt",), kind="factual"),)
    )
    assert question_set_digest((base,)) != question_set_digest(
        (Question(id="a", query="one", relevant_documents=("x.txt",), kind="numeric"),)
    )


def test_the_question_set_digest_holds_nothing_a_machine_put_there() -> None:
    """The point of the whole field: the same file staged anywhere digests the same. Since task
    16.5 a label is a corpus-relative path, so there is no root in a question to leak into this.
    """
    # Arrange — questions as they are written in a tree, with no absolute path anywhere.
    questions = (
        Question(id="a", query="one", relevant_documents=("arxiv/1304.7717v2.pdf",)),
        Question(id="b", query="two", relevant_documents=("pl-wiki/kraków.txt",)),
    )

    # Act
    digest = question_set_digest(questions)

    # Assert — a digest is hex, and holds no separator a staging root would have contributed.
    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)


def test_two_questions_that_differ_only_by_id_are_two_question_sets() -> None:
    """An id is part of the identity because it is what per-question scores are keyed on
    (task 16.4). Two files with the same questions under different ids produce records whose
    scores cannot be paired, so they are not the same question set.
    """
    # Arrange / Act / Assert
    assert question_set_digest((Question(id="a", query="q"),)) != question_set_digest(
        (Question(id="b", query="q"),)
    )


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
        return ResolvedPipeline(name="some-rung")

    monkeypatch.setattr(eval_scoring_module, "resolve_named_pipeline", _resolved_rung)

    # Act
    await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_resolved_pipeline(),
        questions=(Question(query="q", relevant_documents=("doc-best",)),),
        top_k=3,
        ctx=_ctx(),
        query_pipeline="some-rung",
        corpus_document_ids=("doc-best", "doc-middle", "doc-worst"),
    )

    # Assert — best first, which is what `mrr`, `ndcg` and `mean_average_precision` all read.
    assert [passage.id for passage in captured[0].retrieved] == [
        "doc-best",
        "doc-middle",
        "doc-worst",
    ]


# --- Task 16.8 — a question states its own language.


def test_a_question_carries_a_language_and_defaults_to_english() -> None:
    """`eval/questions/*.toml` has stated `language` on every question since the set was
    written; the JSON loader this path uses had no field for it, so the fact stopped at the
    file. It is what a language-aware metric reads, and — since task 16.6's canonical form is
    derived from the model — it is part of the question set's identity.
    """
    # Arrange / Act / Assert
    assert Question(query="q").language == "en"
    assert Question(query="q", language="pl").language == "pl"


def test_the_question_set_digest_moves_when_a_questions_language_does() -> None:
    """Which is the point of deriving the canonical form rather than listing fields: the same
    questions scored as Polish are a different measurement from the same questions scored as
    English, and the digest says so without 16.6 having had to anticipate this field.
    """
    # Arrange / Act / Assert
    assert question_set_digest((Question(id="a", query="q"),)) != question_set_digest(
        (Question(id="a", query="q", language="pl"),)
    )
