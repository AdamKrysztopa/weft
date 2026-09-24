"""A run records its target, and a live target compares against another embedder's.

A run records the target it scored, and `weft eval compare` compares a live target with a
candidate built by another embedder — ledger task **34.7**, owner decision Q-E.

`_incomparable_reasons` refuses two runs whose `model_versions` differ, which is `09` §4's V3:
a metric delta across model versions is not evidence about a technique. A promotion is not a
technique claim. It asks whether a candidate index answers these questions at least as well as the
live one, and the embedder is exactly what changed. So when both runs name different targets, and
corpus and question set agree, the embedding difference is printed as the comparison's
**subject** instead of refusing it. Two runs of one target still refuse, and V3 holds for them.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from weft_cli.eval_commands import (
    EvalCompareArgs,
    EvalCompareCommand,
    EvalRunArgs,
    EvalRunCommand,
    EvalRunCommandResult,
)
from weft_cli.render import render_outcome
from weft_engine.registry_bootstrap import Dependencies, build_dependencies
from weft_eval.run_record import load_run_record
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_store.contract import EmbeddingIdentity

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


def _ctx(deps: Dependencies) -> Context:
    context = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    context.services.add(Dependencies, deps)
    return context


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_promotion_{uuid4().hex[:12]}"
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield f"{_DSN.rsplit('/', 1)[0]}/{name}"
    finally:
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()


def _project(root: Path) -> Path:
    """A corpus, two pipelines differing only in the embedder's width, and one question set."""
    corpus = root / "corpus"
    corpus.mkdir()
    pumps = corpus / "pumps.txt"
    valves = corpus / "valves.txt"
    pumps.write_text("Pumps move water uphill using a rotating impeller.", encoding="utf-8")
    valves.write_text("Valves control flow by opening and closing a passage.", encoding="utf-8")
    pipelines = root / "pipelines"
    pipelines.mkdir()
    (pipelines / "narrow.yaml").write_text(
        "name: narrow\nstages:\n  - id: extract\n    use: text\n  - id: chunk\n"
        "    use: fixed-size\n  - id: embed\n    use: hash\n  - id: store\n    use: pgvector\n",
        encoding="utf-8",
    )
    (pipelines / "wide.yaml").write_text(
        "name: wide\nextends: narrow\nset:\n  - id: embed\n    with: {dimension: 128}\n",
        encoding="utf-8",
    )
    questions = root / "questions.json"
    questions.write_text(
        json.dumps(
            [
                {"query": "what moves water", "relevant_documents": [str(pumps.resolve())]},
                {"query": "what controls flow", "relevant_documents": [str(valves.resolve())]},
            ]
        ),
        encoding="utf-8",
    )
    return corpus


async def _run(deps: Dependencies, corpus: Path, pipeline: str, target: str | None) -> str:
    outcome = await EvalRunCommand().run(
        EvalRunArgs(
            path=str(corpus),
            pipeline=pipeline,
            corpus_name="demo",
            questions="questions.json",
            top_k=2,
            target=target,
        ),
        _ctx(deps),
    )
    assert isinstance(outcome, Produced)
    return cast(EvalRunCommandResult, outcome.value).run_id


async def test_a_live_and_a_candidate_target_compare_with_the_embedder_as_the_subject(
    dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("WEFT_DATABASE_URL", dsn)
    monkeypatch.chdir(tmp_path)
    corpus = _project(tmp_path)
    deps = build_dependencies(config_path=tmp_path / "weft.toml")
    live_run = await _run(deps, corpus, "narrow", None)
    candidate_run = await _run(deps, corpus, "wide", "w128")

    # Act
    compared = await EvalCompareCommand().run(
        EvalCompareArgs(a=live_run, b=candidate_run), _ctx(deps)
    )
    rendered = render_outcome(compared)

    # Assert — each record names the target it scored and the identity that built it.
    live_record = load_run_record(tmp_path / "runs" / f"{live_run}.json")
    candidate_record = load_run_record(tmp_path / "runs" / f"{candidate_run}.json")
    assert live_record.target == "default"
    assert candidate_record.target == "w128"
    assert candidate_record.target_embedding == EmbeddingIdentity(
        plugin="hash", distribution="weft-rag", model="hash", width=128
    )
    assert rendered.exit_code == 0
    assert rendered.stdout is not None
    assert "default → w128" in rendered.stdout
    assert "width 64" in rendered.stdout
    assert "width 128" in rendered.stdout
