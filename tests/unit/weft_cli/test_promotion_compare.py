"""A target change turns an embedding-model difference from a refusal into the comparison's subject.

`weft eval compare` treats two runs over two targets as a promotion comparison — ledger task
**34.7**, owner decision Q-E, at the seam that decides comparability.

Each fixture varies one fact. The records share corpus and question set and differ in embedding
model, which V3 refuses, and in target, which is what turns that difference into the subject.
Holding the rest fixed keeps each assertion about the fact under test (`L12.6`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_cli.eval_commands import (
    EvalCompareArgs,
    EvalCompareCommand,
    EvalCompareCommandResult,
    IncomparableRunsError,
)
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_eval.run_record import CorpusIdentity, build_run_record, write_run_record
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline
from weft_store.contract import EmbeddingIdentity

_SMALL = EmbeddingIdentity(
    plugin="openai-embeddings",
    distribution="weft-rag",
    model="text-embedding-3-small",
    width=None,
)
_LARGE = _SMALL.model_copy(update={"model": "text-embedding-3-large"})


def _ctx() -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(
        Dependencies, Dependencies(registry=Registry(), reports=(), services=ServiceSelection())
    )
    return ctx


def _write(
    directory: Path,
    run_id: str,
    *,
    target: str | None,
    embedding: EmbeddingIdentity,
    corpus_digest: str = "a" * 64,
    question_set_digest: str = "q" * 64,
) -> None:
    record = build_run_record(
        recorded_at="2026-09-22T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name="index-openai", stages=()),
        corpus=CorpusIdentity(name="corpus", digest=corpus_digest),
        model_versions={"embed": f"openai-embeddings:{embedding.model}"},
        metrics={},
        question_set_digest=question_set_digest,
        target=target,
        target_embedding=embedding,
    )
    write_run_record(record, directory / "runs" / f"{run_id}.json")


@pytest.fixture(autouse=True)
def in_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


async def test_two_targets_built_by_two_models_compare_with_the_model_as_the_subject(
    tmp_path: Path,
) -> None:
    # Arrange
    _write(tmp_path, "live", target="default", embedding=_SMALL)
    _write(tmp_path, "candidate", target="large", embedding=_LARGE)

    # Act
    outcome = await EvalCompareCommand().run(EvalCompareArgs(a="live", b="candidate"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, EvalCompareCommandResult)
    assert result.targets == ("default", "large")
    assert any("text-embedding-3-small" in part for part in result.subject)
    assert any("text-embedding-3-large" in part for part in result.subject)


async def test_two_runs_of_one_target_that_differ_in_model_are_still_refused(
    tmp_path: Path,
) -> None:
    """V3 is untouched where no promotion is being judged."""
    # Arrange
    _write(tmp_path, "a", target="default", embedding=_SMALL)
    _write(tmp_path, "b", target="default", embedding=_LARGE)

    # Act / Assert
    with pytest.raises(IncomparableRunsError) as caught:
        await EvalCompareCommand().run(EvalCompareArgs(a="a", b="b"), _ctx())
    assert any("model" in reason for reason in caught.value.reasons)


async def test_runs_that_name_no_target_keep_the_old_refusal(tmp_path: Path) -> None:
    """A record written before `34.7` names no target, and is judged exactly as before."""
    # Arrange
    _write(tmp_path, "a", target=None, embedding=_SMALL)
    _write(tmp_path, "b", target=None, embedding=_LARGE)

    # Act / Assert
    with pytest.raises(IncomparableRunsError):
        await EvalCompareCommand().run(EvalCompareArgs(a="a", b="b"), _ctx())


@pytest.mark.parametrize(
    "differs",
    [{"corpus_digest": "b" * 64}, {"question_set_digest": "r" * 64}],
    ids=["corpus", "question-set"],
)
async def test_two_targets_over_different_corpora_or_questions_are_refused(
    tmp_path: Path, differs: dict[str, str]
) -> None:
    # Arrange
    _write(tmp_path, "live", target="default", embedding=_SMALL)
    _write(tmp_path, "candidate", target="large", embedding=_LARGE, **differs)

    # Act / Assert
    with pytest.raises(IncomparableRunsError):
        await EvalCompareCommand().run(EvalCompareArgs(a="live", b="candidate"), _ctx())
