"""`weft eval experiment` — carried repair **R20.2**: no arm is scored over a partly indexed corpus.

`R36.1` refuses a corpus holding a document an *earlier* index failed. A document whose batch the
embedder answers `Failed` during the run itself was not refused: the arm was scored without it while
its record's corpus identity named the whole corpus. And the refusal's remedy, `weft index
--retry-failed`, named no pipeline or target, so since 20.11 it repaired the live target rather
than the `exp_` target the arm indexes into. Both refusals now name `--pipeline` and `--target`.

Indexing is real — `TextExtractor`, `FixedSizeChunker`, an embedder that fails one document while
told to, one document per batch, into a `MemoryStore`. Scoring is stubbed where
`test_eval_experiment_targets.py` stubs it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest

from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli import eval_commands as eval_commands_module
from weft_cli import ingest as ingest_module
from weft_cli import route_ask as route_ask_module
from weft_cli.eval_commands import CorpusHasFailedSourcesError
from weft_cli.eval_experiment import EvalExperimentArgs, EvalExperimentCommand
from weft_cli.eval_scoring import ScoredRun
from weft_cli.ingest import run_index_for
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_eval import Settings, register
from weft_eval.experiment import EXPERIMENT_SCHEMA_VERSION
from weft_eval.question_set import Question, question_set_digest
from weft_eval.run_record import NoQueryRung, PerQuestionScores, QuestionKey
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, Node, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_store import NodeStore
from weft_store.memory import MemoryStore


class _ServerDownError(WeftError):
    """What an embedder raises when its server stays unreachable past every retry."""


class _OutageEmbedder(HashEmbedder):
    """`hash`, except on the warp document: raises while `down`, `Failed` while `refusing`."""

    down: ClassVar[bool] = False
    refusing: ClassVar[bool] = False

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        if any("warp" in node.content for node in payload):
            if type(self).down:
                raise _ServerDownError("could not reach the embeddings server")
            if type(self).refusing:
                return Failed(reason="the server refused this document")
        return await super().run(payload, ctx)


def _catalogue() -> dict[str, Pipeline]:
    return {
        "index-outage": Pipeline(
            name="index-outage",
            stages=(
                StageDeclaration(id="extract", use="text"),
                StageDeclaration(id="chunk", use="fixed-size"),
                StageDeclaration(id="embed", use="outage"),
                StageDeclaration(id="store", use="memory"),
            ),
        ),
    }


def _stub_catalogue(catalogue: dict[str, Pipeline]) -> Callable[..., dict[str, Pipeline]]:
    def _full_catalogue(
        *, directory: Path = Path("pipelines"), reports: Sequence[object] = ()
    ) -> dict[str, Pipeline]:
        del directory, reports
        return catalogue

    return _full_catalogue


def _deps(store: MemoryStore) -> Dependencies:
    def _store_factory(config: object) -> MemoryStore:
        del config
        return store

    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "outage", _OutageEmbedder, distribution="test")
    registry.add(NodeStore, "memory", _store_factory, distribution="weft-store")
    return Dependencies(registry=registry, reports=(), services=ServiceSelection(store="memory"))


def _ctx(store: MemoryStore) -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, _deps(store))
    return ctx


_QUESTIONS = """[question_set]
schema = 2
absent = ["kind", "difficulty", "quote", "reference_answer", "notes"]
absent_reason = "an experiment fixture"
axes = []

[[question]]
id = "q-1"
text = "what is weft?"
language = "en"
relevant_documents = ["one.txt"]

[[question]]
id = "q-2"
text = "what is a warp?"
language = "en"
relevant_documents = ["two.txt"]
"""


def _experiment(root: Path) -> Path:
    project = root / "project"
    (project / "corpus").mkdir(parents=True, exist_ok=True)
    (project / "corpus" / "one.txt").write_text("weft is the thread across", encoding="utf-8")
    (project / "corpus" / "two.txt").write_text("a warp runs lengthwise", encoding="utf-8")
    (project / "questions.toml").write_text(_QUESTIONS, encoding="utf-8")
    path = project / "experiment.toml"
    path.write_text(
        f"[experiment]\nschema = {EXPERIMENT_SCHEMA_VERSION}\n"
        'name = "outage"\nquestions = "questions.toml"\ncorpus = "corpus"\n'
        'repeats = 2\ntop_k = 5\nmetrics = ["precision@5"]\n'
        "minimum_detectable_effect = 0.05\nindex_batch_size = 1\n"
        '\n[[arm]]\nname = "first"\npipeline = "index-outage"\nrepeats = 1\n'
        '\n[[arm]]\nname = "again"\npipeline = "index-outage"\nrepeats = 1\n',
        encoding="utf-8",
    )
    return path


def _scoring_stub(calls: list[dict[str, Any]]) -> Callable[..., Any]:
    async def _fake(**kwargs: Any) -> ScoredRun:
        calls.append(kwargs)
        questions = cast("tuple[Question, ...]", kwargs["questions"])
        return ScoredRun(
            metrics={},
            query_rung=NoQueryRung(reason="stub"),
            question_scores={
                "precision@5": PerQuestionScores(
                    keyed_by=QuestionKey.QUESTION_ID,
                    scores={question.id: Produced(value=1.0) for question in questions},
                )
            },
            question_set=question_set_digest(questions),
        )

    return _fake


@pytest.fixture(autouse=True)
def in_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "cwd"
    run_dir.mkdir()
    monkeypatch.chdir(run_dir)
    monkeypatch.setattr(ingest_module, "full_catalogue", _stub_catalogue(_catalogue()))
    monkeypatch.setattr(route_ask_module, "full_catalogue", _stub_catalogue(_catalogue()))
    monkeypatch.setattr(_OutageEmbedder, "down", False)
    monkeypatch.setattr(_OutageEmbedder, "refusing", False)


async def test_a_document_that_fails_in_this_run_is_refused_before_scoring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    store = MemoryStore()
    path = _experiment(tmp_path)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))
    monkeypatch.setattr(_OutageEmbedder, "refusing", True)

    # Act
    with pytest.raises(CorpusHasFailedSourcesError) as raised:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx(store))

    # Assert
    message = str(raised.value)
    assert "failed while this run indexed them" in message
    assert "--pipeline index-outage" in message
    assert re.search(r"--target exp_[0-9a-f]{32}", message) is not None
    assert "--retry-failed" in message
    assert calls == []
    assert list(Path("runs").glob("*.json")) == []


async def test_after_an_outage_the_printed_remedy_lets_the_experiment_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An outage aborts the run, the rerun is refused naming a remedy, and that remedy works."""
    # Arrange
    store = MemoryStore()
    path = _experiment(tmp_path)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_commands_module, "score_pipeline", _scoring_stub(calls))
    monkeypatch.setattr(_OutageEmbedder, "down", True)
    with pytest.raises(_ServerDownError):
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx(store))
    monkeypatch.setattr(_OutageEmbedder, "down", False)
    with pytest.raises(CorpusHasFailedSourcesError) as refused:
        await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx(store))
    printed = re.search(r"--pipeline (\S+) --target (exp_[0-9a-f]{32})", str(refused.value))
    assert printed is not None, f"the remedy names no pipeline and target: {refused.value}"
    await run_index_for(
        _deps(store),
        path.parent / "corpus",
        ctx=_ctx(store),
        pipeline=printed.group(1),
        target=printed.group(2),
        retry_failed=True,
    )

    # Act
    outcome = await EvalExperimentCommand().run(EvalExperimentArgs(path=str(path)), _ctx(store))

    # Assert
    assert isinstance(outcome, Produced)
    assert len(calls) == 2, "both arms are scored once the corpus is whole"
