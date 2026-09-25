"""The corpus-layer lifecycle soak, Phase 43e task **43.25**, run from an installed wheel.

One run drives the installed `weft` binary through a corpus `raptor` layer's whole lifecycle on
one backend — build, add and join, re-parse, delete, an interrupted build resumed, a join read
across its publish by a handle held open from before it, and `weft reconcile` in each mode — and
before and after every step reads the store directly: the generation catalogue, every source's
layer records and every node, by SQL on pgvector and by scroll on Qdrant (`L8.30`). A step passes
when its exit code, its operator line and every invariant over those reads hold.

Run it with the soak venv's own interpreter, from a directory outside this repository::

    $VENV/bin/python scripts/soak_layers.py --backend pgvector --weft $VENV/bin/weft --work DIR

Each run creates its own database (and, on Qdrant, names its own collections), and drops exactly
those names when it ends. It refuses to start while `pg_stat_activity` shows a session it did not
open, and re-checks before every step. Configuration makes no paid call: `scripted` for every LLM
role and `hash` for the embedder.

**The tree's second `asyncio.run`**, by the owner's answer at Phase 43e's opening: the reader held
across a publish is the configured store, opened through the wheel's registry exactly as an
embedding application opens it, and holding one needs an event loop. No shipped command holds a
handle across calls. `tests/architecture/test_ff7_colour_integrity.py` names this file in its
waiver.

The pure functions — the configuration a run writes, the snapshot model, every invariant and step
check, the line parsers and the read classifier — are pinned by `tests/unit/scripts/
test_soak_layers.py`. `main` drives real containers and the shipped binary, and is exercised by
running it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import signal
import sys
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Final, cast

import httpx
import psycopg
from psycopg import sql
from pydantic import BaseModel, ConfigDict

from weft_engine.registry_bootstrap import build_dependencies
from weft_kernel.seam import aclose
from weft_store import NodeStore
from weft_store.contract import Filter, FilterOp, MetadataFilter

LAYER: Final = "raptor-corpus"
RAPTOR: Final = "weft-index-raptor"
CHECKPOINT: Final = "weft-index-layer"
PG_URL: Final = "postgresql://weft:weft@localhost:5433"
QDRANT_URL: Final = "http://localhost:6333"
QUESTION: Final = "What was measured in Paris?"
STALE_LINE: Final = rf"layer '{LAYER}' is stale: a source it covered was deleted or re-parsed"
#: The companion collections a Qdrant store creates beside its own
#: (`weft_qdrant/store.py:427 "__sources"`, and the two after it).
QDRANT_SUFFIXES: Final = ("", "__sources", "__targets", "__generations")

_JOINED = re.compile(r"layer '([^']+)': joined (\d+) leaves, (\d+) unassigned")
_RECLAIMED = re.compile(r"reclaimed (\d+) node\(s\) from withdrawn generations")
TOPICS: Final = {
    "elements": ("polonium", "radium", "uranium", "thorium", "actinium", "radon", "francium"),
    "baking": ("sourdough", "baguette", "brioche", "croissant", "fougasse", "focaccia", "pretzel"),
}


class Backend(BaseModel):
    """One backend a run is pointed at, and the names it owns there."""

    model_config = ConfigDict(frozen=True)

    kind: str
    database: str

    @property
    def collections(self) -> tuple[str, ...]:
        """Every Qdrant collection this run's store may create, by exact name."""
        return (
            tuple(f"{self.database}{s}" for s in QDRANT_SUFFIXES) if self.kind == "qdrant" else ()
        )


class Generation(BaseModel):
    """A row of the generation catalogue."""

    model_config = ConfigDict(frozen=True)

    id: str
    layer: str
    status: str


class Source(BaseModel):
    """A source record and its layers' statuses, by layer name."""

    model_config = ConfigDict(frozen=True)

    id: str
    layers: dict[str, str]


class StoredNode(BaseModel):
    """What the soak reads of one stored node."""

    model_config = ConfigDict(frozen=True)

    id: str
    sources: frozenset[str]
    parents: tuple[str, ...]
    generations: frozenset[str]
    summary: bool
    checkpoint: bool


class Snapshot(BaseModel):
    """Everything one read of the store returned."""

    model_config = ConfigDict(frozen=True)

    generations: tuple[Generation, ...]
    sources: tuple[Source, ...]
    nodes: tuple[StoredNode, ...]

    def with_status(self, status: str) -> frozenset[str]:
        """The ids of every generation in `status`."""
        return frozenset(g.id for g in self.generations if g.status == status)

    def tree(self, generation: str) -> frozenset[str]:
        """The summaries `generation` holds."""
        return frozenset(n.id for n in self.nodes if n.summary and generation in n.generations)

    def published_tree(self) -> frozenset[str]:
        """The summaries of the one published generation, or none."""
        published = self.with_status("published")
        return frozenset[str]().union(*(self.tree(g) for g in published))

    def layer_statuses(self) -> dict[str, str]:
        """Each source's status for the soak's layer, `missing` where it has no record."""
        return {s.id: s.layers.get(LAYER, "missing") for s in self.sources}


class Outcome(BaseModel):
    """One invocation of the binary: its exit code and what it printed."""

    model_config = ConfigDict(frozen=True)

    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def text(self) -> str:
        """Stdout and stderr together, the way an operator reads them."""
        return f"{self.stdout}\n{self.stderr}"


def weft_toml(backend: Backend, *, otel: bool = False) -> str:
    """The `weft.toml` a run writes: its own database or collection, no paid call anywhere.

    Args:
        backend: Which store, and the database or collection name this run owns.
        otel: Print every span to stdout, so a test can count model calls.

    Returns:
        The file's text.
    """
    lines = [
        "[packs.store]",
        f'dsn = "{PG_URL}/{backend.database}"',
        "[llm.roles]",
        'index = { provider = "scripted", model = "scripted" }',
        'generate = { provider = "scripted", model = "scripted" }',
        "[services]",
        f'store = "{"qdrant" if backend.kind == "qdrant" else "pgvector"}"',
        'embed = "hash"',
    ]
    if backend.kind == "qdrant":
        lines += ["[packs.qdrant]", f'collection = "{backend.database}"', "vector_size = 64"]
    if otel:
        lines += ["[packs.otel]", 'exporter = "console"']
    return "\n".join(lines) + "\n"


def layer_document() -> str:
    """The project-local corpus layer: small clusters, and the shipped concurrency, never pinned.

    Through `vars:`, which the shipped document threads into both `raptor` and its `join`
    stage. The join is then typed wider, so an added leaf always has a cluster with room and a
    join replaces a summary rather than leaving every new leaf unassigned.
    """
    return (
        f"name: {LAYER}\nextends: enrich-with-raptor\nvars:\n  layer.scope: corpus\n"
        "  raptor.cluster_size: 5\n  raptor.similarity_threshold: -1.0\n"
        "replace:\n  - {id: join, use: adrap, with: {cluster_size: 50, "
        "similarity_threshold: -1.0}}\n"
    )


def document(topic: str, name: str, revision: int = 0) -> str:
    """One corpus document's text. `revision` changes its bytes, and so its chunk."""
    detail = f" Revised note {revision}." if revision else ""
    if topic == "elements":
        return f"Notes on {name}: its half-life and decay chain, measured in Paris.{detail}\n"
    return f"Notes on baking {name}: flour, hydration and proofing, in a Paris bakery.{detail}\n"


def corpus(scale: int) -> dict[str, str]:
    """`scale` copies of every topic's documents, by file name."""
    return {
        f"{name}-{copy}.md": document(topic, f"{name} {copy}")
        for copy in range(scale)
        for topic, names in TOPICS.items()
        for name in names
    }


def joined(text: str) -> tuple[int, int] | None:
    """`(joined, unassigned)` from a join's operator line, or `None` when it printed none."""
    match = _JOINED.search(text)
    return (int(match.group(2)), int(match.group(3))) if match else None


def reclaimed(text: str) -> int:
    """How many nodes a command said it reclaimed, summed over every line that says so."""
    return sum(int(m.group(1)) for m in _RECLAIMED.finditer(text))


def llm_spans(stdout: str, role: str = "index") -> int:
    """How many `llm:<role>` spans the console exporter printed."""
    decoder = json.JSONDecoder()
    names = [_span_name(decoder, stdout, m.start()) for m in re.finditer(r"(?m)^\{", stdout)]
    return names.count(f"llm:{role}")


def _span_name(decoder: json.JSONDecoder, text: str, start: int) -> str:
    try:
        span: object = decoder.raw_decode(text, start)[0]
    except json.JSONDecodeError:
        return ""
    return str(cast("dict[str, object]", span).get("name", "")) if isinstance(span, dict) else ""


def invariants(
    snap: Snapshot,
    *,
    spared: frozenset[str] = frozenset(),
    reclaims: bool = True,
    building_allowed: bool = False,
) -> list[str]:
    """What must hold after every command that exited 0.

    Args:
        snap: The store, read after the command.
        spared: Generations the command itself withdrew, whose nodes a closing pass keeps for a
            reader still holding them (`R43.47`).
        reclaims: Whether the command ran a repairing pass (`weft index`'s closing one, or
            `weft reconcile`), after which no older withdrawn generation's nodes remain.
        building_allowed: An interrupted build's generation is still open, for its resume.

    Returns:
        One sentence per violation.
    """
    withdrawn = snap.with_status("withdrawn") - spared if reclaims else frozenset[str]()
    return [
        *_catalogue_problems(snap, building_allowed=building_allowed),
        *_orphans(snap),
        *_survivors(snap, withdrawn),
        *_tree_is_whole(snap),
    ]


def _catalogue_problems(snap: Snapshot, *, building_allowed: bool) -> list[str]:
    """At most one published generation per layer, and none left open unless allowed."""
    problems: list[str] = []
    published = [g for g in snap.generations if g.status == "published"]
    if len({g.layer for g in published}) != len(published):
        problems.append(f"more than one published generation of a layer: {published}")
    if (building := snap.with_status("building")) and not building_allowed:
        problems.append(f"a generation left building: {sorted(building)}")
    return problems


def _orphans(snap: Snapshot) -> list[str]:
    """Every node whose sources include one no record holds any more."""
    recorded = {s.id for s in snap.sources}
    return [
        f"node {node.id[:12]} names sources no record holds: {sorted(node.sources - recorded)}"
        for node in snap.nodes
        if node.sources - recorded
    ]


def _survivors(snap: Snapshot, withdrawn: frozenset[str]) -> list[str]:
    """Every node held by nothing but generations in `withdrawn`."""
    return [
        f"node {node.id[:12]} survives only in withdrawn {sorted(node.generations)}"
        for node in snap.nodes
        if node.generations and "" not in node.generations and node.generations <= withdrawn
    ]


def _tree_is_whole(snap: Snapshot) -> list[str]:
    """Where every source's layer record is active, every published summary's parents exist."""
    statuses = set(snap.layer_statuses().values())
    if statuses != {"active"}:
        return []
    present = {n.id for n in snap.nodes}
    tree = snap.published_tree()
    return [
        f"published summary {n.id[:12]} under an active layer has a missing parent"
        for n in snap.nodes
        if n.id in tree and not set(n.parents) <= present
    ]


def check_join(before: Snapshot, after: Snapshot, outcome: Outcome) -> list[str]:
    """A join publishes one new tree that keeps every summary it did not replace.

    With `joined 0 leaves` nothing was replaced, so the new tree is the old one.
    """
    problems: list[str] = []
    counts = joined(outcome.text)
    if counts is None:
        return [f"no `joined N leaves, M unassigned` line in: {outcome.text.strip()[:300]}"]
    old, new = before.published_tree(), after.published_tree()
    if counts[0] == 0 and new != old:
        problems.append(
            f"joined 0 leaves, yet the published tree moved: {len(old)} -> {len(new)} summaries,"
            f" {len(old - new)} gone, {len(new - old)} new"
        )
    if set(after.layer_statuses().values()) != {"active"}:
        problems.append(f"layer not active on every source after a join: {after.layer_statuses()}")
    return problems


def check_rebuilt(before: Snapshot, after: Snapshot) -> list[str]:
    """A build or rebuild leaves one published tree, active on every source, and a new one."""
    problems: list[str] = []
    if set(after.layer_statuses().values()) != {"active"}:
        problems.append(f"layer not active on every source: {after.layer_statuses()}")
    if not after.published_tree():
        problems.append("no published tree")
    if after.with_status("published") == before.with_status("published"):
        problems.append("the published generation did not change")
    return problems


def check_stale(after: Snapshot, *, released: frozenset[str] = frozenset()) -> list[str]:
    """Every remaining source's record for the layer reads `stale`.

    A re-parsed source is `released`: its chunks changed, so its own record goes with them.
    """
    statuses = {s: v for s, v in after.layer_statuses().items() if s not in released}
    missing = [s for s in released if after.layer_statuses().get(s) not in (None, "missing")]
    problems = (
        [] if set(statuses.values()) == {"stale"} else [f"layer not stale everywhere: {statuses}"]
    )
    if after.published_tree():
        # A stale layer is hidden from every read until republished (43.30).
        problems.append(f"a stale layer still has {len(after.published_tree())} published nodes")
    return (
        problems + [f"a re-parsed source kept its layer record: {missing}"] if missing else problems
    )


def classify_reads(
    old: frozenset[str], new: frozenset[str], reads: Sequence[frozenset[str]]
) -> str:
    """Name each read by the tree it saw: `O` old, `N` new, `=` either, `?` neither, `x` none.

    A ranked read returns some of a tree's summaries, never necessarily all, so a read is
    placed by what only one tree holds: `?` is a summary of neither tree, or of both trees'
    unshared parts at once; `=` saw only what the two share and cannot say which it read.
    """
    return "".join(_placed(old, new, read) for read in reads)


def _placed(old: frozenset[str], new: frozenset[str], read: frozenset[str]) -> str:
    only_old, only_new = read & (old - new), read & (new - old)
    if not read:
        return "x"
    if not read <= old | new or (only_old and only_new):
        return "?"
    return "O" if only_old else "N" if only_new else "="


async def run_weft(weft: Path, argv: Sequence[str], cwd: Path) -> Outcome:
    """Run the installed binary once and capture everything it said."""
    process = await asyncio.create_subprocess_exec(
        str(weft), *argv, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await process.communicate()
    return Outcome(
        argv=tuple(argv),
        exit_code=process.returncode if process.returncode is not None else -1,
        stdout=out.decode(errors="replace"),
        stderr=err.decode(errors="replace"),
    )


async def foreign_sessions(own_database: str) -> list[str]:
    """Every Postgres session that is neither this soak's probe nor inside its own database."""
    async with await psycopg.AsyncConnection.connect(f"{PG_URL}/weft", autocommit=True) as conn:
        cursor = await conn.execute(
            "SELECT datname, application_name FROM pg_stat_activity"
            " WHERE datname IS NOT NULL AND pid <> pg_backend_pid() AND datname <> %s",
            (own_database,),
        )
        return [f"{row[0]} ({row[1] or 'no name'})" for row in await cursor.fetchall()]


async def admin(statement: sql.Composed) -> None:
    """Run one statement against the server's maintenance database."""
    async with await psycopg.AsyncConnection.connect(f"{PG_URL}/weft", autocommit=True) as conn:
        await conn.execute(statement)


#: One read of a pgvector database as a single JSON document, shaped as `Snapshot`, for a
#: database whose store has created its tables; `_PG_NO_GENERATIONS` before a layer ever ran.
_PG_SNAPSHOT: Final = """
SELECT json_build_object(
  'generations', (SELECT coalesce(json_agg(json_build_object(
      'id', id, 'layer', layer, 'status', status)), '[]'::json) FROM weft_generations),
  'sources', (SELECT coalesce(json_agg(json_build_object('id', s.id, 'layers', (
      SELECT coalesce(json_object_agg(r->>'name', r->>'status'), '{}'::json)
      FROM jsonb_array_elements(s.layers) r))), '[]'::json) FROM weft_sources s),
  'nodes', (SELECT coalesce(json_agg(json_build_object(
      'id', id, 'sources', sources, 'parents', parents, 'generations', generations,
      'summary', coalesce(ext->'weft-index-raptor' ? 'level', false),
      'checkpoint', coalesce(ext->'weft-index-layer' ? 'checkpoint', false))), '[]'::json)
    FROM weft_nodes))
"""
_PG_NO_GENERATIONS: Final = """
SELECT json_build_object(
  'generations', '[]'::json,
  'sources', (SELECT coalesce(json_agg(json_build_object('id', s.id, 'layers', (
      SELECT coalesce(json_object_agg(r->>'name', r->>'status'), '{}'::json)
      FROM jsonb_array_elements(s.layers) r))), '[]'::json) FROM weft_sources s),
  'nodes', (SELECT coalesce(json_agg(json_build_object(
      'id', id, 'sources', sources, 'parents', parents, 'generations', generations,
      'summary', coalesce(ext->'weft-index-raptor' ? 'level', false),
      'checkpoint', coalesce(ext->'weft-index-layer' ? 'checkpoint', false))), '[]'::json)
    FROM weft_nodes))
"""
_PG_TABLES: Final = (
    "SELECT to_regclass('weft_nodes') IS NOT NULL, to_regclass('weft_generations') IS NOT NULL"
)


async def pg_snapshot(database: str) -> Snapshot:
    """Read the catalogue, the sources and the nodes of one pgvector database."""
    async with await psycopg.AsyncConnection.connect(
        f"{PG_URL}/{database}", autocommit=True
    ) as conn:
        tables = await (await conn.execute(_PG_TABLES)).fetchone()
        if tables is None or not tables[0]:
            return Snapshot(generations=(), sources=(), nodes=())
        query = _PG_SNAPSHOT if tables[1] else _PG_NO_GENERATIONS
        row = await (await conn.execute(query)).fetchone()
    return Snapshot.model_validate(row[0] if row else {})


async def _scroll(client: httpx.AsyncClient, collection: str) -> list[dict[str, object]]:
    exists = await client.get(f"/collections/{collection}/exists")
    if not exists.json()["result"]["exists"]:
        return []
    payloads: list[dict[str, object]] = []
    offset: object = None
    while True:
        body: dict[str, object] = {"limit": 256, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        result = (await client.post(f"/collections/{collection}/points/scroll", json=body)).json()
        payloads += [p["payload"] for p in result["result"]["points"]]
        offset = result["result"].get("next_page_offset")
        if offset is None:
            return payloads


class _Lineage(BaseModel):
    sources: list[str] = []
    parents: list[str] = []


class _QdrantNode(BaseModel):
    """The part of a Qdrant node payload the soak reads."""

    id: str
    lineage: _Lineage = _Lineage()
    generations: list[str] = []
    ext: dict[str, dict[str, object]] = {}

    def stored(self) -> StoredNode:
        """The payload as the soak's own node row."""
        return StoredNode(
            id=self.id,
            sources=frozenset(self.lineage.sources),
            parents=tuple(self.lineage.parents),
            generations=frozenset(self.generations),
            summary="level" in self.ext.get(RAPTOR, {}),
            checkpoint="checkpoint" in self.ext.get(CHECKPOINT, {}),
        )


class _LayerRecord(BaseModel):
    name: str
    status: str


class _QdrantSource(BaseModel):
    id: str
    layers: list[_LayerRecord] = []


async def qdrant_snapshot(collection: str) -> Snapshot:
    """Read the catalogue, the sources and the nodes of one Qdrant store."""
    async with httpx.AsyncClient(base_url=QDRANT_URL, timeout=30) as client:
        generations = await _scroll(client, f"{collection}__generations")
        sources = await _scroll(client, f"{collection}__sources")
        nodes = await _scroll(client, collection)
    return Snapshot(
        generations=tuple(Generation.model_validate(g) for g in generations),
        sources=tuple(
            Source(id=q.id, layers={r.name: r.status for r in q.layers})
            for q in (_QdrantSource.model_validate(s) for s in sources)
        ),
        nodes=tuple(_QdrantNode.model_validate(n).stored() for n in nodes),
    )


async def snapshot(backend: Backend) -> Snapshot:
    """Read the backend this run owns."""
    if backend.kind == "qdrant":
        return await qdrant_snapshot(backend.database)
    return await pg_snapshot(backend.database)


class Soak:
    """One run against one backend: its project directory, its binary and what it found."""

    def __init__(self, backend: Backend, weft: Path, work: Path) -> None:
        self.backend = backend
        self.weft = weft
        self.project = work / backend.database
        self.violations: list[str] = []
        empty = Snapshot(generations=(), sources=(), nodes=())
        self.last: tuple[Snapshot, Snapshot] = (empty, empty)

    def write(self, name: str, text: str) -> Path:
        """Write one corpus file and return its path."""
        path = self.project / "corpus" / name
        path.write_text(text, encoding="utf-8")
        return path

    async def step(
        self,
        label: str,
        argv: Sequence[str],
        *,
        expect_exit: int = 0,
        reclaims: bool = True,
        building_allowed: bool = False,
        line: str | None = None,
    ) -> Outcome:
        """Run one command between two reads of the store, and check what always must hold.

        `line`, given, is a pattern the operator's output must contain.
        """
        await self.guard()
        before = await snapshot(self.backend)
        outcome = await run_weft(self.weft, argv, self.project)
        after = await snapshot(self.backend)
        spared = after.with_status("withdrawn") - before.with_status("withdrawn")
        found = (
            []
            if outcome.exit_code == expect_exit
            else [
                f"exit {outcome.exit_code}, expected {expect_exit}: {outcome.text.strip()[-400:]}"
            ]
        )
        if line is not None and not re.search(line, outcome.text):
            found.append(f"no line matching {line!r}")
        if expect_exit == 0:
            found += invariants(
                after, spared=spared, reclaims=reclaims, building_allowed=building_allowed
            )
        self.report(label, outcome, after, found)
        self.last = (before, after)
        return outcome

    def report(self, label: str, outcome: Outcome, after: Snapshot, found: Sequence[str]) -> None:
        """Print one step's verdict and keep its violations."""
        gens = ", ".join(f"{g.id}:{g.status}" for g in after.generations) or "none"
        tree, statuses = after.published_tree(), set(after.layer_statuses().values())
        print(f"--- {label}: `weft {' '.join(outcome.argv)}` exit={outcome.exit_code}")
        for line in (outcome.stdout + outcome.stderr).splitlines():
            if line.strip() and not line.startswith(("{", " ", "}")):
                print(f"    | {line}")
        print(
            f"    store: {len(after.sources)} sources {sorted(statuses)}, {len(after.nodes)} nodes,"
            f" published tree {len(tree)}, generations {gens}"
        )
        for problem in found:
            print(f"    VIOLATION {problem}")
        self.violations += [f"{label}: {p}" for p in found]

    def expect(self, label: str, problems: Sequence[str]) -> None:
        """Record a step-specific check's violations under the step's label."""
        for problem in problems:
            print(f"    VIOLATION {problem}")
        self.violations += [f"{label}: {p}" for p in problems]

    async def guard(self) -> None:
        """Refuse to go on while anything else uses the Postgres container."""
        if others := await foreign_sessions(self.backend.database):
            raise SystemExit(f"another session is using the container: {others}")


async def lifecycle(soak: Soak) -> None:
    """Build, join, re-parse, delete, each followed by the rebuild the step calls for."""
    index = ["index", "corpus", "--layers", LAYER]
    await soak.step("build", index, line=r"(\d+) documents: \1 indexed, 0 unchanged")
    soak.expect("build", check_rebuilt(*soak.last))

    soak.write("radon-extra.md", document("elements", "radon extra"))
    out = await soak.step("add and join", index)
    soak.expect("add and join", check_join(*soak.last, out))

    reparsed = soak.write("polonium-0.md", document("elements", "polonium 0", revision=1))
    await soak.step("re-parse", ["index", "corpus", "--layers", "none"], line=STALE_LINE)
    soak.expect(
        "re-parse", check_stale(soak.last[1], released=frozenset({str(reparsed.resolve())}))
    )
    await soak.step("rebuild after re-parse", index)
    soak.expect("rebuild after re-parse", check_rebuilt(*soak.last))

    # By a path relative to the project, as an operator types it (43.31).
    victim = soak.project / "corpus" / "radium-0.md"
    await soak.step(
        "delete", ["delete", "corpus/radium-0.md", "--yes"], reclaims=False, line=STALE_LINE
    )
    soak.expect("delete", check_stale(soak.last[1]))
    victim.unlink()
    await soak.step("rebuild after delete", index)
    soak.expect("rebuild after delete", check_rebuilt(*soak.last))

    # A file removed from disk is released by the next index of its directory (43.32).
    (soak.project / "corpus" / "thorium-1.md").unlink()
    await soak.step(
        "file gone from disk",
        ["index", "corpus", "--layers", "none"],
        line=r"released 1 source no longer on disk\.",
    )
    soak.expect("file gone from disk", check_stale(soak.last[1]))
    await soak.step("rebuild after a gone file", index)
    soak.expect("rebuild after a gone file", check_rebuilt(*soak.last))

    # The cheap full rebuild of an unchanged corpus layer (43.29).
    await soak.step("reprocess rebuild", [*index, "--layers-only", "--reprocess"])
    soak.expect("reprocess rebuild", check_rebuilt(*soak.last))


async def interrupted(soak: Soak) -> None:
    """Interrupt a rebuild once it has kept a summary, repair, then resume it.

    The published tree must survive the interrupt whole, `weft reconcile --mode repair` must
    leave the open generation and what it kept, and the resume must pay only for the rest.
    """
    soak.write("uranium-0.md", document("elements", "uranium 0", revision=2))
    await soak.step("re-parse before interrupt", ["index", "corpus", "--layers", "none"])
    published = soak.last[1].published_tree()
    (soak.project / "weft.toml").write_text(weft_toml(soak.backend, otel=True), encoding="utf-8")
    out, kept_ids = await _interrupt_a_build(soak)
    at_interrupt = soak.last[1]
    if at_interrupt.published_tree() != published:
        soak.expect("interrupt", ["the published tree changed under an interrupted build"])
    await soak.step(
        "repair between interrupt and resume",
        ["reconcile", "--mode", "repair", "--yes"],
        building_allowed=True,
    )
    if lost := kept_ids - {n.id for n in soak.last[1].nodes}:
        soak.expect("repair between interrupt and resume", [f"repair removed {len(lost)} kept"])
    resumed = await soak.step("resume", ["index", "corpus", "--layers", LAYER, "--layers-only"])
    tree = soak.last[1].published_tree()
    if missing := kept_ids - tree:
        soak.expect("resume", [f"{len(missing)} summaries kept before the interrupt were re-paid"])
    calls = llm_spans(out), llm_spans(resumed.stdout)
    print(f"    llm:index spans: interrupted {calls[0]}, resumed {calls[1]}, tree {len(tree)}")
    if calls[1] > len(tree) - len(kept_ids & tree):
        soak.expect("resume", [f"resumed paid {calls[1]} calls for {len(tree - kept_ids)} new"])
    (soak.project / "weft.toml").write_text(weft_toml(soak.backend), encoding="utf-8")


async def _interrupt_a_build(soak: Soak) -> tuple[str, frozenset[str]]:
    """SIGINT a layer build once it has kept a summary; its stdout and the summaries it kept."""
    process = await asyncio.create_subprocess_exec(
        str(soak.weft),
        "index",
        "corpus",
        "--layers",
        LAYER,
        "--layers-only",
        cwd=soak.project,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    kept = await _await_checkpoint(soak.backend, process)
    if process.returncode is None:
        process.send_signal(signal.SIGINT)
    out, _ = await process.communicate()
    after = await snapshot(soak.backend)
    soak.last = (soak.last[1], after)
    building = after.with_status("building")
    kept_ids = frozenset(n.id for n in after.nodes if n.checkpoint and n.generations & building)
    print(f"--- interrupt: exit={process.returncode}; kept {kept}, then {len(kept_ids)}")
    if process.returncode != 130:
        soak.expect("interrupt", [f"exit {process.returncode} after SIGINT, expected 130"])
    if len(building) != 1 or not kept_ids:
        soak.expect(
            "interrupt",
            [f"expected one open generation holding kept summaries: {sorted(building)}"],
        )
    return out.decode(errors="replace"), kept_ids


async def second_writer(soak: Soak) -> None:
    """A delete issued while a build holds the store is refused by name, and changes nothing."""
    soak.write("thorium-0.md", document("elements", "thorium 0", revision=3))
    await soak.step("re-parse before a second writer", ["index", "corpus", "--layers", "none"])
    victim = (soak.project / "corpus" / "actinium-0.md").resolve()
    build = await asyncio.create_subprocess_exec(
        str(soak.weft),
        "index",
        "corpus",
        "--layers",
        LAYER,
        "--layers-only",
        cwd=soak.project,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    before = await snapshot(soak.backend)
    await _await_building(soak.backend, build)
    refused = await run_weft(soak.weft, ["delete", str(victim), "--yes"], soak.project)
    raced = build.returncode is not None
    await build.communicate()
    after = await snapshot(soak.backend)
    print(f"--- second writer: exit={refused.exit_code}; the build had finished first: {raced}")
    for line in refused.text.strip().splitlines():
        print(f"    | {line}")
    problems = [] if raced else _refusal_problems(refused, after, str(victim))
    problems += [] if build.returncode == 0 else [f"the build exited {build.returncode}"]
    spared = after.with_status("withdrawn") - before.with_status("withdrawn")
    soak.expect("second writer", problems + invariants(after, spared=spared))


def _refusal_problems(refused: Outcome, after: Snapshot, victim: str) -> list[str]:
    problems = [] if refused.exit_code != 0 else ["a delete during a build exited 0"]
    if "another writer holds this store" not in refused.text:
        problems.append(f"the refusal names no writer: {refused.text.strip()[:200]}")
    if victim not in {s.id for s in after.sources}:
        problems.append("the refused delete removed its source anyway")
    return problems


async def _await_building(backend: Backend, process: asyncio.subprocess.Process) -> None:
    """Poll until a generation is open, or the process ends."""
    deadline = time.monotonic() + 120
    while process.returncode is None and time.monotonic() < deadline:
        if (await snapshot(backend)).with_status("building"):
            return
        await asyncio.sleep(0.02)


async def _await_checkpoint(backend: Backend, process: asyncio.subprocess.Process) -> int:
    """Poll until the build has kept one summary, or it ends; return how many it had kept."""
    deadline = time.monotonic() + 120
    while process.returncode is None and time.monotonic() < deadline:
        snap = await snapshot(backend)
        building = snap.with_status("building")
        kept = sum(1 for n in snap.nodes if n.checkpoint and n.generations & building)
        if kept:
            return kept
        await asyncio.sleep(0.02)
    return 0


async def read_across(
    soak: Soak, label: str, writes: dict[str, str], *, reparse: bool = False
) -> None:
    """Publish a new tree while a held handle and fresh `weft ask` runs keep reading.

    `writes` are the corpus files changed first: new ones make the publish a join; with
    `reparse`, changed ones are re-parsed first, which stales the layer and makes it a
    rebuild. The held handle is the configured store, opened through the wheel's registry the
    way an embedding application opens it, and closed through the seam when the step ends.
    """
    for name, text in writes.items():
        soak.write(name, text)
    if reparse:
        await soak.step(f"re-parse before {label}", ["index", "corpus", "--layers", "none"])
    deps = build_dependencies(soak.project / "weft.toml")
    entry = deps.registry.entry(NodeStore, deps.services.store)
    store = cast(MetadataFilter, entry.factory(None))
    try:
        await _read_while_publishing(soak, store, label)
    finally:
        await aclose(
            store, distribution=entry.distribution, contract="NodeStore", plugin=deps.services.store
        )


async def _read_while_publishing(soak: Soak, store: MetadataFilter, label: str) -> None:
    summaries = Filter(op=FilterOp.EXISTS, field=f"ext.{RAPTOR}.level")

    async def held_read() -> frozenset[str]:
        page = await store.matching(summaries)
        ids = {str(n.id) for n in page.items}
        while page.next_cursor is not None:
            page = await store.matching(summaries, page.next_cursor)
            ids |= {str(n.id) for n in page.items}
        return frozenset(ids)

    old = await held_read()
    build = asyncio.create_task(soak.step(label, ["index", "corpus", "--layers", LAYER]))
    held: list[frozenset[str]] = []
    fresh: list[frozenset[str]] = []
    while not build.done():
        held.append(await held_read())
        fresh.append(await _fresh_read(soak))
    held += [await held_read() for _ in range(3)]
    fresh += [await _fresh_read(soak) for _ in range(2)]
    await build
    new = soak.last[1].published_tree()
    held_seen, fresh_seen = classify_reads(old, new, held), classify_reads(old, new, fresh)
    print(f"    trees: old {len(old)}, new {len(new)}, {len(old - new)} replaced")
    print(f"    held handle: {held_seen}; fresh asks: {fresh_seen}")
    problems = [] if old != new else ["the publish left the tree unchanged, so no read informs"]
    # A stale layer is hidden (43.30): across a rebuild the old tree is already gone, so a read
    # before the publish legitimately sees none, and the new tree is the only one ever seen.
    hidden: set[str] = {"x"} if not old else set()
    problems += [f"held handle read {r}" for r in sorted(set(held_seen) - {"O", "="} - hidden)]
    problems += [
        f"a fresh ask read {r}" for r in sorted(set(fresh_seen) - {"O", "N", "="} - hidden)
    ]
    if "O" in fresh_seen[-2:]:
        problems.append("a fresh ask after the publish read the old tree")
    soak.expect(label, problems)


async def _fresh_read(soak: Soak) -> frozenset[str]:
    out = await run_weft(
        soak.weft,
        ["ask", "--retrieve-only", "--format", "json", "--top-k", "1000", QUESTION],
        soak.project,
    )
    ids = frozenset(re.findall(r'"node_id"\s*:\s*"([^"]+)"', out.stdout))
    snap = await snapshot(soak.backend)
    return ids & {n.id for n in snap.nodes if n.summary}


async def reconciled(soak: Soak) -> None:
    """`--dry-run` changes nothing; `repair` and `full` each leave every invariant holding."""
    await soak.step(
        "reconcile --dry-run",
        ["reconcile", "--dry-run", "--yes"],
        reclaims=False,
        line=r"mode 'full' would run against 1 participant",
    )
    before, after = soak.last
    if before != after:
        soak.expect("reconcile --dry-run", ["the store changed under --dry-run"])
    await soak.step(
        "reconcile repair", ["reconcile", "--mode", "repair", "--yes"], line=r"mode 'repair' — 1"
    )
    await soak.step(
        "reconcile full", ["reconcile", "--mode", "full", "--yes"], line=r"mode 'full' — 1"
    )


async def setup(backend: Backend, soak: Soak, scale: int) -> None:
    """Create this run's database, project directory, configuration and corpus."""
    await admin(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(backend.database)))
    (soak.project / "corpus").mkdir(parents=True)
    (soak.project / "pipelines").mkdir()
    (soak.project / "weft.toml").write_text(weft_toml(backend), encoding="utf-8")
    (soak.project / "pipelines" / f"{LAYER}.yaml").write_text(layer_document(), encoding="utf-8")
    for name, text in corpus(scale).items():
        soak.write(name, text)


async def teardown(backend: Backend) -> list[str]:
    """Drop exactly the names this run created, and report anything of its own left behind."""
    await admin(
        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(backend.database))
    )
    async with httpx.AsyncClient(base_url=QDRANT_URL, timeout=30) as client:
        for name in backend.collections:
            await client.delete(f"/collections/{name}")
        listed = (await client.get("/collections")).json()["result"]["collections"]
    left = [c["name"] for c in listed if c["name"].startswith(backend.database)]
    return [f"collections left behind: {left}"] if left else []


async def soak_one(kind: str, weft: Path, work: Path, scale: int) -> list[str]:
    """Run the whole lifecycle on one backend and return every violation found."""
    backend = Backend(kind=kind, database=f"weft_soak_{kind}_{uuid.uuid4().hex[:8]}")
    soak = Soak(backend, weft, work)
    await soak.guard()
    await setup(backend, soak, scale)
    try:
        await _drive(soak)
    finally:
        soak.violations += await teardown(backend)
    return soak.violations


async def _drive(soak: Soak) -> None:
    await lifecycle(soak)
    await interrupted(soak)
    await second_writer(soak)
    await read_across(
        soak,
        "join read across",
        {n: document("elements", n) for n in ("thorium-extra.md", "radon-extra-2.md")},
    )
    await read_across(
        soak,
        "rebuild read across",
        {"sourdough-0.md": document("baking", "sourdough 0", 4)},
        reparse=True,
    )
    await reconciled(soak)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the arguments, run the soak and print its verdict."""
    parser = argparse.ArgumentParser(description="The corpus-layer lifecycle soak (task 43.25).")
    parser.add_argument("--backend", choices=("pgvector", "qdrant"), required=True)
    parser.add_argument("--weft", type=Path, required=True, help="the installed binary")
    parser.add_argument("--work", type=Path, required=True, help="a directory outside the repo")
    parser.add_argument("--scale", type=int, default=24, help="copies of each document")
    args = parser.parse_args(argv)
    violations = asyncio.run(soak_one(args.backend, args.weft, args.work, args.scale))
    print(f"=== {args.backend}: {len(violations)} violation(s)")
    for violation in violations:
        print(f"  {violation}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
