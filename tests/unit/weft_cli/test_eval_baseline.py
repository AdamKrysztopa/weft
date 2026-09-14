"""`weft eval baseline` — ledger repair **R22.4c**: the pipeline it runs, and what it refuses.

Nothing here reaches a store, so none of it needs a container; the run itself is
`tests/integration/test_eval_baseline.py`. Every refusal below happens before the corpus is staged,
and each test checks that by looking for the working directory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

import weft_eval
from tests.discovery import discover_for_tests
from weft_cli.compile import contracts_for
from weft_cli.eval_baseline import (
    BaselineOutputExistsError,
    BaselineRunError,
    EvalBaselineArgs,
    EvalBaselineCommand,
)
from weft_cli.pipeline_catalogue import load_pipeline_catalogue
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_eval.baseline import DepthTooShallowError, judge_reproduction, load_baseline_report
from weft_eval.corpus_manifest import Tier
from weft_kernel.context import Context
from weft_kernel.resolution import resolve

_PUBLISHED = (
    Path(__file__).resolve().parents[3] / "eval" / "baselines" / "8854c33f71ea-2026-08-25.json"
)

_BODIES = {
    "doc-a": b"# Alpha\n\nThe alpha passage names the kestrel.\n",
    "doc-b": b"# Beta\n\nThe beta passage names the heron.\n",
}


def _corpus(directory: Path) -> tuple[Path, Path]:
    """A two-document fetch-tier manifest with its bytes on disk, and one question over it."""
    entries: list[str] = []
    for identifier, body in _BODIES.items():
        path = directory / "wiki" / f"{identifier}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        entries.append(
            f'[[document]]\nid = "{identifier}"\npath = "wiki/{identifier}.md"\n'
            f'format = "markdown"\nlanguage = "en"\n'
            f'sha256 = "{hashlib.sha256(body).hexdigest()}"\ntier = "fetch"\n'
            f'source = "https://example.org/{identifier}"\n'
        )
    manifest = directory / "manifest.toml"
    manifest.write_text('[corpus]\nname = "tiny"\n\n' + "\n".join(entries), encoding="utf-8")
    questions = directory / "questions"
    questions.mkdir()
    (questions / "set.toml").write_text(
        '[[question]]\nid = "q-a"\ntext = "What does the alpha passage name?"\nlanguage = "en"\n'
        'kind = "definitional"\ndifficulty = "easy"\nrelevant_documents = ["doc-a"]\n'
        'reference_answer = "The kestrel."\nnotes = "written for this test"\n\n'
        '  [[question.quote]]\n  document = "doc-a"\n  page = 0\n  text = "names the kestrel"\n',
        encoding="utf-8",
    )
    return manifest, questions


def _args(directory: Path, **overrides: object) -> EvalBaselineArgs:
    fields: dict[str, object] = {
        "manifest": str(directory / "manifest.toml"),
        "questions": str(directory / "questions"),
        "workdir": str(directory / "work"),
    }
    return EvalBaselineArgs.model_validate(fields | overrides)


def _ctx() -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(
        Dependencies,
        Dependencies(registry=discover_for_tests(), reports=(), services=ServiceSelection()),
    )
    return ctx


def test_the_shipped_baseline_document_is_the_pipeline_the_published_record_names() -> None:
    # Arrange
    registry = discover_for_tests()
    catalogue = load_pipeline_catalogue(Path(weft_eval.__file__).parent / "pipelines")
    document = catalogue["baseline"]
    published = load_baseline_report(_PUBLISHED)

    # Act
    resolved = resolve(
        document,
        registry=registry,
        contracts=contracts_for(document, registry=registry, parents=catalogue, reports=()),
        parents=catalogue,
    )
    shipped = published.model_copy(
        update={"record": published.record.model_copy(update={"resolved_pipeline": resolved})}
    )
    reproduction = judge_reproduction(published, shipped)

    # Assert
    assert [stage.use for stage in resolved.stages] == ["text", "fixed-size", "hash", "qdrant"]
    assert reproduction.reproduced


async def test_an_unknown_tier_is_refused_naming_every_tier(tmp_path: Path) -> None:
    # Arrange
    _corpus(tmp_path)

    # Act
    with pytest.raises(BaselineRunError) as caught:
        await EvalBaselineCommand().run(_args(tmp_path, tiers="fetch,borrowed"), _ctx())

    # Assert
    message = str(caught.value)
    assert "'borrowed'" in message
    assert all(tier.value in message for tier in Tier)
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize(
    ("damage", "document", "status"),
    [("overwrite", "doc-a", "corrupt"), ("delete", "doc-b", "missing")],
)
async def test_a_selected_document_that_does_not_verify_is_refused_before_staging(
    tmp_path: Path, damage: str, document: str, status: str
) -> None:
    # Arrange
    _corpus(tmp_path)
    path = tmp_path / "wiki" / f"{document}.md"
    if damage == "overwrite":
        path.write_bytes(b"# Something else\n")
    else:
        path.unlink()

    # Act
    with pytest.raises(BaselineRunError) as caught:
        await EvalBaselineCommand().run(_args(tmp_path), _ctx())

    # Assert
    assert document in str(caught.value)
    assert status in str(caught.value)
    assert not (tmp_path / "work").exists()


async def test_a_depth_deeper_than_the_retrieval_is_refused_before_staging(tmp_path: Path) -> None:
    # Arrange
    _corpus(tmp_path)

    # Act
    with pytest.raises(DepthTooShallowError) as caught:
        await EvalBaselineCommand().run(_args(tmp_path, depths="5,20", top_k=10), _ctx())

    # Assert
    assert "20" in str(caught.value)
    assert not (tmp_path / "work").exists()


async def test_a_report_path_that_already_exists_is_refused_before_staging(tmp_path: Path) -> None:
    # Arrange
    _corpus(tmp_path)
    out = tmp_path / "report.json"
    out.write_text("{}", encoding="utf-8")

    # Act
    with pytest.raises(BaselineOutputExistsError) as caught:
        await EvalBaselineCommand().run(_args(tmp_path, out=str(out)), _ctx())

    # Assert
    assert str(out) in str(caught.value)
    assert out.read_text(encoding="utf-8") == "{}"
    assert not (tmp_path / "work").exists()


def test_a_single_repetition_is_refused_as_an_argument(tmp_path: Path) -> None:
    # V3: a baseline run once "records no interval and no later run can be judged against it".
    # Act / Assert
    with pytest.raises(ValidationError, match="repeats"):
        _args(tmp_path, repeats=1)
