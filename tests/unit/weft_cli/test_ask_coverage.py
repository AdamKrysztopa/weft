"""Task 43.4: `weft ask` says how much of the corpus it could see while an ingest is running.

The counts come from one `list_sources` read per store in use, the read `weft sources list`
already takes. The denominator is what the store has recorded, never the directory: a file no run
has reached yet is unknown to `weft ask`. `indexing` covers both a run in flight and one that was
interrupted, since the store cannot tell them apart. When every source is `ACTIVE`, the output is
byte-identical to a build without this task.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from weft_cli import commands, render
from weft_cli.commands import AskCommandResult
from weft_cli.coverage import SourceCoverage
from weft_cli.output import AskFormat
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_generate.payload import Answer, AnswerStance
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Produced, SourceId
from weft_kernel.registry import Registry
from weft_retrieve.payload import Query
from weft_store import NodeStore, SourceRecord, SourceStatus
from weft_store.memory import MemoryStore

_WHEN = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_STORES: list[MemoryStore] = []


def _store_factory(config: object) -> MemoryStore:
    del config
    return _STORES[-1]


def _null_factory(config: object) -> object:
    del config
    return object()


def _record(name: str, status: SourceStatus) -> SourceRecord:
    return SourceRecord(
        id=SourceId(f"file:///corpus/{name}"),
        uri=f"file:///corpus/{name}",
        content_hash=f"hash-{name}",
        indexed_at=_WHEN,
        pipeline="index-text",
        status=status,
    )


async def _ctx_with(records: tuple[SourceRecord, ...]) -> Context:
    _STORES.append(MemoryStore())
    for record in records:
        await _STORES[-1].put_source(record)
    registry = Registry()
    registry.add(NodeStore, "memory", _store_factory, distribution="weft-store")
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(pack="store", distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="memory"),
    )
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


def _answer(stance: AnswerStance = AnswerStance.ANSWERED) -> Answer:
    return Answer(
        origin=Query(text="what changed?"),
        text="the answer" if stance is AnswerStance.ANSWERED else "",
        stance=stance,
        citations=(),
        used=(),
        answered_by="scripted",
    )


def _result(
    coverage: SourceCoverage | None,
    *,
    stance: AnswerStance = AnswerStance.ANSWERED,
    format: AskFormat = AskFormat.TEXT,
) -> AskCommandResult:
    return AskCommandResult(
        question="what changed?",
        top_k=5,
        format=format,
        pipeline_name="retrieve-then-generate",
        answer=_answer(stance),
        coverage=coverage,
    )


_PARTIAL = SourceCoverage(indexed=412, failed=3, indexing=585)
_COMPLETE = SourceCoverage(indexed=1000, failed=0, indexing=0)


async def test_ask_counts_the_recorded_sources_by_status(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    ctx = await _ctx_with(
        (
            _record("a.txt", SourceStatus.ACTIVE),
            _record("b.txt", SourceStatus.ACTIVE),
            _record("c.txt", SourceStatus.FAILED),
            _record("d.txt", SourceStatus.INDEXING),
            _record("e.txt", SourceStatus.DELETING),
        )
    )

    async def _fake_run_routed_ask(*_args: object, **_kwargs: object) -> tuple[str, Answer]:
        return "retrieve-then-generate", _answer()

    monkeypatch.setattr(commands, "run_routed_ask", _fake_run_routed_ask)

    # Act
    outcome = await commands.AskCommand().run(commands.AskArgs(question="what changed?"), ctx)

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AskCommandResult)
    assert result.coverage == SourceCoverage(indexed=2, failed=1, indexing=1)


def test_coverage_is_complete_only_with_nothing_failed_or_indexing() -> None:
    assert _COMPLETE.complete
    assert not _PARTIAL.complete
    assert not SourceCoverage(indexed=5, failed=1, indexing=0).complete
    assert not SourceCoverage(indexed=5, failed=0, indexing=1).complete


def test_partial_coverage_is_stated_under_the_answer() -> None:
    # Act
    rendered = render.render_outcome(Produced(value=_result(_PARTIAL)))

    # Assert
    assert rendered.stdout is not None
    assert "sources: 412 indexed · 3 failed · 585 indexing" in rendered.stdout


def test_complete_coverage_leaves_the_output_byte_identical() -> None:
    # Act
    with_coverage = render.render_outcome(Produced(value=_result(_COMPLETE)))
    without = render.render_outcome(Produced(value=_result(None)))

    # Assert
    assert with_coverage == without


def test_no_evidence_with_sources_still_indexing_says_they_are_not_yet_indexed() -> None:
    # Act
    rendered = render.render_outcome(
        Produced(value=_result(_PARTIAL, stance=AnswerStance.NOT_IN_CORPUS))
    )

    # Assert
    assert rendered.stdout is not None
    assert "585 sources are not yet indexed" in rendered.stdout


def test_no_evidence_with_nothing_indexing_keeps_the_plain_refusal() -> None:
    # Arrange
    failed_only = SourceCoverage(indexed=997, failed=3, indexing=0)

    # Act
    rendered = render.render_outcome(
        Produced(value=_result(failed_only, stance=AnswerStance.NOT_IN_CORPUS))
    )

    # Assert
    assert rendered.stdout is not None
    assert "the corpus does not answer this." in rendered.stdout
    assert "not yet indexed" not in rendered.stdout


def test_the_json_envelope_carries_partial_coverage_and_omits_complete() -> None:
    # Act
    partial = render.render_outcome(
        Produced(value=_result(_PARTIAL, format=AskFormat.JSON)), as_json=True
    )
    complete = render.render_outcome(
        Produced(value=_result(_COMPLETE, format=AskFormat.JSON)), as_json=True
    )
    without = render.render_outcome(
        Produced(value=_result(None, format=AskFormat.JSON)), as_json=True
    )

    # Assert
    assert partial.stdout is not None
    assert json.loads(partial.stdout)["coverage"] == {
        "indexed": 412,
        "failed": 3,
        "indexing": 585,
    }
    assert complete == without


def test_a_retrieve_only_answer_states_partial_coverage_under_its_hits() -> None:
    # Arrange
    from weft_cli.ask import AskHit

    result = AskCommandResult(
        question="what changed?",
        top_k=5,
        format=AskFormat.TEXT,
        hits=(AskHit(rank=1, node_id="n1", score=0.9, content="first"),),
        coverage=_PARTIAL,
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout is not None
    assert "sources: 412 indexed · 3 failed · 585 indexing" in rendered.stdout


def test_no_matching_passages_still_states_partial_coverage() -> None:
    # Arrange
    result = AskCommandResult(
        question="what changed?", top_k=5, format=AskFormat.TEXT, hits=(), coverage=_PARTIAL
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout is not None
    assert "no matching passages found." in rendered.stdout
    assert "sources: 412 indexed · 3 failed · 585 indexing" in rendered.stdout
