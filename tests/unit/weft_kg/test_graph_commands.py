"""`weft graph propose`, `activate` and `show` — the first `Command`s this pack ships. **11.11**.

Mirrors `packages/weft-rag/src/weft_kg/commands.py`. Against the real Postgres container, skipped
with a reason when it is absent, in the module-level form `test_store.py` uses and for the same
reason: every test here reads or writes the pack's own tables.

**The three answer three different questions and only one of them writes.** `propose` measures what
the corpus produced and **prints**; `activate` is the operator's decision, and is the only one that
touches anything; `show` reports what is true of the corpus now. That split is why the permission
classes differ, and `03` → *Permissions* makes a pack declare each at registration with no default.

**Why `activate` writes in two places, and why that is not redundancy — `S13`.** The **file** is
what an operator approves: a diffable artefact a pull request can show, named from `[packs.graph]`
so it is per project, which is what `weft.toml` has been since `03:909`. The **row** is what the
corpus is under. Answered from the file alone, *which schema is this corpus under* would be a
property of whichever operator's disk was asked, so two checkouts pointing at one database would
hold contradictory beliefs and nothing could notice — the silence this task's own line forbids.
`test_the_corpus_answers_for_itself_not_the_operator_s_disk` is that property.

**The row is keyed per database, and that is a narrowing of `S13`'s wording — settled with the
owner 2026-09-10.** `S13` says *keyed by collection*. There is no collection in this tree: `03`
defers the concept explicitly and argues against building one, because no command accepts a
collection argument and nothing would consult it. The pack's tables are already one namespace per
`[packs.graph] dsn`, so today one database **is** one corpus and a single row delivers the property
in full. When a collection concept ships, this row's key becomes the collection; until then,
inventing one would be state that looks consulted and is not, which is exactly what `03` refused.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from pydantic import SecretStr

from weft_cli.registry_bootstrap import Dependencies
from weft_cli.services import ServiceSelection
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced, SourceId
from weft_kernel.registry import Registry
from weft_kg.commands import (
    GraphActivateArgs,
    GraphActivateCommand,
    GraphProposeArgs,
    GraphProposeCommand,
    GraphProposeResult,
    GraphShowArgs,
    GraphShowCommand,
    GraphShowResult,
)
from weft_kg.payload import ExtractedFact
from weft_kg.schema import EmptyCorpusError, GraphSchema, MalformedSchemaFileError, RelationRule
from weft_kg.store import GraphSettings, GraphStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


def _unreachable_reason() -> str | None:
    try:
        conn = psycopg.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`."
    conn.close()
    return None


_UNREACHABLE = _unreachable_reason()
pytestmark = pytest.mark.skipif(_UNREACHABLE is not None, reason=_UNREACHABLE or "")

_SETTINGS = GraphSettings(dsn=SecretStr(_DSN))


def _ctx() -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(
        Dependencies, Dependencies(registry=Registry(), reports=(), services=ServiceSelection())
    )
    return ctx


def _fact_node(source: str, predicate: str, target: str, *, types: tuple[str, str]) -> Node:
    """A node carrying an `ExtractedFact`, the shape `llm-facts` writes and `propose` reads."""
    node = Node.synthetic(
        content=f"{source} {predicate} {target}",
        media_type=MediaType.TEXT,
        reason="weft_kg's own schema-command test",
        sources=frozenset({SourceId("doc-a")}),
    )
    return node.with_ext(
        ExtractedFact(
            source=source,
            source_type=types[0],
            predicate=predicate,
            target=target,
            target_type=types[1],
        )
    )


@pytest.fixture
async def store() -> AsyncIterator[GraphStore]:
    instance = GraphStore(_SETTINGS)
    await instance.count()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE kg_nodes, kg_sources, kg_entities CASCADE")
        await cur.execute("DELETE FROM kg_active_schema")
    await conn.close()
    yield instance
    # **Cleared on the way out as well as on the way in.** The setup `DELETE` is enough for the
    # suite — each test starts clean — and it is not enough for the *container*, which is shared
    # with a human running the binary against the same database. `kg_active_schema` holds
    # **configuration** rather than data (`S13` records that cost), so a row left behind is a
    # corpus claiming to be under a schema nobody activated. Measured: it leaked into a real
    # `weft graph show` run during this task.
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM kg_active_schema")
    await conn.close()
    await instance.aclose()


def _schema_file(directory: Path, *, name: str, predicate: str = "wrote") -> Path:
    path = directory / f"{name}.toml"
    path.write_text(
        "\n".join(
            [
                f'name = "{name}"',
                "",
                "[[relations]]",
                'source_type = "person"',
                f'predicate = "{predicate}"',
                'target_type = "method"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


async def _activate(directory: Path, path: Path) -> None:
    await GraphActivateCommand(_SETTINGS).run(GraphActivateArgs(path=str(path)), _ctx())
    del directory


async def test_propose_reads_the_corpus_and_prints_the_shape_it_produced(
    store: GraphStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The headline for this command: what an operator curates is a measurement of their own
    corpus, ranked by how often the corpus wrote it, not a model's opinion of what it should be.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    await store.add(
        [
            _fact_node("Chucri", "wrote", "adRAP", types=("person", "method")),
            _fact_node("Azouz", "wrote", "RAPTOR", types=("person", "method")),
            _fact_node("adRAP", "extends", "RAPTOR", types=("method", "method")),
        ]
    )

    # Act
    outcome = await GraphProposeCommand(_SETTINGS).run(GraphProposeArgs(min_count=1), _ctx())

    # Assert — `wrote` was written twice and `extends` once, so `wrote` leads.
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, GraphProposeResult)
    proposed = result.proposed
    assert [rule.predicate for rule in proposed.relations] == ["wrote", "extends"]


async def test_propose_persists_nothing(
    store: GraphStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`propose` prints and never persists — the task line's own words. A command that quietly
    activated what it proposed would make the operator's approval a formality, which is the whole
    point of the file existing.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    await store.add([_fact_node("Chucri", "wrote", "adRAP", types=("person", "method"))])

    # Act
    await GraphProposeCommand(_SETTINGS).run(GraphProposeArgs(min_count=1), _ctx())

    # Assert — nothing activated, and no weft.toml written.
    shown = await GraphShowCommand(_SETTINGS).run(GraphShowArgs(), _ctx())
    assert isinstance(shown, Produced)
    assert isinstance(shown.value, GraphShowResult)
    assert shown.value.active is None
    assert not (tmp_path / "weft.toml").exists()


async def test_propose_from_a_corpus_that_produced_no_facts_refuses(
    store: GraphStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Printing an empty schema would invite an operator to activate one that admits nothing and
    drops every fact in the corpus. Refused, naming what to run first.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    del store

    # Act / Assert
    with pytest.raises(EmptyCorpusError):
        await GraphProposeCommand(_SETTINGS).run(GraphProposeArgs(), _ctx())


async def test_activate_records_the_schema_in_the_project_file_and_in_the_corpus(
    store: GraphStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`S13`'s two halves, asserted together because either alone is the defect it settles: the
    file is what a pull request shows, the row is what the corpus is under.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    del store
    path = _schema_file(tmp_path, name="papers")

    # Act
    outcome = await GraphActivateCommand(_SETTINGS).run(GraphActivateArgs(path=str(path)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    written = (tmp_path / "weft.toml").read_text(encoding="utf-8")
    assert "[packs.graph]" in written
    assert "papers.toml" in written
    shown = await GraphShowCommand(_SETTINGS).run(GraphShowArgs(), _ctx())
    assert isinstance(shown, Produced)
    assert isinstance(shown.value, GraphShowResult)
    assert shown.value.active is not None
    assert shown.value.active.name == "papers"


async def test_the_corpus_answers_for_itself_not_the_operator_s_disk(
    store: GraphStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """**The property `S13` exists for.** A second checkout — a different directory, no
    `weft.toml`, no schema file — pointed at the same database must read the same answer. If the
    file were the only record, the two would hold contradictory beliefs about one corpus and
    nothing could notice.
    """
    # Arrange — activate from one directory.
    monkeypatch.chdir(tmp_path)
    del store
    await _activate(tmp_path, _schema_file(tmp_path, name="papers"))

    # Act — a second checkout, sharing only the database.
    elsewhere = tmp_path / "another-checkout"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    shown = await GraphShowCommand(_SETTINGS).run(GraphShowArgs(), _ctx())

    # Assert
    assert not (elsewhere / "weft.toml").exists()
    assert isinstance(shown, Produced)
    assert isinstance(shown.value, GraphShowResult)
    assert shown.value.active is not None
    assert shown.value.active.name == "papers"


async def test_activate_refuses_a_file_that_is_not_a_schema_by_name(
    store: GraphStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A curated file is hand-edited, so a malformed one is the ordinary case rather than the
    exotic one. Refused naming the file, and **nothing written** — a half-activation that
    recorded a name for a schema it could not read is the state nothing could diagnose.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    del store
    broken = tmp_path / "broken.toml"
    broken.write_text('name = "papers"\nrelations = "all of them"\n', encoding="utf-8")

    # Act / Assert
    with pytest.raises(MalformedSchemaFileError, match="broken.toml"):
        await GraphActivateCommand(_SETTINGS).run(GraphActivateArgs(path=str(broken)), _ctx())
    assert not (tmp_path / "weft.toml").exists()


async def test_show_prints_every_schema_the_corpus_holds_not_only_the_active_one(
    store: GraphStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """**The sentence this task exists for**: *a corpus holding two schemas is a fact
    `weft graph show` prints, never a silence.*

    A corpus indexed under one schema and re-indexed under another holds facts from both, and an
    operator reading only the active one would believe the graph is uniform when it is not. The
    facts carry their own schema identity (`ExtractedFact.schema_id`), so this is read from the
    corpus rather than from a history nobody kept.
    """
    # Arrange — facts extracted under two different schemas, plus one under none.
    monkeypatch.chdir(tmp_path)
    first = GraphSchema(
        name="papers",
        relations=(RelationRule(source_type="person", predicate="wrote", target_type="method"),),
    )
    second = GraphSchema(
        name="reports",
        relations=(RelationRule(source_type="person", predicate="cited", target_type="paper"),),
    )
    nodes = [
        _fact_node("Chucri", "wrote", "adRAP", types=("person", "method")),
        _fact_node("Azouz", "cited", "adRAP", types=("person", "paper")),
        _fact_node("Nobody", "mused", "aloud", types=("person", "thing")),
    ]
    tagged = [
        nodes[0].with_ext(_with_schema(nodes[0], first.identity)),
        nodes[1].with_ext(_with_schema(nodes[1], second.identity)),
        nodes[2],
    ]
    await store.add(tagged)
    await _activate(tmp_path, _schema_file(tmp_path, name="papers"))

    # Act
    shown = await GraphShowCommand(_SETTINGS).run(GraphShowArgs(), _ctx())

    # Assert — both identities are reported, and so is the untagged remainder.
    assert isinstance(shown, Produced)
    assert isinstance(shown.value, GraphShowResult)
    identities = {presence.identity for presence in shown.value.schemas_in_corpus}
    assert {first.identity, second.identity} <= identities
    assert sum(presence.facts for presence in shown.value.schemas_in_corpus) == 3


def _with_schema(node: Node, identity: str) -> ExtractedFact:
    """That node's fact, re-stated under `identity` — the shape `llm-facts` writes when a schema
    is active. Built from the node's own ext rather than repeated by hand, so a field added to
    `ExtractedFact` does not silently stop being carried here.
    """
    fact = node.ext_as(ExtractedFact)
    assert fact is not None
    return fact.model_copy(update={"schema_id": identity})


def test_each_command_declares_its_permission_class() -> None:
    """`03` → *Permissions*, G3's rule: a plugin-contributed command declares its class at
    registration and there is **no default** — `read` silently under-protects and `destroy`
    trains people to pass `--yes` reflexively.

    `activate` is `write` rather than `overwrite` on `weft config set`'s own precedent: it edits
    `weft.toml`, which is what that command does, and the 2026-08-20 repair moved exactly this
    kind of edit out of `overwrite`. `propose` and `show` read and print.
    """
    # Assert
    assert GraphProposeCommand.permission_class is PermissionClass.READ
    assert GraphShowCommand.permission_class is PermissionClass.READ
    assert GraphActivateCommand.permission_class is PermissionClass.WRITE
