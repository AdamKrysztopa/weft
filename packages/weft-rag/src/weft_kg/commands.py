"""`weft graph propose`, `activate`, `show` and `bridges` — this pack's `Command`s. **11.11**,
`bridges` at **11.13**.

**The first three answer three different questions and only one of them writes.** `propose`
measures what the corpus's own facts already produced and prints it — nothing persists.
`activate` is the operator's own decision, and it is the only one that touches anything. `show`
reports what is true of the corpus right now. That split is why the permission classes differ
(`activate` is `WRITE`, the other two `READ`), and `03` → *Permissions* makes a pack declare each
at registration with no default (G3).

**Why `activate` writes in two places, and why that is not redundancy — `S13`.** The **file** is
what an operator approves: a diffable artefact a pull request can show, named from `[packs.graph]`
so it is per project, on `weft.toml`'s own footing since `03:909`. The **row**
(`weft_kg.store.GraphStore.activate_schema`) is what the corpus itself is under. Answered from the
file alone, *which schema is this corpus under* would be a property of whichever operator's disk
was asked, so two checkouts pointing at one database could hold contradictory beliefs with nothing
to notice — the silence `weft_kg.store`'s own module docstring refuses. **Order matters and so
does the direction**: `load_schema` first, so a malformed file leaves nothing written; the file
second; the row last — a row naming a schema the file cannot produce is the state nothing could
diagnose.

**`propose`'s renderer prints the proposed schema as the TOML an operator can paste into a file**,
because that is the whole workflow this command exists for: propose, edit by hand, activate.
**`show`'s renderer prints every schema the corpus's own facts carry, the untagged group
included** — `weft_kg.store.SchemaPresence`'s own docstring: *a corpus holding two schemas is a
fact this prints, never a silence.*

**`bridges` is the falsification instrument `11.10`'s own measured run argued for.** It manufactures
the questions on which a single-passage retriever must fail — two-hop paths whose endpoints share
no chunk — citing each hop's own evidence and measuring the vector ceiling from a second,
independent query rather than trusting the walk's own filter; see `weft_kg.bridges`'s module
docstring for the full argument and `CeilingDisagreesError`'s own docstring for what happens when
the two disagree. `WRITE`, not `READ`, because `--write` can create a file — a permission class is
a fact about what a command *can* do, never about which flags one invocation happened to carry.
Its renderer prints the ceiling before the path for every bridge, once — the order is the
argument, not an incidental choice — then the pasteable TOML skeleton for a person who wants to
promote one of these into `eval/questions/`; that skeleton carries no `quote`, because a hop's
citation is a node whose `ExtractedFact` is a model's *rendering* of a triple, never the chunk's
own words, and V2 verifies a quote by finding it verbatim in the extracted document.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.config_surface import set_config_text
from weft_cli.registry_bootstrap import DEFAULT_CONFIG_PATH
from weft_command import ExitCode, Rendered
from weft_command.contract import CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kg.bridges import (
    QUESTION_KIND,
    Bridge,
    bridges_from,
    no_relations_to_bridge_error,
    questions_as_json,
)
from weft_kg.schema import GraphSchema, load_schema, propose_schema
from weft_kg.store import ActiveSchema, GraphSettings, GraphStore, SchemaPresence


class GraphProposeArgs(BaseModel):
    """`weft graph propose [--min-count N] [--name NAME]` — no path: this measures the corpus
    that is already there and prints, it never reads or writes a file of its own.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_count: int = Field(default=2, ge=1)
    name: str = Field(default="proposed", min_length=1)


class GraphProposeResult(CommandResult):
    """What one `propose` run measured. `observed` is the number of *distinct* arrangements the
    corpus produced, at any count — never the number that survived `min_count`, which is already
    visible as `len(proposed.relations)`; the two together are what tells an operator how much of
    what their corpus said, `min_count` actually kept.
    """

    proposed: GraphSchema
    observed: int


class GraphActivateArgs(BaseModel):
    """`weft graph activate <path>` — the curated schema file to activate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)


class GraphActivateResult(CommandResult):
    """What `activate` did: which schema, by name and by identity, from which file, recorded
    into which project file — `config_path` alongside `path` because the two are not the same
    string once `weft.toml` lives somewhere other than the current directory.
    """

    name: str
    identity: str
    path: str
    config_path: str


class GraphShowArgs(BaseModel):
    """`weft graph show` — no arguments: it reports the corpus's own state, never one entity's."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class GraphShowResult(CommandResult):
    """The corpus's own answer to *which schema is this under*, and *which schemas does it hold
    evidence of* — `weft_kg.store.ActiveSchema`/`SchemaPresence`'s own docstrings for what each
    carries and why `schemas_in_corpus` is never truncated to the active one alone.
    """

    active: ActiveSchema | None
    schemas_in_corpus: tuple[SchemaPresence, ...]


class GraphBridgesArgs(BaseModel):
    """`weft graph bridges [--limit N] [--write PATH]` — no other argument: this measures the
    corpus that is already there, exactly like `propose`, plus one optional side effect.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    limit: int = Field(default=10, ge=1, description="how many bridges to list at most")
    write: str = Field(
        default="",
        description=(
            "write the questions to this path as the JSON `weft eval run --questions` reads; "
            "nothing is written when the corpus yields no bridge"
        ),
    )


class GraphBridgesResult(CommandResult):
    """What one `bridges` run found. `relations_examined` is what tells the two refusal-adjacent
    outcomes apart when `bridges` is empty: a corpus with relations but no bridge among them
    (`11.10`'s own measured finding, printable) against one with none at all
    (`NoRelationsToBridgeError`, raised before this result is ever built). `written_to` is `""`
    whenever nothing was written — see `GraphBridgesArgs.write`'s own docstring for when that is.
    """

    bridges: tuple[Bridge, ...]
    relations_examined: int
    written_to: str


class GraphProposeCommand:
    """Measures the corpus and proposes a schema from it. Persists nothing — see the module
    docstring's opening paragraph.
    """

    args_model: ClassVar[type[BaseModel]] = GraphProposeArgs
    result_model: ClassVar[type[CommandResult]] = GraphProposeResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "propose a curated schema from the arrangements the corpus already wrote"

    def __init__(self, settings: GraphSettings, config: object = None) -> None:
        del config
        self._store = GraphStore(settings)

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        propose_args = cast(GraphProposeArgs, args)
        observed = await self._store.observed_triples()
        schema = propose_schema(observed, name=propose_args.name, min_count=propose_args.min_count)
        return Produced(value=GraphProposeResult(proposed=schema, observed=len(observed)))


class GraphActivateCommand:
    """Activates a curated schema file: writes `[packs.graph] schema_file` into `weft.toml` and
    records the schema's own identity on the corpus. `WRITE`, not `OVERWRITE` — see the module
    docstring: this edits `weft.toml`, exactly what `weft config set` does, and the 2026-08-20
    repair moved that kind of edit out of `overwrite`.
    """

    args_model: ClassVar[type[BaseModel]] = GraphActivateArgs
    result_model: ClassVar[type[CommandResult]] = GraphActivateResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = (
        "activate a curated schema file: write it into weft.toml and record it on the corpus"
    )

    def __init__(self, settings: GraphSettings, config: object = None) -> None:
        del config
        self._store = GraphStore(settings)

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        activate_args = cast(GraphActivateArgs, args)
        # Validate first — a `MalformedSchemaFileError` here leaves nothing written, which is
        # what makes a half-activation (a row naming a schema the file cannot produce) impossible
        # rather than merely unlikely. See the module docstring's own "order matters" paragraph.
        schema = load_schema(Path(activate_args.path))

        config_path = DEFAULT_CONFIG_PATH
        current = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
        updated = set_config_text(
            current, section="packs.graph", key="schema_file", value=activate_args.path
        )
        config_path.write_text(updated, encoding="utf-8")

        await self._store.activate_schema(schema, source_path=activate_args.path)

        return Produced(
            value=GraphActivateResult(
                name=schema.name,
                identity=schema.identity,
                path=activate_args.path,
                config_path=str(config_path),
            )
        )


class GraphShowCommand:
    """Reports the corpus's own state: its active schema, and every schema its facts carry."""

    args_model: ClassVar[type[BaseModel]] = GraphShowArgs
    result_model: ClassVar[type[CommandResult]] = GraphShowResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = (
        "show the corpus's active schema and every schema its facts were extracted under"
    )

    def __init__(self, settings: GraphSettings, config: object = None) -> None:
        del config
        self._store = GraphStore(settings)

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx, args
        active = await self._store.active_schema()
        schemas_in_corpus = await self._store.schemas_in_corpus()
        return Produced(value=GraphShowResult(active=active, schemas_in_corpus=schemas_in_corpus))


class GraphBridgesCommand:
    """Lists two-hop paths whose endpoints share no chunk, with the vector ceiling on each —
    see the module docstring's `bridges` paragraph and `weft_kg.bridges`'s own for the full
    argument.
    """

    args_model: ClassVar[type[BaseModel]] = GraphBridgesArgs
    result_model: ClassVar[type[CommandResult]] = GraphBridgesResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = (
        "list two-hop paths whose endpoints share no chunk, with the vector ceiling on each"
    )

    def __init__(self, settings: GraphSettings, config: object = None) -> None:
        del config
        self._store = GraphStore(settings)

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        bridges_args = cast(GraphBridgesArgs, args)
        relations = await self._store.relation_count()
        if relations == 0:
            raise no_relations_to_bridge_error()

        candidates = await self._store.two_hop_bridges(limit=bridges_args.limit)
        entity_ids: set[str] = set()
        for candidate in candidates:
            entity_ids.add(candidate.source_entity)
            entity_ids.add(candidate.target_entity)
        chunks_by_entity = await self._store.chunks_by_entity(tuple(sorted(entity_ids)))
        bridges = bridges_from(candidates, chunks_by_entity=chunks_by_entity)

        written_to = ""
        if bridges and bridges_args.write:
            Path(bridges_args.write).write_text(questions_as_json(bridges), encoding="utf-8")
            written_to = bridges_args.write

        return Produced(
            value=GraphBridgesResult(
                bridges=bridges, relations_examined=relations, written_to=written_to
            )
        )


def _quote(value: str) -> str:
    """The identical escaping `weft_cli.config_surface._quote` uses, restated rather than
    imported: that name is private to its own module, and a curated schema's TOML is this pack's
    own artefact to render, not `weft_cli`'s.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _schema_as_toml(schema: GraphSchema) -> str:
    """`schema`, rendered as the TOML `weft_kg.schema.load_schema` reads back — the exact shape
    an operator pastes into a file and activates unchanged. `schema_version` is left out: a fresh
    proposal is always this installed pack's own current version, which is the default
    `GraphSchema.schema_version` already supplies with nothing written.
    """
    lines = [f"name = {_quote(schema.name)}", ""]
    for relation in schema.relations:
        lines.extend(
            [
                "[[relations]]",
                f"source_type = {_quote(relation.source_type)}",
                f"predicate = {_quote(relation.predicate)}",
                f"target_type = {_quote(relation.target_type)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip("\n") + "\n"


def render_graph_propose(result: object) -> Rendered:
    """`weft graph propose`, for a person — task **6.20**, G13's third repair, the same seam
    `weft_cli.commands.register` uses for its own eighteen built-ins.

    Prints the schema as pasteable TOML, not a structured summary: the whole workflow this
    command exists for is propose, edit by hand, activate, and a summary would have to be
    translated back into the file an operator actually needs.
    """
    typed = cast(GraphProposeResult, result)
    header = (
        f"# proposed from {typed.observed} distinct arrangement(s) the corpus already wrote\n"
        f"# paste into a file, edit as needed, then: weft graph activate <path>\n"
    )
    return Rendered(
        stdout=header + _schema_as_toml(typed.proposed), stderr=None, exit_code=ExitCode.SUCCESS
    )


def render_graph_activate(result: object) -> Rendered:
    """`weft graph activate`, for a person — states both halves `S13` writes, so an operator sees
    that the file and the corpus were both updated rather than inferring it.
    """
    typed = cast(GraphActivateResult, result)
    lines = [
        f"activated '{typed.name}' ({typed.identity})",
        f"  from {typed.path}",
        f"  recorded in {typed.config_path} and on the corpus",
    ]
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def render_graph_show(result: object) -> Rendered:
    """`weft graph show`, for a person — **the sentence this task exists for**: *a corpus holding
    two schemas is a fact this prints, never a silence.* Every entry in `schemas_in_corpus` is
    printed, the untagged one included, never only the active identity.
    """
    typed = cast(GraphShowResult, result)
    lines: list[str] = []
    if typed.active is not None:
        lines.append(f"active schema: '{typed.active.name}' ({typed.active.identity})")
        lines.append(f"  from {typed.active.source_path}, activated {typed.active.activated_at}")
    else:
        lines.append("no schema is active")
    if typed.schemas_in_corpus:
        lines.append("schemas the corpus's facts carry:")
        for presence in typed.schemas_in_corpus:
            label = presence.identity if presence.identity else "(no schema)"
            lines.append(f"  {label}: {presence.facts} fact(s)")
    else:
        lines.append("the corpus holds no facts")
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


#: The comment block `bridges_as_question_toml` prints above every `[[question]]` table — see
#: that function's own docstring for the two things it has to say and why. Kept as one constant
#: rather than inlined, so the required "derived from" sentence lives in exactly one place.
_BRIDGE_TOML_HEADER = (
    "# diagnostic questions, not V2 ground truth. eval/check_questions.py refuses these until a\n"
    "# person writes the reference answer, the provenance note, language and difficulty, and\n"
    "# chooses one of V2's own kinds. No quote is written: a citation on a fact is a citation\n"
    "# on a claim derived from a chunk, so a span taken off a fact node is the model's\n"
    "# rendering of a triple and appears verbatim in no document, which is what a V2 quote is\n"
    "# verified against.\n"
)


def bridges_as_question_toml(bridges: Sequence[Bridge]) -> str:
    """`bridges`, as pasteable TOML for a person who wants one of these in `eval/questions/`.

    Deliberately not V2 ground truth — see `_BRIDGE_TOML_HEADER` and the module docstring's
    `bridges` paragraph. Exactly six keys per `[[question]]`, no `quote` among them: `id`,
    `text`, `kind`, `relevant_documents`, `reference_answer = ""`, `notes = ""`.
    """
    lines = [_BRIDGE_TOML_HEADER]
    for bridge in bridges:
        documents = ", ".join(_quote(document) for document in bridge.relevant_documents)
        lines.extend(
            [
                "[[question]]",
                f"id = {_quote(bridge.question_id)}",
                f"text = {_quote(bridge.question)}",
                f"kind = {_quote(QUESTION_KIND)}",
                f"relevant_documents = [{documents}]",
                'reference_answer = ""',
                'notes = ""',
                "",
            ]
        )
    return "\n".join(lines).rstrip("\n") + "\n"


def render_graph_bridges(result: object) -> Rendered:
    """`weft graph bridges`, for a person — the vector ceiling before the path, for every bridge,
    because a reader who meets the path first has already been told the graph found something;
    the ceiling is what says the vector baseline could not have. See the module docstring's
    `bridges` paragraph.
    """
    typed = cast(GraphBridgesResult, result)
    lines = [f"{len(typed.bridges)} bridge(s) found among {typed.relations_examined} relation(s)"]
    if not typed.bridges:
        lines.append(
            "this corpus's relations are all answerable from a single chunk, so it holds no "
            "question on which a graph must beat a vector baseline. A larger corpus, or a rung "
            "that extracts more facts, is what produces one."
        )
        return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)

    for index, bridge in enumerate(typed.bridges, start=1):
        ceiling = bridge.ceiling
        lines.append(f"bridge {index}: {bridge.question}")
        lines.append(
            f"  vector ceiling: {ceiling.chunks_holding_both} chunk(s) hold both endpoints; "
            f"best single chunk holds {ceiling.best_single_chunk_endpoints} of 2; "
            f"{ceiling.chunks_holding_either} chunk(s) hold either"
        )
        # The walk, with a plain dash rather than an arrow: reach is undirected, and the arrows
        # below belong to the facts, which are not. Printing both is what lets a reader see that
        # a hop was traversed against the direction its own fact was written in.
        lines.append(f"  path: {bridge.endpoints[0]} — {bridge.via} — {bridge.endpoints[1]}")
        for hop in bridge.hops:
            documents = ", ".join(hop.documents)
            lines.append(
                f"  {hop.source} --{hop.predicate}--> {hop.target} "
                f"[node {hop.node_id}; {documents}]"
            )

    lines.append("")
    lines.append("paste into eval/questions/*.toml, then fill in what the comment names:")
    lines.append(bridges_as_question_toml(typed.bridges))

    if typed.written_to:
        lines.append(
            f"wrote {len(typed.bridges)} question(s) to {typed.written_to} — "
            f"weft eval run --questions {typed.written_to}"
        )

    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


__all__ = [
    "GraphActivateArgs",
    "GraphActivateCommand",
    "GraphActivateResult",
    "GraphBridgesArgs",
    "GraphBridgesCommand",
    "GraphBridgesResult",
    "GraphProposeArgs",
    "GraphProposeCommand",
    "GraphProposeResult",
    "GraphShowArgs",
    "GraphShowCommand",
    "GraphShowResult",
    "bridges_as_question_toml",
    "render_graph_activate",
    "render_graph_bridges",
    "render_graph_propose",
    "render_graph_show",
]
