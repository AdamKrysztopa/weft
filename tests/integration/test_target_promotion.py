"""`weft target promote|rollback|drop` — ledger tasks **34.8** and **34.9**.

A promote switches which target is live, and every reader that names no target follows it, so it
is gated on evidence: two persisted runs, the first scoring the live target and the second the
candidate, over one corpus and one question set. `eval compare` decides comparability with the
same code (Q-E, no second comparison logic). A candidate still being indexed or deleted, or one
whose embedder was never recorded, is refused whatever the evidence. `--without-evidence` is an
explicit override, and it is written onto the pointer. `--yes` only answers the prompt.
`rollback` restores the previous target, and `drop` refuses both targets a rollback needs.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr

from weft_cli.commands import TargetPromoteCommandResult
from weft_cli.eval_commands import EvalRunCommandResult
from weft_engine.api import Weft
from weft_engine.targets import (
    CandidateIdentityUnrecordedError,
    CandidateNotReadyError,
    EmbeddingIdentityMismatchError,
    PromotionEvidenceMismatchError,
    PromotionEvidenceMissingError,
)
from weft_kernel.payload import SourceId
from weft_store.contract import (
    DEFAULT_TARGET,
    SourceRecord,
    SourceStatus,
    TargetInUseError,
    target_name,
)
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


@pytest.fixture
async def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """A corpus, a narrow and a wide pipeline, one question set, and a database of its own."""
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_promote_{uuid4().hex[:12]}"
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = f"{_DSN.rsplit('/', 1)[0]}/{name}"
    monkeypatch.chdir(tmp_path)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    pumps = corpus / "pumps.txt"
    pumps.write_text("Pumps move water uphill using a rotating impeller.", encoding="utf-8")
    valves = corpus / "valves.txt"
    valves.write_text("Valves control flow by opening and closing a passage.", encoding="utf-8")
    pipelines = tmp_path / "pipelines"
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
    (tmp_path / "questions.toml").write_text(
        _toml_questions(
            [
                ("what moves water", str(pumps.resolve())),
                ("what controls flow", str(valves.resolve())),
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "weft.toml").write_text(f'[packs.store]\ndsn = "{dsn}"\n')
    try:
        yield tmp_path
    finally:
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()


async def _scored(w: Weft, pipeline: str, target: str | None) -> str:
    result = await w.run(
        "eval run",
        {
            "path": "corpus",
            "pipeline": pipeline,
            "corpus_name": "demo",
            "questions": "questions.toml",
            "top_k": 2,
            "target": target,
        },
    )
    return cast(EvalRunCommandResult, result).run_id


def _store(project: Path) -> PgVectorStore:
    dsn = (project / "weft.toml").read_text().split('"')[1]
    return PgVectorStore(PgVectorSettings(dsn=SecretStr(dsn)))


async def test_a_candidate_promoted_on_evidence_becomes_live_and_rollback_restores_it(
    project: Path,
) -> None:
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        live_run = await _scored(w, "narrow", None)
        candidate_run = await _scored(w, "wide", "w128")

        # Act
        promoted = await w.run(
            "target promote", {"name": "w128", "evidence": [live_run, candidate_run]}, yes=True
        )
        catalogue_after = await _store(project).target_catalogue()

        # Assert — the pointer switched and carries its evidence.
        assert isinstance(promoted, TargetPromoteCommandResult)
        assert catalogue_after.live == "w128"
        assert catalogue_after.previous == DEFAULT_TARGET
        assert catalogue_after.promotion is not None
        assert catalogue_after.promotion.evidence == (live_run, candidate_run)
        assert not catalogue_after.promotion.without_evidence
        assert catalogue_after.promotion.by

        # A reader naming no target now reads the candidate, so the old embedder is refused.
        with pytest.raises(EmbeddingIdentityMismatchError):
            await w.run("ask", {"question": "what moves water", "retrieve_only": True})
        with pytest.raises(TargetInUseError):
            await w.run("target drop", {"name": DEFAULT_TARGET}, yes=True)

        await w.run("target rollback", {}, yes=True)
        restored = await w.run("ask", {"question": "what moves water", "retrieve_only": True})
    assert (await _store(project).target_catalogue()).live == DEFAULT_TARGET
    assert restored is not None


async def test_a_promote_without_evidence_is_refused_naming_both_ways_forward(
    project: Path,
) -> None:
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        await _scored(w, "wide", "w128")

        # Act / Assert
        with pytest.raises(PromotionEvidenceMissingError) as caught:
            await w.run("target promote", {"name": "w128"}, yes=True)
    message = str(caught.value)
    assert "--evidence" in message
    assert "--without-evidence" in message
    assert (await _store(project).target_catalogue()).live == DEFAULT_TARGET


async def test_evidence_in_the_wrong_order_or_for_another_target_is_refused(project: Path) -> None:
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        live_run = await _scored(w, "narrow", None)
        candidate_run = await _scored(w, "wide", "w128")

        # Act / Assert — the first run must score the live target and the second the candidate.
        with pytest.raises(PromotionEvidenceMismatchError):
            await w.run(
                "target promote",
                {"name": "w128", "evidence": [candidate_run, live_run]},
                yes=True,
            )
    assert (await _store(project).target_catalogue()).live == DEFAULT_TARGET


async def test_the_override_is_written_onto_the_pointer(project: Path) -> None:
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        await _scored(w, "wide", "w128")

        # Act
        await w.run("target promote", {"name": "w128", "without_evidence": True}, yes=True)

    # Assert
    catalogue = await _store(project).target_catalogue()
    assert catalogue.live == "w128"
    assert catalogue.promotion is not None
    assert catalogue.promotion.without_evidence


async def test_a_candidate_still_indexing_is_not_promoted(project: Path) -> None:
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        await _scored(w, "wide", "w128")
        candidate = await _store(project).bind_target(target_name("w128"))
        await candidate.put_source(
            SourceRecord(
                id=SourceId("half-written"),
                uri="file:///half-written.txt",
                content_hash="h",
                indexed_at=datetime.now(UTC),
                pipeline="wide",
                status=SourceStatus.INDEXING,
            )
        )

        # Act / Assert
        with pytest.raises(CandidateNotReadyError) as caught:
            await w.run("target promote", {"name": "w128", "without_evidence": True}, yes=True)
    assert "half-written" in str(caught.value)


async def test_a_candidate_whose_embedder_was_never_recorded_is_not_promoted(
    project: Path,
) -> None:
    # Arrange — a target that exists only by a source record: no write ever claimed an identity.
    candidate = await _store(project).bind_target(target_name("w256"))
    await candidate.put_source(
        SourceRecord(
            id=SourceId("doc"),
            uri="file:///doc.txt",
            content_hash="h",
            indexed_at=datetime.now(UTC),
            pipeline="wide",
        )
    )

    # Act / Assert
    async with Weft.open(project / "weft.toml") as w:
        with pytest.raises(CandidateIdentityUnrecordedError) as caught:
            await w.run("target promote", {"name": "w256", "without_evidence": True}, yes=True)
    assert "'w256'" in str(caught.value)


def _toml_questions(pairs: list[tuple[str, str]]) -> str:
    """The TOML question set (the JSON list went at `weft-rag` 3.0.0, task 43.38)."""
    header = (
        '[question_set]\nschema = 2\nabsent = ["kind", "difficulty", "quote", "reference_answer", '
        '"notes"]\nabsent_reason = "an integration fixture"\naxes = []\n\n'
    )
    return header + "".join(
        f'[[question]]\nid = "{i}"\ntext = {json.dumps(text)}\nlanguage = "en"\n'
        f"relevant_documents = [{json.dumps(document)}]\n\n"
        for i, (text, document) in enumerate(pairs)
    )
