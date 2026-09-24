"""Replaying a frozen pool through rerankers — ledger **40.2**, its second half.

A replay never embeds and never searches: it hydrates each captured chunk from the store by id,
hands the ranking to a document whose first stage takes a `Ranking`, and scores what that document
packed on `(-score, rank)`. Every way the pool, the question file or the store can have moved since
capture is refused by name rather than scored, because a replay that silently re-read different data
would be a comparison between two things nobody chose.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import ClassVar

import pytest

from weft_cli import route_ask as route_ask_module
from weft_cli.eval_scoring import ScoredRun, score_pipeline
from weft_embed import Embedder
from weft_eval import Settings, register
from weft_eval.pool import (
    POOL_MANIFEST_SCHEMA_VERSION,
    LoadedPool,
    PoolChunk,
    PoolIntegrityError,
    PoolManifest,
    PoolQuestion,
    PoolQuestionEntry,
    relevant_set_sha256,
    text_sha256,
)
from weft_eval.question_set import Question, QuestionField
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import (
    Failed,
    Lineage,
    MediaType,
    Node,
    NodeId,
    Outcome,
    Produced,
    SourceId,
)
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_retrieve import ContextPacker, Reranker
from weft_retrieve.anchor_promote import AnchorPromote
from weft_retrieve.payload import Ranking
from weft_retrieve.repack import Repack
from weft_store import NodeStore, Scored

_CORPUS = "/capture-host/corpus"
_DOCUMENTS = ("doc-a.txt", "doc-b.txt", "doc-c.txt", "doc-d.txt", "doc-w.txt", "doc-z.txt")


def _node(document: str, words: str) -> Node:
    return Node.synthetic(content=words, media_type=MediaType.TEXT, reason="fixture").model_copy(
        update={
            "lineage": Lineage.derived(
                parents=(), sources=frozenset({SourceId(f"{_CORPUS}/{document}")})
            )
        }
    )


_NODES = {
    "a1": _node("doc-a.txt", "alpha one"),
    "a2": _node("doc-a.txt", "alpha two"),
    "b1": _node("doc-b.txt", "beta one"),
    "c1": _node("doc-c.txt", "gamma one"),
    "d1": _node("doc-d.txt", "delta one"),
    "w1": _node("doc-w.txt", "WRH123 is the reset code"),
    **{f"z{n}": _node("doc-z.txt", f"filler {n}") for n in range(1, 5)},
}

#: Appended below every captured pool, so each is at least as deep as the `@5` metrics read — a
#: real pool is fifty chunks, and a metric refuses a ranking shallower than its `k` (`R38.5`).
_FILLER = tuple(f"z{n}" for n in range(1, 5))


class _Store:
    """A store holding `_NODES`, whose search and embedding a replay must never reach."""

    rows: ClassVar[int] = len(_NODES)
    held: ClassVar[dict[str, Node]] = {}
    count_after_first_get: ClassVar[int | None] = None
    gets: ClassVar[int] = 0

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        _Store.gets += 1
        return [_Store.held[str(i)] for i in ids if str(i) in _Store.held]

    async def count(self) -> int:
        if _Store.count_after_first_get is not None and _Store.gets > 0:
            return _Store.count_after_first_get
        return _Store.rows

    async def search_vector(self, *_args: object, **_kwargs: object) -> Sequence[Scored[Node]]:
        raise AssertionError("a replay searched the store")


class _Embedder:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        raise AssertionError("a replay embedded something")


class _Spy:
    """A reranker that records which question each ranking says it serves, and refuses one."""

    version: ClassVar[str] = "1"
    seen: ClassVar[list[str]] = []

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        del ctx
        entry = payload.ext.get(PoolQuestionEntry.__namespace__)
        assert isinstance(entry, PoolQuestionEntry)
        _Spy.seen.append(entry.question_id)
        if payload.origin.text == "refused here":
            return Failed(reason="the spy refuses this question")
        return Produced(value=payload)


@pytest.fixture(autouse=True)
def fresh_store() -> None:
    _Store.held = {str(node.id): node for node in _NODES.values()}
    _Store.rows = len(_NODES)
    _Store.count_after_first_get = None
    _Store.gets = 0
    _Spy.seen = []


def _registry() -> Registry:
    registry = Registry()
    registry.add(Embedder, "hash", _Embedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _Store, distribution="weft-store")
    registry.add(ContextPacker, "repack", Repack, distribution="weft-retrieve")
    registry.add(Reranker, "spy-rerank", _Spy, distribution="weft-retrieve")
    registry.add(Reranker, "anchor-promote", AnchorPromote, distribution="weft-retrieve")
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


def _catalogue() -> Callable[..., dict[str, Pipeline]]:
    documents = {
        "replay-forward": Pipeline(
            name="replay-forward",
            stages=(StageDeclaration(id="pack", use="repack", config={"method": "forward"}),),
        ),
        "replay-reverse": Pipeline(
            name="replay-reverse",
            stages=(StageDeclaration(id="pack", use="repack", config={"method": "reverse"}),),
        ),
        "replay-promote": Pipeline(
            name="replay-promote",
            stages=(
                StageDeclaration(id="promote", use="anchor-promote"),
                StageDeclaration(id="pack", use="repack", config={"method": "reverse"}),
            ),
        ),
        "replay-spy": Pipeline(
            name="replay-spy",
            stages=(
                StageDeclaration(id="spy", use="spy-rerank"),
                StageDeclaration(id="pack", use="repack", config={"method": "reverse"}),
            ),
        ),
    }

    def _full_catalogue(
        *, directory: Path = Path("pipelines"), reports: Sequence[object] = ()
    ) -> dict[str, Pipeline]:
        del directory, reports
        return documents

    return _full_catalogue


def _ingest() -> ResolvedPipeline:
    return ResolvedPipeline(
        name="index",
        stages=(
            ResolvedStage(
                id="embed", contract="Embedder", use="hash", distribution="w", provenance="index"
            ),
            ResolvedStage(
                id="store",
                contract="NodeStore",
                use="pgvector",
                distribution="w",
                provenance="index",
            ),
        ),
    )


def _question(identifier: str, text: str, relevant: tuple[str, ...]) -> Question:
    return Question.model_validate(
        {
            "id": identifier,
            "text": text,
            "language": "en",
            "relevant_documents": relevant,
            "absent": frozenset(
                {
                    QuestionField.KIND,
                    QuestionField.DIFFICULTY,
                    QuestionField.QUOTE,
                    QuestionField.REFERENCE_ANSWER,
                    QuestionField.NOTES,
                }
            ),
            "absent_reason": "a replay fixture",
            "axes": {},
        }
    )


def _chunk(key: str, score: float) -> PoolChunk:
    node = _NODES[key]
    return PoolChunk(
        node_id=str(node.id),
        document_id=sorted(str(s) for s in node.lineage.sources)[0],
        content_sha256=hashlib.sha256(node.content.encode("utf-8")).hexdigest(),
        score=score,
    )


def _pool(*entries: tuple[Question, tuple[PoolChunk, ...], bool]) -> LoadedPool:
    manifest = PoolManifest(
        schema_version=POOL_MANIFEST_SCHEMA_VERSION,
        experiment="replay-fixture",
        experiment_digest="e" * 64,
        arm="dense",
        corpus_digest="c" * 64,
        question_set_digest="q" * 64,
        query_pipeline="dense-pool-retrieve",
        query_pipeline_identity="i" * 64,
        model_versions={},
        store="pgvector",
        store_rows=len(_NODES),
        document_ids=tuple(f"{_CORPUS}/{d}" for d in _DOCUMENTS),
        questions=tuple(
            PoolQuestion(
                id=question.id,
                text_sha256=text_sha256(question.text),
                relevant_sha256=relevant_set_sha256(question.relevant_documents),
                rule_fires=fires,
                chunks=chunks
                + tuple(_chunk(key, 0.01 - n / 1000) for n, key in enumerate(_FILLER)),
            )
            for question, chunks, fires in entries
        ),
    )
    return LoadedPool(manifest=manifest, sha256="f" * 64)


async def _replay(
    monkeypatch: pytest.MonkeyPatch,
    pool: LoadedPool,
    questions: tuple[Question, ...],
    *,
    through: str = "replay-forward",
) -> ScoredRun:
    monkeypatch.setattr(route_ask_module, "full_catalogue", _catalogue())
    return await score_pipeline(
        registry=_registry(),
        resolved_pipeline=_ingest(),
        questions=questions,
        top_k=5,
        ctx=Context(tenant_id="t", run_id="r", trace_id="tr", locale="en"),
        corpus_document_ids=pool.manifest.document_ids,
        query_pipeline=through,
        pool=pool,
    )


def _reciprocal_ranks(scored: ScoredRun) -> dict[str, float]:
    per_question = scored.question_scores["mrr@5"].scores
    return {
        key: float(outcome.value)
        for key, outcome in per_question.items()
        if isinstance(outcome, Produced)
    }


async def test_an_identity_replay_scores_exactly_the_captured_ranking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — the relevant document first, third, and absent.
    first = _question("q-first", "first", ("doc-a.txt",))
    third = _question("q-third", "third", ("doc-c.txt",))
    absent = _question("q-absent", "absent", ("doc-d.txt",))
    ranked = (_chunk("a1", 0.9), _chunk("b1", 0.5), _chunk("c1", 0.1))
    pool = _pool(
        (first, ranked, False),
        (third, ranked, False),
        (absent, (_chunk("a1", 0.9), _chunk("b1", 0.5)), False),
    )

    # Act
    scored = await _replay(monkeypatch, pool, (first, third, absent))

    # Assert
    assert _reciprocal_ranks(scored) == {
        "q-first": 1.0,
        "q-third": pytest.approx(1 / 3),
        "q-absent": 0.0,
    }


async def test_hits_tied_on_score_keep_the_order_the_pool_gave_them_under_reverse_packing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    question = _question("q-tie", "tie", ("doc-a.txt",))
    pool = _pool((question, (_chunk("a1", 3.5), _chunk("b1", 3.5)), False))

    # Act
    scored = await _replay(monkeypatch, pool, (question,), through="replay-reverse")

    # Assert
    assert _reciprocal_ranks(scored) == {"q-tie": 1.0}


async def test_two_chunks_of_one_document_collapse_to_its_first_in_emitted_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — doc-a twice above doc-b: collapsed, doc-b is second, not third.
    question = _question("q-dup", "dup", ("doc-b.txt",))
    pool = _pool((question, (_chunk("a1", 0.9), _chunk("a2", 0.8), _chunk("b1", 0.7)), False))

    # Act
    scored = await _replay(monkeypatch, pool, (question,))

    # Assert
    assert _reciprocal_ranks(scored) == {"q-dup": 0.5}


async def test_a_stage_that_refuses_one_question_excludes_it_and_the_run_goes_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    kept = _question("q-kept", "kept", ("doc-a.txt",))
    refused = _question("q-refused", "refused here", ("doc-a.txt",))
    chunks = (_chunk("a1", 0.9), _chunk("b1", 0.5))
    pool = _pool((kept, chunks, False), (refused, chunks, False))

    # Act
    scored = await _replay(monkeypatch, pool, (kept, refused), through="replay-spy")

    # Assert
    aggregate = scored.metrics["mrr@5"]
    assert isinstance(aggregate, Produced)
    assert (aggregate.value.n, aggregate.value.excluded) == (1, 1)
    assert "refuses" in str(scored.question_scores["mrr@5"].scores["q-refused"])


async def test_every_stage_learns_which_question_it_serves_even_when_two_share_a_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — TechQA asks fourteen texts twice; `Query` carries no id, so only the entry can say.
    one = _question("q-one", "the same text", ("doc-a.txt",))
    two = _question("q-two", "the same text", ("doc-a.txt",))
    chunks = (_chunk("a1", 0.9),)
    pool = _pool((one, chunks, False), (two, chunks, False))

    # Act
    await _replay(monkeypatch, pool, (one, two), through="replay-spy")

    # Assert
    assert _Spy.seen == ["q-one", "q-two"]


async def test_the_manifests_rule_fires_becomes_an_axis_of_every_replayed_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    anchored = _question("q-anchored", "error WRH123", ("doc-a.txt",))
    plain = _question("q-plain", "plain", ("doc-a.txt",))
    chunks = (_chunk("a1", 0.9),)
    pool = _pool((anchored, chunks, True), (plain, chunks, False))

    # Act
    scored = await _replay(monkeypatch, pool, (anchored, plain))

    # Assert
    assert scored.question_axes is not None
    assert scored.question_axes["q-anchored"]["rule-fires"] == "true"
    assert scored.question_axes["q-plain"]["rule-fires"] == "false"


def _moved(case: str) -> tuple[LoadedPool, tuple[Question, ...], str]:
    """One way the pool, the question file or the store moved since capture, and the fragment of
    the refusal's claim that names it.
    """
    question = _question("q-1", "what is alpha", ("doc-a.txt",))
    chunks = (_chunk("a1", 0.9), _chunk("b1", 0.5))
    pool = _pool((question, chunks, False))
    if case == "question-text":
        return pool, (_question("q-1", "what is beta", ("doc-a.txt",)),), "text"
    if case == "relevant-set":
        return pool, (_question("q-1", "what is alpha", ("doc-b.txt",)),), "relevant"
    if case == "question-not-captured":
        return pool, (question, _question("q-2", "what is gamma", ("doc-c.txt",))), "q-2"
    if case == "question-not-asked":
        other = _question("q-2", "what is gamma", ("doc-c.txt",))
        return _pool((question, chunks, False), (other, chunks, False)), (question,), "q-2"
    if case == "chunk-missing":
        _Store.held.pop(str(_NODES["b1"].id))
        return pool, (question,), str(_NODES["b1"].id)
    if case == "chunk-changed":
        wrong = chunks[1].model_copy(update={"content_sha256": "0" * 64})
        return _pool((question, (chunks[0], wrong), False)), (question,), str(_NODES["b1"].id)
    if case == "rows-before":
        _Store.rows = len(_NODES) + 1
        return pool, (question,), "row"
    _Store.count_after_first_get = len(_NODES) - 1
    return pool, (question,), "row"


@pytest.mark.parametrize(
    "case",
    [
        "question-text",
        "relevant-set",
        "question-not-captured",
        "question-not-asked",
        "chunk-missing",
        "chunk-changed",
        "rows-before",
        "rows-after",
    ],
)
async def test_a_pool_that_no_longer_matches_what_it_is_replayed_against_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    # Arrange
    pool, questions, named = _moved(case)

    # Act
    with pytest.raises(PoolIntegrityError) as caught:
        await _replay(monkeypatch, pool, questions)

    # Assert
    assert named in str(caught.value)


async def test_a_promotion_lifting_the_relevant_passage_from_third_to_first_scores_it_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — ledger 40.3's fixture: packed by `reverse`, scored on (-score, rank).
    question = _question("q-anchored", "what does WRH123 mean", ("doc-w.txt",))
    pool = _pool((question, (_chunk("a1", 0.9), _chunk("b1", 0.8), _chunk("w1", 0.7)), True))

    # Act
    scored = await _replay(monkeypatch, pool, (question,), through="replay-promote")

    # Assert
    assert _reciprocal_ranks(scored) == {"q-anchored": 1.0}
