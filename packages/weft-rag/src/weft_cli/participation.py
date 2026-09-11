"""Which `NodeStore` names this project has actually run data through.

Task **6.18**, discharging G13's first repair (`docs/02-extension-model.md` §1 → *Extended by
G13*): task 5.1a narrowed the `NodeStore` fan-out to the single store `[services] store` names,
so a project with pgvector and Qdrant both installed does not connect to a database the
operator does not use. That narrowing is right about the unused backend and wrong about the
graph store, which registers under `NodeStore` too and is written to by a pipeline nothing
tells `[services] store` about. **The rule is now: the configured store, plus every `NodeStore`
named by a pipeline in the project's catalogue or by a persisted run record.** A store this
project has actually run data through participates; a store nothing selects and nothing names
does not — nothing is declared, so no pack author has a rule to remember.

**Carried repair R11.2 narrows the first half of that rule again.** `G19` folded `weft-qdrant`
into the `weft-rag` wheel, so every install now carries the pack that used to be a deliberate
opt-in. Reading the *whole* catalogue — every project-local document plus every document every
installed pack contributes — meant the moment a shipped `index-qdrant` document named `qdrant`,
every unrelated project on earth acquired a Qdrant participant. The subject is now the
project's *own* documents (`project`), plus every ancestor reached through an `extends:` chain
(resolved against `catalogue`, never a subject in its own right) — a project that derives from
a shipped rung still counts the stores that rung names, and a document nothing in the project
derives from names no store this project uses.

This module computes only the *set of names in use*; `weft_cli.fanout.participants_for` is what
turns that set into participants, keeping the two questions — "which names count" and "how a
capability fan-out is walked" — apart exactly as `weft_cli.fanout`'s own docstring already keeps
"who participates" apart from "what happens to them once known".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from weft_eval.run_record import RunRecord, load_run_record
from weft_kernel.errors import WeftError
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry
from weft_store import NodeStore

DEFAULT_INDEX_RUNS_DIR: Final[Path] = Path("runs/index")


class UnreadableRunRecordError(WeftError):
    """A persisted run record under the runs directory will not parse.

    Raised rather than skipped, deliberately: `stores_in_use` reads the run history precisely to
    find a store a catalogue no longer names, and a record that will not parse might be the one
    record naming it. Skipping it would let that store's contents survive their source silently —
    `docs/internal/lessons.md` L5.9's rule, that an empty answer means "I did not find it" and never
    "it is not there", applied to a directory sweep instead of a single lookup.
    """

    def __init__(self, message: str, *, path: Path) -> None:
        super().__init__(message)
        self.path = path


def load_run_records(directory: Path) -> tuple[RunRecord, ...]:
    """Every persisted run record directly under `directory`, in sorted filename order.

    A `directory` that does not exist yet holds no runs — a fresh project with nothing indexed
    is not an error, so this returns `()` rather than raising. A file that exists but will not
    parse *is* refused, by name, through `UnreadableRunRecordError`: see that error's own
    docstring for why it is not simply skipped.
    """
    if not directory.is_dir():
        return ()
    records: list[RunRecord] = []
    for path in sorted(directory.glob("*.json")):
        try:
            records.append(load_run_record(path))
        except (OSError, ValueError) as exc:
            raise UnreadableRunRecordError(
                f"run record at {path} could not be read: {exc}. A store this project has "
                f"run data through may be named only here, so a run record that will not "
                f"parse is refused rather than silently skipped.",
                path=path,
            ) from exc
    return tuple(records)


def _stage_names_from_pipeline(pipeline: Pipeline) -> frozenset[str]:
    """Every plugin name a document `pipeline` can carry — `02` §1 → *Extended by G13*'s "named
    by a pipeline in the project's catalogue". `stages`, `replace` and each `insert.stage` are
    the three `StageDeclaration`-carrying places a document can name a plugin at all; `remove`
    holds stage ids to drop, never a plugin name, and `set` has no `use:` field to read.
    """
    names: set[str] = {stage.use for stage in pipeline.stages}
    names.update(stage.use for stage in pipeline.replace)
    names.update(operator.stage.use for operator in pipeline.insert)
    return frozenset(names)


def _stage_names_from_record(record: RunRecord) -> frozenset[str]:
    """Every plugin name a persisted `record` actually resolved to and ran."""
    return frozenset(stage.use for stage in record.resolved_pipeline.stages)


def _stage_names_from_ancestors(
    pipeline: Pipeline, *, project: Mapping[str, Pipeline], catalogue: Mapping[str, Pipeline]
) -> frozenset[str]:
    """Every plugin name reachable by following `pipeline.extends` up its chain.

    `catalogue` is consulted for exactly one thing — resolving a parent's name — and only
    because a project document may extend a rung an installed pack contributes rather than one
    it wrote itself; `catalogue` is looked up first and `project` second, so a project document
    that happens to share a name with a shipped one still resolves to something. **A parent
    name neither mapping holds stops that branch of the walk rather than raising.** A document
    whose `extends:` names nothing is a document that cannot resolve at all —
    `weft_kernel.resolution.UnknownParentPipelineError` already refuses it, by name, on every
    command that actually resolves one — and this function resolves none: it only asks which
    stores a document *would* reach if it could run. `weft delete` reaps stores, not documents,
    so refusing a deletion over an unrelated document's broken `extends:` would leave the stores
    it can name untouched, reaping nothing rather than too little.

    **Visited names are tracked so a cycle in `extends:` terminates this walk.**
    `weft_kernel.resolution` refuses a cycle on every path that *resolves* a document, and this
    walk resolves none, so termination has to be this function's own property.
    """
    names: set[str] = set()
    visited: set[str] = {pipeline.name}
    parent_name = pipeline.extends
    while parent_name is not None and parent_name not in visited:
        visited.add(parent_name)
        parent = catalogue.get(parent_name, project.get(parent_name))
        if parent is None:
            break
        names.update(_stage_names_from_pipeline(parent))
        parent_name = parent.extends
    return frozenset(names)


def stores_in_use(
    *,
    configured: str,
    registry: Registry,
    project: Mapping[str, Pipeline],
    catalogue: Mapping[str, Pipeline],
    records: Sequence[RunRecord],
) -> frozenset[str]:
    """The `NodeStore` names this project has actually run data through — `02` §1 → *Extended
    by G13*'s rule, narrowed by carried repair **R11.2**.

    `configured` — `[services] store` — is included unconditionally, whether or not it is
    registered: diagnosing an unresolvable `[services] store` is
    `weft_cli.registry_bootstrap.require_plugin`'s job, and repeating that translation here
    would give the same mistake two different messages (`docs/internal/lessons.md` L5.9).

    `project` is the subject — the documents this project itself wrote. Every other name is
    kept only if it is both named by something reachable from `project` — a stage in a project
    document itself, a stage in an ancestor reached through its `extends:` chain, or a stage a
    persisted run in `records` actually resolved to — *and* registered under `NodeStore` in
    `registry`: a document or a run can name a plugin registered under some other contract
    entirely (an extractor, say), and that name is not a store no matter how many pipelines
    mention it. `catalogue` is never itself a subject: a pipeline only ever present there and
    never reachable from `project` — a rung an installed pack contributes that nothing derives
    from — contributes nothing.
    """
    node_store_names = registry.names_for(NodeStore)
    named: set[str] = set()
    for pipeline in project.values():
        named.update(_stage_names_from_pipeline(pipeline))
        named.update(_stage_names_from_ancestors(pipeline, project=project, catalogue=catalogue))
    for record in records:
        named.update(_stage_names_from_record(record))
    return frozenset({configured}) | (named & node_store_names)


__all__ = [
    "DEFAULT_INDEX_RUNS_DIR",
    "UnreadableRunRecordError",
    "load_run_records",
    "stores_in_use",
]
