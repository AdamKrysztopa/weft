"""The other three shipped layer shapes, and all four stacked — task **43.41**.

`scripts/soak_layers.py` drives `raptor-corpus`, a corpus-scoped RAPTOR summary layer, on one
backend; this sibling drives the other shapes it never touches — a source-scoped RAPTOR layer, the
shipped `enrich-with-questions`, a `facts-and-graph` layer over `weft_kg`, and all four stacked on
one project — reusing `soak_layers`' backend setup, teardown and command runner rather than a
second copy of them. Imported from `scripts/soak_layers.py:main`, never run on its own: `--shape`
there is the one entry point, and `tests/architecture/test_ff7_colour_integrity.py`'s harness
waiver names only `soak_layers.py`, so nothing here calls `asyncio.run`.

The pure functions — the configuration and documents a run writes, the participant counts and the
per-layer checks — are pinned by `tests/unit/scripts/test_soak_shapes.py`. `soak_shape` drives real
containers and the shipped binary, and is exercised by running it.
"""

from __future__ import annotations

import asyncio
import json
import re
import signal
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

import soak_layers
from psycopg import sql
from soak_layers import Backend, Snapshot


class Shape(StrEnum):
    """One of the three shapes 43f adds, plus every shape stacked on one project."""

    RAPTOR_SOURCE = "raptor-source"
    QUESTIONS = "questions"
    FACTS = "facts-and-graph"
    STACKED = "stacked"


_SHAPE_LAYERS: Final[dict[Shape, tuple[str, ...]]] = {
    Shape.RAPTOR_SOURCE: ("raptor-source",),
    Shape.QUESTIONS: ("enrich-with-questions",),
    Shape.FACTS: ("facts-scripted",),
    Shape.STACKED: ("raptor-corpus", "raptor-source", "enrich-with-questions", "facts-scripted"),
}


def shape_layers(shape: Shape) -> tuple[str, ...]:
    """The layer names `--layers` passes for this shape's run."""
    return _SHAPE_LAYERS[shape]


def uses_graph_base(shape: Shape) -> bool:
    """Whether this shape's base pipeline writes through the graph store too."""
    return shape in (Shape.FACTS, Shape.STACKED)


_FACTS_REPLY: Final = json.dumps(
    {
        "facts": [
            {
                "source": "pump",
                "source_type": "organisation",
                "predicate": "moves",
                "target": "water",
                "target_type": "organisation",
            },
            {
                "source": "water",
                "source_type": "organisation",
                "predicate": "flows into",
                "target": "tank",
                "target_type": "organisation",
            },
        ]
    }
)


def shape_toml(backend: Backend, shape: Shape) -> str:
    """`soak_layers.weft_toml`'s configuration, plus a graph shape's own store and `facts` role."""
    text = soak_layers.weft_toml(backend)
    if not uses_graph_base(shape):
        return text
    lines = [
        "[packs.graph]",
        f'dsn = "{soak_layers.PG_URL}/{backend.database}"',
        "[llm.roles.facts]",
        'provider = "scripted"',
        'model = "scripted"',
        "[llm.roles.facts.settings]",
        f"reply = '{_FACTS_REPLY}'",
    ]
    return text + "\n".join(lines) + "\n"


#: Source-scoped: no `layer.scope`, unlike `soak_layers.layer_document`'s corpus-scoped sibling.
#: Typed, not `auto` — measured at 43f's opening: `auto` finds no threshold under `hash` on half
#: the sources.
_RAPTOR_SOURCE_DOCUMENT: Final = (
    "name: raptor-source\nextends: enrich-with-raptor\nvars:\n"
    "  raptor.cluster_size: 5\n  raptor.similarity_threshold: -1.0\n"
)
#: Its own `facts` role, never `index` — measured at 43f's opening: the scripted echo `index`
#: uses degrades every fact, so a shared role built none.
_FACTS_DOCUMENT: Final = (
    "name: facts-scripted\nextends: enrich-with-facts-and-graph\n"
    "set:\n  - {id: facts, with: {role: facts}}\n"
)
_INDEX_QDRANT_GRAPH_DOCUMENT: Final = (
    "name: index-qdrant-graph\nextends: index-with-graph\nreplace:\n  - {id: store, use: qdrant}\n"
)


def shape_documents(backend: Backend, shape: Shape) -> dict[str, str]:
    """File name to YAML for `pipelines/`, only the documents this shape's run actually uses."""
    documents: dict[str, str] = {}
    if shape in (Shape.RAPTOR_SOURCE, Shape.STACKED):
        documents["raptor-source.yaml"] = _RAPTOR_SOURCE_DOCUMENT
    if shape is Shape.STACKED:
        documents["raptor-corpus.yaml"] = soak_layers.layer_document()
    if shape in (Shape.FACTS, Shape.STACKED):
        documents["facts-scripted.yaml"] = _FACTS_DOCUMENT
    if backend.kind == "qdrant" and uses_graph_base(shape):
        documents["index-qdrant-graph.yaml"] = _INDEX_QDRANT_GRAPH_DOCUMENT
    return documents


def base_argv(backend: Backend, shape: Shape) -> tuple[str, ...]:
    """`--pipeline <graph base>`, on the backend's own store, for a graph shape; `()` otherwise."""
    if not uses_graph_base(shape):
        return ()
    pipeline = "index-qdrant-graph" if backend.kind == "qdrant" else "index-with-graph"
    return ("--pipeline", pipeline)


def expected_participants(backend: Backend, shape: Shape) -> int:
    """How many `NodeStore` participants this shape's project names — measured at 43f's opening.

    A pgvector graph base names two: its own store and the graph's. A Qdrant graph base names
    three: `qdrant`, the graph's own store, and `pgvector` — the ancestor `index-with-graph`
    `index-qdrant-graph` derives from still names it, and a name any of the project's own
    documents or their ancestors name counts (`weft_cli.participation.stores_in_use`).
    """
    if not uses_graph_base(shape):
        return 1
    return 3 if backend.kind == "qdrant" else 2


_WORDS: Final = (
    "radium",
    "polonium",
    "thorium",
    "uranium",
    "actinium",
    "radon",
    "francium",
    "Paris",
    "Warsaw",
    "laboratory",
    "decay",
    "isotope",
    "chain",
    "spectrum",
    "sample",
    "crucible",
    "electrometer",
    "pitchblende",
    "ore",
    "salt",
)


def _sentence(name: str, index: int, revision: int, i: int) -> str:
    first, second, third = (
        _WORDS[(i * 7 + index) % 20],
        _WORDS[(i * 3 + len(name)) % 20],
        _WORDS[(i * i + revision) % 20],
    )
    return (
        f"{name.capitalize()} {index}.{i} (revision {revision}) records {first} beside {second}"
        f" and {third} at step {i * 13 + index}."
    )


def long_document(name: str, index: int, revision: int = 0) -> str:
    """Several chunks' worth of sentences that never repeat within a document.

    Over 3 x 512 characters, so a per-source tree has more than one leaf to build from; varied by
    `name` and `index` so two documents never collide, and by `revision` so a re-parse changes
    every sentence's bytes without changing how many there are.
    """
    sentences = (_sentence(name, index, revision, i) for i in range(40))
    return " ".join(sentences) + "\n"


def layer_nodes(snap: Snapshot, layer: str) -> frozenset[str]:
    """The ids of every node `layer` stamped."""
    return frozenset(n.id for n in snap.nodes if n.layer == layer)


def check_built(snap: Snapshot, layers: Sequence[str]) -> list[str]:
    """Each of `layers` is active on every source recorded, and has built at least one node."""
    problems: list[str] = []
    for layer in layers:
        statuses = {s.id: s.layers.get(layer, "missing") for s in snap.sources}
        if statuses and set(statuses.values()) != {"active"}:
            problems.append(f"layer '{layer}' not active on every source: {statuses}")
        if not layer_nodes(snap, layer):
            problems.append(f"layer '{layer}' built no node")
    return problems


def check_reparsed(before: Snapshot, after: Snapshot, layer: str, *, reparsed: str) -> list[str]:
    """The re-parsed source's record for `layer` is gone; every other source's nodes unchanged."""
    problems: list[str] = []
    status = next((s.layers.get(layer) for s in after.sources if s.id == reparsed), None)
    if status is not None:
        problems.append(f"re-parsed source '{reparsed}' kept its record for layer '{layer}'")
    before_others = {n.id for n in before.nodes if n.layer == layer and reparsed not in n.sources}
    after_others = {n.id for n in after.nodes if n.layer == layer and reparsed not in n.sources}
    if before_others != after_others:
        problems.append(
            f"layer '{layer}' nodes of sources other than '{reparsed}' changed:"
            f" {sorted(before_others)} -> {sorted(after_others)}"
        )
    return problems


def check_released(snap: Snapshot, source: str) -> list[str]:
    """No node still names `source` after it was released."""
    return [
        f"node {node.id} still names '{source}' after it was released"
        for node in snap.nodes
        if source in node.sources
    ]


def indexing_sources(snap: Snapshot, layer: str) -> frozenset[str]:
    """Every source whose record for `layer` reads `indexing` — what an interrupt awaits."""
    return frozenset(s.id for s in snap.sources if s.layers.get(layer) == "indexing")


@dataclass(frozen=True, slots=True)
class _Run:
    """One shape's own layer names and base pipeline, threaded through every step."""

    soak: soak_layers.Soak
    shape: Shape
    base: tuple[str, ...]
    per_source: tuple[str, ...]
    corpus_layer: str | None

    @property
    def layers(self) -> tuple[str, ...]:
        """Every layer this run's `--layers` names."""
        return shape_layers(self.shape)


@dataclass(frozen=True, slots=True)
class _Read:
    """One command's outcome, and the primary and graph reads taken around it."""

    outcome: soak_layers.Outcome
    before: Snapshot
    before_graph: Snapshot | None
    after: Snapshot
    after_graph: Snapshot | None


def _notes(run: _Run) -> list[int]:
    """The index of every `note-<i>.md` the run's corpus still holds."""
    return sorted(
        int(path.stem.removeprefix("note-"))
        for path in (run.soak.project / "corpus").glob("note-[0-9]*.md")
    )


def _per_source_layers(shape: Shape) -> tuple[str, ...]:
    """This shape's layers other than the corpus one — each with its own per-source checks."""
    return tuple(layer for layer in shape_layers(shape) if layer != soak_layers.LAYER)


def _corpus_layer(shape: Shape) -> str | None:
    """`raptor-corpus`, for the shape that stacks it; `None` for every other shape."""
    return soak_layers.LAYER if soak_layers.LAYER in shape_layers(shape) else None


async def _snapshots(run: _Run) -> tuple[Snapshot, Snapshot | None]:
    """The primary read, and — for a graph shape — the graph store's own `kg_*` read."""
    primary = await soak_layers.snapshot(run.soak.backend)
    if not uses_graph_base(run.shape):
        return primary, None
    graph = await soak_layers.pg_snapshot(run.soak.backend.database, table="kg")
    return primary, graph


def _orphan_problems(primary: Snapshot, graph: Snapshot | None) -> list[str]:
    problems = [f"primary: {p}" for p in soak_layers.orphans(primary)]
    if graph is not None:
        problems += [f"graph: {p}" for p in soak_layers.orphans(graph)]
    return problems


def _layer_problems(
    layers: Sequence[str], after: Snapshot, after_graph: Snapshot | None
) -> list[str]:
    problems = check_built(after, layers)
    if after_graph is not None:
        problems += [f"graph: {p}" for p in check_built(after_graph, layers)]
    return problems


def _exit_problems(outcome: soak_layers.Outcome, expect_exit: int, line: str | None) -> list[str]:
    found = (
        []
        if outcome.exit_code == expect_exit
        else [f"exit {outcome.exit_code}, expected {expect_exit}: {outcome.text.strip()[-400:]}"]
    )
    if line is not None and not re.search(line, outcome.text):
        found.append(f"no line matching {line!r}")
    return found


async def _command(
    run: _Run, label: str, argv: Sequence[str], *, expect_exit: int = 0, line: str | None = None
) -> _Read:
    """Run one command between two reads of the primary and (for a graph shape) the graph store."""
    before, before_graph = await _snapshots(run)
    outcome = await soak_layers.run_weft(run.soak.weft, argv, run.soak.project)
    after, after_graph = await _snapshots(run)
    found = _exit_problems(outcome, expect_exit, line)
    if expect_exit == 0:
        found += _orphan_problems(after, after_graph)
        if run.corpus_layer is not None:
            spared = after.with_status("withdrawn") - before.with_status("withdrawn")
            found += soak_layers.invariants(after, spared=spared)
    run.soak.report(label, outcome, after, found)
    return _Read(
        outcome=outcome,
        before=before,
        before_graph=before_graph,
        after=after,
        after_graph=after_graph,
    )


async def _build(run: _Run) -> None:
    argv = ["index", "corpus", *run.base, "--layers", ",".join(run.layers)]
    read = await _command(run, "build", argv, line=r"\d+ documents:")
    run.soak.expect("build", _layer_problems(run.per_source, read.after, read.after_graph))
    if run.corpus_layer is not None:
        run.soak.expect("build", soak_layers.check_rebuilt(read.before, read.after))


async def _add(run: _Run) -> None:
    before, _ = await _snapshots(run)
    run.soak.write("note-added.md", long_document("added", 0))
    argv = ["index", "corpus", *run.base, "--layers", ",".join(run.layers)]
    read = await _command(run, "add", argv)
    run.soak.expect("add", _layer_problems(run.per_source, read.after, read.after_graph))
    run.soak.expect("add", _unaffected_problems(run.per_source, before, read.after))
    if run.corpus_layer is not None:
        run.soak.expect("add", soak_layers.check_join(read.before, read.after, read.outcome))


def _unaffected_problems(layers: Sequence[str], before: Snapshot, after: Snapshot) -> list[str]:
    problems: list[str] = []
    for layer in layers:
        missing = layer_nodes(before, layer) - layer_nodes(after, layer)
        if missing:
            problems.append(
                f"layer '{layer}' lost node(s) an unrelated add should not touch: {sorted(missing)}"
            )
    return problems


async def _reparse_and_rebuild(run: _Run) -> None:
    target = run.soak.project / "corpus" / "note-0.md"
    reparsed = str(target.resolve())
    run.soak.write("note-0.md", long_document("note", 0, revision=1))
    read = await _command(run, "re-parse", ["index", "corpus", *run.base, "--layers", "none"])
    for layer in run.per_source:
        run.soak.expect(
            "re-parse", check_reparsed(read.before, read.after, layer, reparsed=reparsed)
        )
    if run.corpus_layer is not None:
        run.soak.expect(
            "re-parse", soak_layers.check_stale(read.after, released=frozenset({reparsed}))
        )
    argv = ["index", "corpus", *run.base, "--layers", ",".join(run.layers)]
    rebuild = await _command(run, "rebuild after re-parse", argv)
    run.soak.expect(
        "rebuild after re-parse",
        _layer_problems(run.per_source, rebuild.after, rebuild.after_graph),
    )
    if run.corpus_layer is not None:
        run.soak.expect(
            "rebuild after re-parse", soak_layers.check_rebuilt(rebuild.before, rebuild.after)
        )


async def _delete(run: _Run) -> None:
    victim = str((run.soak.project / "corpus" / "note-1.md").resolve())
    read = await _command(run, "delete", ["delete", "corpus/note-1.md", "--yes"])
    run.soak.expect("delete", check_released(read.after, victim))
    if read.after_graph is not None:
        run.soak.expect("delete", [f"graph: {p}" for p in check_released(read.after_graph, victim)])
    if run.corpus_layer is not None:
        run.soak.expect("delete", soak_layers.check_stale(read.after))
    (run.soak.project / "corpus" / "note-1.md").unlink()


async def _gone_from_disk(run: _Run) -> None:
    target = run.soak.project / "corpus" / "note-2.md"
    victim = str(target.resolve())
    target.unlink()
    read = await _command(
        run,
        "file gone from disk",
        ["index", "corpus", *run.base, "--layers", "none"],
        line=r"released 1 source no longer on disk\.",
    )
    run.soak.expect("file gone from disk", check_released(read.after, victim))
    if read.after_graph is not None:
        run.soak.expect(
            "file gone from disk", [f"graph: {p}" for p in check_released(read.after_graph, victim)]
        )


async def _await_indexing(run: _Run, layer: str, process: asyncio.subprocess.Process) -> None:
    """Poll until `layer` shows a source `indexing`, or the process ends."""
    deadline = time.monotonic() + 120
    while process.returncode is None and time.monotonic() < deadline:
        snap = await soak_layers.snapshot(run.soak.backend)
        if indexing_sources(snap, layer):
            return
        await asyncio.sleep(0.02)


async def _interrupt_and_resume(run: _Run) -> None:
    layer = run.per_source[0]
    for index in _notes(run):
        run.soak.write(f"note-{index}.md", long_document("note", index, revision=2))
    await _command(
        run, "re-parse before interrupt", ["index", "corpus", *run.base, "--layers", "none"]
    )
    process = await asyncio.create_subprocess_exec(
        str(run.soak.weft),
        "index",
        "corpus",
        *run.base,
        "--layers",
        layer,
        "--layers-only",
        cwd=run.soak.project,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await _await_indexing(run, layer, process)
    if process.returncode is not None:
        run.soak.expect("interrupt", ["the build finished before it could be interrupted"])
    else:
        process.send_signal(signal.SIGINT)
    await process.communicate()
    if process.returncode != 130:
        run.soak.expect("interrupt", [f"exit {process.returncode} after SIGINT, expected 130"])
    resume = await _command(
        run, "resume", ["index", "corpus", *run.base, "--layers", layer, "--layers-only"]
    )
    run.soak.expect("resume", _layer_problems((layer,), resume.after, resume.after_graph))


def _refusal_problems(refused: soak_layers.Outcome, after: Snapshot, victim: str) -> list[str]:
    problems = [] if refused.exit_code != 0 else ["a delete during a build exited 0"]
    if "another writer holds this store" not in refused.text:
        problems.append(f"the refusal names no writer: {refused.text.strip()[:200]}")
    if victim not in {s.id for s in after.sources}:
        problems.append("the refused delete removed its source anyway")
    return problems


async def _second_writer(run: _Run) -> None:
    layer = run.per_source[0]
    # Every source re-parsed, so the build outlasts the poll; one source finishes in ~0.1 s.
    for index in _notes(run):
        run.soak.write(f"note-{index}.md", long_document("note", index, revision=3))
    await _command(
        run,
        "re-parse before a second writer",
        ["index", "corpus", *run.base, "--layers", "none"],
    )
    victim = str((run.soak.project / "corpus" / "note-4.md").resolve())
    build = await asyncio.create_subprocess_exec(
        str(run.soak.weft),
        "index",
        "corpus",
        *run.base,
        "--layers",
        layer,
        "--layers-only",
        cwd=run.soak.project,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await _await_indexing(run, layer, build)
    refused = await soak_layers.run_weft(
        run.soak.weft, ["delete", victim, "--yes"], run.soak.project
    )
    raced = build.returncode is not None
    await build.communicate()
    after, _ = await _snapshots(run)
    problems = (
        ["the build finished before the delete could race it, so nothing was checked"]
        if raced
        else _refusal_problems(refused, after, victim)
    )
    run.soak.expect("second writer", problems)


async def _reconciled(run: _Run) -> None:
    n = expected_participants(run.soak.backend, run.shape)
    await _command(
        run,
        "reconcile --dry-run",
        ["reconcile", "--dry-run", "--yes"],
        line=rf"mode 'full' would run against {n} participant",
    )
    await _command(
        run,
        "reconcile repair",
        ["reconcile", "--mode", "repair", "--yes"],
        line=rf"mode 'repair' — {n}",
    )
    await _command(
        run,
        "reconcile full",
        ["reconcile", "--mode", "full", "--yes"],
        line=rf"mode 'full' — {n}",
    )


async def _setup(backend: Backend, soak: soak_layers.Soak, shape: Shape, scale: int) -> None:
    await soak_layers.admin(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(backend.database)))
    (soak.project / "corpus").mkdir(parents=True)
    (soak.project / "pipelines").mkdir()
    (soak.project / "weft.toml").write_text(shape_toml(backend, shape), encoding="utf-8")
    for name, text in shape_documents(backend, shape).items():
        (soak.project / "pipelines" / name).write_text(text, encoding="utf-8")
    for i in range(max(scale, 5)):
        soak.write(f"note-{i}.md", long_document("note", i))


async def _drive(run: _Run) -> None:
    await _build(run)
    await _add(run)
    await _reparse_and_rebuild(run)
    await _delete(run)
    await _gone_from_disk(run)
    await _interrupt_and_resume(run)
    await _second_writer(run)
    await _reconciled(run)


async def soak_shape(kind: str, shape: Shape, weft: Path, work: Path, scale: int) -> list[str]:
    """Run one layer shape's whole lifecycle on one backend and return every violation found."""
    backend = Backend(kind=kind, database=f"weft_soak_{kind}_{uuid.uuid4().hex[:8]}")
    soak = soak_layers.Soak(backend, weft, work)
    await soak.guard()
    await _setup(backend, soak, shape, scale)
    run = _Run(
        soak=soak,
        shape=shape,
        base=base_argv(backend, shape),
        per_source=_per_source_layers(shape),
        corpus_layer=_corpus_layer(shape),
    )
    try:
        await _drive(run)
    finally:
        soak.violations += await soak_layers.teardown(backend)
    return soak.violations
