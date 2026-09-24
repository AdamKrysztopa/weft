"""`--target` on every command that touches a store, and `weft target list` — ledger task **34.6**.

Driven through the embedded API, `Weft.open` over a `weft.toml` naming a database this test owns,
because that is the same assembly the CLI runs (`weft_engine.api` → `build_dependencies`) and it
reaches each command's real `run`. A candidate is built beside the live target by `weft index
--target`, created on its first write; every command that only reads a target refuses one that
does not exist, naming every target that does (FF12). `default` stays what it was.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from weft_cli.commands import (
    AskCommandResult,
    SourcesListCommandResult,
    TargetListCommandResult,
)
from weft_engine.api import Weft
from weft_store.contract import DEFAULT_TARGET, EmbeddingIdentity, UnknownTargetError

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


@pytest.fixture
async def project(tmp_path: Path) -> AsyncIterator[Path]:
    """A corpus and a `weft.toml` naming a database of this test's own, dropped by exact name."""
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_target_cmds_{uuid4().hex[:12]}"
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "pumps.txt").write_text("Pumps move water uphill using a rotating impeller.")
    (corpus / "valves.txt").write_text("Valves control flow by opening and closing a passage.")
    dsn = f"{_DSN.rsplit('/', 1)[0]}/{name}"
    (tmp_path / "weft.toml").write_text(f'[packs.store]\ndsn = "{dsn}"\n')
    try:
        yield tmp_path
    finally:
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()


async def test_index_with_a_target_builds_a_candidate_and_leaves_the_live_target_alone(
    project: Path,
) -> None:
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        # Act
        await w.index(project / "corpus", target="w128")
        live = await w.run("sources list", {})
        candidate = await w.run("sources list", {"target": "w128"})
        listed = await w.run("target list", {})

    # Assert
    assert isinstance(live, SourcesListCommandResult)
    assert isinstance(candidate, SourcesListCommandResult)
    assert isinstance(listed, TargetListCommandResult)
    assert live.sources == ()
    assert len(candidate.sources) == 2
    by_name = {target.name: target for target in listed.targets}
    assert by_name[DEFAULT_TARGET].live
    assert by_name[DEFAULT_TARGET].sources == 0
    assert not by_name["w128"].live
    assert not by_name["w128"].previous
    assert by_name["w128"].sources == 2
    assert by_name["w128"].embedding == EmbeddingIdentity(
        plugin="hash", distribution="weft-rag", model="hash", width=64
    )


async def test_asking_a_target_reads_that_target(project: Path) -> None:
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        await w.index(project / "corpus", target="w128")

        # Act
        from_candidate = await w.run(
            "ask", {"question": "what moves water", "retrieve_only": True, "target": "w128"}
        )
        from_live = await w.run("ask", {"question": "what moves water", "retrieve_only": True})

    # Assert
    assert isinstance(from_candidate, AskCommandResult)
    assert isinstance(from_live, AskCommandResult)
    assert from_candidate.hits
    assert from_live.hits == ()


@pytest.mark.parametrize(
    ("command", "fields"),
    [
        ("ask", {"question": "what moves water", "retrieve_only": True}),
        ("sources list", {}),
        ("reconcile", {}),
    ],
)
async def test_a_read_against_a_target_that_does_not_exist_is_refused_naming_those_that_do(
    project: Path, command: str, fields: dict[str, object]
) -> None:
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        await w.index(project / "corpus", target="w128")

        # Act / Assert
        with pytest.raises(UnknownTargetError) as caught:
            await w.run(command, {**fields, "target": "w256"}, yes=True)
    assert set(caught.value.valid_options) == {DEFAULT_TARGET, "w128"}
    assert "'w256'" in str(caught.value)


async def test_a_second_index_into_the_same_candidate_reports_it_unchanged(project: Path) -> None:
    """A candidate is an ordinary target once it exists: change detection runs inside it."""
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        await w.index(project / "corpus", target="w128")

        # Act
        await w.index(project / "corpus", target="w128")
        candidate = await w.run("sources list", {"target": "w128"})

    # Assert
    assert isinstance(candidate, SourcesListCommandResult)
    assert len(candidate.sources) == 2


async def test_the_pass_after_indexing_a_candidate_reconciles_that_candidate(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found running the binary at `34.6`: the automatic post-index `reconcile` converged the
    live target while the run had written into the candidate. The wire is checked along its
    length by capturing the call (`L9.79`).
    """
    # Arrange
    from weft_cli.reconcile import reconcile_everywhere as real

    seen: list[str | None] = []

    async def spy(*args: object, **kwargs: object) -> object:
        seen.append(cast("str | None", kwargs.get("target")))
        return await cast("Any", real)(*args, **kwargs)

    monkeypatch.setattr("weft_cli.commands.reconcile_everywhere", spy)

    # Act
    async with Weft.open(project / "weft.toml") as w:
        await w.index(project / "corpus", target="w128")

    # Assert
    assert seen == ["w128"]
