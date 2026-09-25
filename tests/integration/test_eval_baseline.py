"""`weft eval baseline` against a real store — ledger repair **R22.4c**.

The procedure the reproduction archive documents, run in this process: stage a manifest's tier,
index it through the shipped `baseline` pipeline, retrieve every question it can score more than
once, and write the published report's shape. Qdrant, in a collection of its own per test, because
the `baseline` document names it and the published numbers were measured on it.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from weft_cli.eval_baseline import (
    BaselineStoreNotIsolatedError,
    EvalBaselineArgs,
    EvalBaselineCommand,
    EvalBaselineCommandResult,
)
from weft_cli.ingest import run_index
from weft_engine.registry_bootstrap import Dependencies, build_dependencies
from weft_eval.baseline import ExclusionKind, judge_reproduction, load_baseline_report
from weft_eval.run_record import CorpusDigestBasis, corpus_identity
from weft_kernel.context import Context
from weft_kernel.payload import Produced

_QDRANT_URL = os.environ.get("WEFT_QDRANT_URL", "http://localhost:6333")
_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

#: id → (path under the archive, format, tier, bytes). `doc-d` is declared and never written, as a
#: copyrighted paper is; its digest is over the bytes a holder of it would have.
_DOCUMENTS: dict[str, tuple[str, str, str, bytes]] = {
    "doc-a": (
        "wiki/doc-a.md",
        "markdown",
        "fetch",
        b"# Alpha\n\nThe alpha passage names the kestrel.\n",
    ),
    "doc-b": (
        "wiki/doc-b.md",
        "markdown",
        "fetch",
        b"# Beta\n\nThe beta passage names the heron.\n",
    ),
    "doc-c": (
        "arxiv/doc-c.pdf",
        "pdf",
        "fetch",
        b"%PDF-1.4 bytes the text extractor never claims\n",
    ),
    "doc-d": ("papers/doc-d.md", "markdown", "operator", b"# Delta\n"),
}

_QUESTION = """[[question]]
id = "{id}"
text = "What does {document} say?"
language = "en"
kind = "definitional"
difficulty = "easy"
relevant_documents = ["{document}"]
reference_answer = "{quote}"
notes = "written for this test"

  [[question.quote]]
  document = "{document}"
  page = 0
  text = "{quote}"
"""

_UNANSWERABLE = """[[question]]
id = "q-none"
text = "What does the corpus say about the albatross?"
language = "en"
kind = "unanswerable"
difficulty = "hard"
reference_answer = "Nothing."
notes = "written for this test"
"""


async def _qdrant_unreachable() -> str | None:
    client = AsyncQdrantClient(url=_QDRANT_URL, timeout=2)
    try:
        await client.info()
    except (OSError, ValueError, UnexpectedResponse, ResponseHandlingException) as exc:
        return (
            f"WEFT_QDRANT_URL ({_QDRANT_URL}) is unreachable: {exc}. "
            f"`docker compose --profile conformance up -d qdrant`."
        )
    finally:
        await client.close()
    return None


def _write_archive(archive: Path) -> None:
    entries: list[str] = []
    for identifier, (relative, fmt, tier, body) in _DOCUMENTS.items():
        if tier == "fetch":
            (archive / relative).parent.mkdir(parents=True, exist_ok=True)
            (archive / relative).write_bytes(body)
        source = f'source = "https://example.org/{identifier}"\n' if tier == "fetch" else ""
        entries.append(
            f'[[document]]\nid = "{identifier}"\npath = "{relative}"\nformat = "{fmt}"\n'
            f'language = "en"\nsha256 = "{hashlib.sha256(body).hexdigest()}"\n'
            f'tier = "{tier}"\n{source}'
        )
    (archive / "corpus-manifest.toml").write_text(
        '[corpus]\nname = "tiny"\n\n' + "\n".join(entries), encoding="utf-8"
    )
    questions = archive / "questions"
    questions.mkdir()
    (questions / "set.toml").write_text(
        _QUESTION.format(id="q-a", document="doc-a", quote="names the kestrel")
        + _QUESTION.format(id="q-b", document="doc-b", quote="names the heron")
        + _QUESTION.format(id="q-c", document="doc-c", quote="never claims")
        + _QUESTION.format(id="q-d", document="doc-d", quote="Delta")
        + _UNANSWERABLE,
        encoding="utf-8",
    )


@pytest.fixture
async def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    reason = await _qdrant_unreachable()
    if reason is not None:
        pytest.skip(reason)
    collection = f"weft_baseline_{uuid4().hex[:12]}"
    (tmp_path / "weft.toml").write_text(
        f'[packs.qdrant]\nurl = "{_QDRANT_URL}"\ncollection = "{collection}"\nvector_size = 64\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    monkeypatch.chdir(tmp_path)
    _write_archive(tmp_path / "archive")
    yield tmp_path
    client = AsyncQdrantClient(url=_QDRANT_URL)
    for suffix in ("", "__sources", "__targets", "__generations"):
        name = f"{collection}{suffix}"
        if await client.collection_exists(name):
            await client.delete_collection(name)
    listed = (await client.get_collections()).collections
    await client.close()
    # R43.49: a companion collection the store creates and this teardown does not name is left
    # in the container on every run; 196 had accumulated when it was found.
    assert [c.name for c in listed if c.name.startswith(collection)] == []


def _refuse_a_subprocess(*args: object, **kwargs: object) -> None:
    raise AssertionError(f"a subprocess was started: {args!r} {kwargs!r}")


def _ctx(deps: Dependencies) -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


def _args(project: Path, out: str, **overrides: object) -> EvalBaselineArgs:
    fields: dict[str, object] = {
        "manifest": str(project / "archive" / "corpus-manifest.toml"),
        "questions": str(project / "archive" / "questions"),
        "repeats": 2,
        "top_k": 2,
        "depths": "1,2",
        "workdir": str(project / "work"),
        "out": str(project / out),
    }
    return EvalBaselineArgs.model_validate(fields | overrides)


async def test_a_baseline_is_taken_in_process_and_a_second_run_reproduces_it(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setattr(subprocess, "run", _refuse_a_subprocess)
    monkeypatch.setattr(subprocess, "Popen", _refuse_a_subprocess)
    deps = build_dependencies(project / "weft.toml")

    # Act
    first = await EvalBaselineCommand().run(_args(project, "first.json"), _ctx(deps))
    second = await EvalBaselineCommand().run(_args(project, "second.json"), _ctx(deps))

    # Assert
    assert isinstance(first, Produced)
    assert isinstance(first.value, EvalBaselineCommandResult)
    assert isinstance(second, Produced)
    assert isinstance(second.value, EvalBaselineCommandResult)
    report = load_baseline_report(Path(first.value.path))
    assert report.documents == ("doc-a", "doc-b")
    assert report.questions == ("q-a", "q-b", "q-none")
    assert report.tiers == ("fetch",)
    assert report.extractor == "text"
    assert report.repeats == 2
    assert all(len(record.values) == 2 for record in report.metrics)
    assert {record.metric for record in report.metrics} == {
        f"{granularity}-{name}@{k}"
        for granularity in ("quote", "document")
        for name in ("recall", "mrr", "ndcg")
        for k in (1, 2)
    }
    assert [(excluded.question_id, excluded.kind) for excluded in report.excluded] == [
        ("q-none", ExclusionKind.NO_JUDGEMENT),
        ("q-none", ExclusionKind.NO_JUDGEMENT),
    ]
    pipeline = report.record.resolved_pipeline
    assert pipeline.name == "baseline"
    assert [stage.use for stage in pipeline.stages] == ["text", "fixed-size", "hash", "qdrant"]
    assert report.record.corpus == corpus_identity(
        "tiny",
        (
            f"{identifier}\t{hashlib.sha256(_DOCUMENTS[identifier][3]).hexdigest()}"
            for identifier in ("doc-a", "doc-b")
        ),
    )
    assert report.record.corpus_digest_basis is CorpusDigestBasis.MANIFEST_DIGESTS
    reproduction = judge_reproduction(report, load_baseline_report(Path(second.value.path)))
    assert reproduction.reproduced
    assert reproduction.provenance == ()


async def test_a_store_holding_passages_this_run_did_not_stage_is_refused(project: Path) -> None:
    # Arrange
    deps = build_dependencies(project / "weft.toml")
    elsewhere = project / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "doc-z.md").write_text(
        "# Zeta\n\nA passage no manifest names, about the kestrel.\n", encoding="utf-8"
    )
    await run_index(
        elsewhere, registry=deps.registry, ctx=_ctx(deps), pipeline="baseline", reports=deps.reports
    )

    # Act
    with pytest.raises(BaselineStoreNotIsolatedError) as caught:
        await EvalBaselineCommand().run(
            _args(project, "polluted.json", top_k=3, depths="1"), _ctx(deps)
        )

    # Assert
    assert "doc-z" in str(caught.value)
    assert "'qdrant'" in str(caught.value)
    assert not (project / "polluted.json").exists()
