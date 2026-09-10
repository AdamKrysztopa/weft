"""`weft graph bridges` — the graph half of the falsification instrument. **11.13**.

Mirrors `packages/weft-rag/src/weft_kg/bridges.py` and the fourth `Command` in
`packages/weft-rag/src/weft_kg/commands.py`. Against the real Postgres container, skipped with a
reason when it is absent, in the module-level form `test_graph_commands.py` uses and for the same
reason: every test here reads or writes the pack's own tables.

**What the command is for, and why it is not another way of listing the graph.** `11.10` shipped
four graph rungs and the measured run said plainly that the demonstration corpus was too small to
show the graph beating the vector baseline, which answered the same question correctly. A
comparison is only evidence where the two sides *can* disagree, so this command manufactures the
questions on which a single-passage retriever must fail: **two-hop paths whose endpoints share no
chunk.** No chunk holds both endpoints, so no passage answers the question, so no embedding is good
enough — the ceiling is a property of the corpus, not of the retriever.

**The ceiling is measured by a second query and the two are made to disagree.** The bridge query's
own `NOT EXISTS` clause is what selects a path in the first place, so reading the ceiling off that
clause would be a comparison whose two sides come from one source and could not fail
(`docs/lessons.md` `L5.6`). `GraphStore.chunks_by_entity` is a different query with a different
filter, `weft_kg.bridges.bridges_from` compares the two, and `CeilingDisagreesError` is what
happens when they differ — `test_a_ceiling_that_disagreed_with_the_walk_is_refused` plants exactly
that disagreement rather than trusting the sentence.

**Generated questions are diagnostic and can never be V2 ground truth.** `--write` emits the JSON
`weft eval run --questions` reads, carrying `kind = "requires-graph-hop"`, which is what makes
`weft eval compare … --kind requires-graph-hop` — `01` → Phase 11's own Exit clause — a
measurement rather than a plan. The pasteable TOML the renderer prints is the *other* direction: a
skeleton for a person who wants one of these in `eval/questions/`, and `eval/check_questions.py`
refuses it, because `reference_answer` is empty, `notes` is empty and `requires-graph-hop` is not
one of V2's kinds. That refusal is the property, and this file asserts it through the real V2
reader rather than against a copy of its rules.

**Why the command writes no `quote`, and why that is 11.14's sentence arriving early.** A hop's
citation is the node whose `ExtractedFact` stated it, and a fact node's content is the model's
rendering of a triple — a claim *derived from* a chunk, not the chunk's own words. V2 verifies a
quote by finding it verbatim in the extracted document, so a quote taken from a fact node would be
ground truth that is false about the corpus. The command therefore cites the node and leaves the
quote to the person, which is the honest half of the same distinction.
"""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from check_questions import Question as GroundTruthQuestion
from pydantic import SecretStr, ValidationError

from weft_cli.eval_scoring import load_questions
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.services import ServiceSelection
from weft_command.contract import CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_kg.bridges import (
    QUESTION_KIND,
    Bridge,
    BridgeCandidate,
    BridgeHop,
    CeilingDisagreesError,
    NoRelationsToBridgeError,
    VectorCeiling,
    bridges_from,
    questions_as_json,
)
from weft_kg.commands import (
    GraphBridgesArgs,
    GraphBridgesCommand,
    GraphBridgesResult,
    bridges_as_question_toml,
    render_graph_bridges,
)
from weft_kg.payload import ExtractedFact
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


def _fact_node(source: str, predicate: str, target: str, *, document: str) -> Node:
    """A node carrying an `ExtractedFact`, the shape `llm-facts` writes and this command reads.

    `document` is the whole point of the fixture: a bridge is only a bridge when no *chunk* holds
    both endpoints, and the cheapest way to arrange that in a test is one fact per node.
    """
    node = Node.synthetic(
        content=f"{source} {predicate} {target}",
        media_type=MediaType.TEXT,
        reason="weft_kg's own bridges test",
        sources=frozenset({SourceId(document)}),
    )
    return node.with_ext(
        ExtractedFact(
            source=source,
            source_type="thing",
            predicate=predicate,
            target=target,
            target_type="thing",
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
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM kg_active_schema")
    await conn.close()
    await instance.aclose()


async def _two_document_bridge(store: GraphStore) -> tuple[Node, Node]:
    """`Azouz --authored--> mRMR --evaluated-on--> NCI`, one hop per document.

    `Azouz` and `NCI` are named in no common node, so the pair is a bridge; `mRMR` is named in
    both, which is what makes it the via.
    """
    first = _fact_node("Azouz", "authored", "mRMR", document="doc-a")
    second = _fact_node("mRMR", "evaluated-on", "NCI", document="doc-b")
    await store.add([first, second])
    return first, second


def _bridges_result(outcome: Outcome[CommandResult]) -> GraphBridgesResult:
    """Narrow an `Outcome` to this command's own result, for the type checker and for the reader.

    `Outcome` is a union and `CommandResult` is the base, so `outcome.value.bridges` is not a
    fact a checker can establish — `test_graph_commands.py` takes the identical narrowing for
    `GraphShowResult`. Both assertions are real: a `Failed` or a foreign result type here is a
    defect, and this is where it names itself.
    """
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, GraphBridgesResult)
    return result


# ---------------------------------------------------------------- the walk ---


async def test_a_two_hop_path_whose_endpoints_share_no_chunk_is_found(store: GraphStore) -> None:
    """The happy path, and the property the whole command exists for."""
    # Arrange
    await _two_document_bridge(store)

    # Act
    outcome = await GraphBridgesCommand(_SETTINGS).run(GraphBridgesArgs(), _ctx())

    # Assert
    result = _bridges_result(outcome)
    assert len(result.bridges) == 1
    bridge = result.bridges[0]
    assert bridge.endpoints == ("Azouz", "NCI")
    assert bridge.via == "mRMR"


async def test_each_hop_carries_the_node_that_evidenced_it(store: GraphStore) -> None:
    """*"each hop with its own citation"* — the node whose fact stated that hop, and the
    document that node came from, never the path as one undifferentiated claim."""
    # Arrange
    first, second = await _two_document_bridge(store)

    # Act
    outcome = await GraphBridgesCommand(_SETTINGS).run(GraphBridgesArgs(), _ctx())

    # Assert
    bridge = _bridges_result(outcome).bridges[0]
    assert [hop.node_id for hop in bridge.hops] == [str(first.id), str(second.id)]
    assert [hop.predicate for hop in bridge.hops] == ["authored", "evaluated-on"]
    assert [set(hop.documents) for hop in bridge.hops] == [{"doc-a"}, {"doc-b"}]


async def test_a_hop_is_printed_in_the_direction_the_corpus_stated_it(store: GraphStore) -> None:
    """A walk is undirected and a **fact is not**, and printing one as the other is a false claim
    standing beside a true citation.

    `kg_relations` stores a direction and `GraphWalk.neighbourhood` walks it undirected, which has
    always been right — that walk returns entities and states no predicate. This command states
    one. So a hop the walk traverses against the stored direction must still read the way the
    corpus wrote it: the path here runs `Azouz -> mRMR -> NCI` and the corpus said *mRMR was
    authored-by Azouz*, so `mRMR --authored-by--> Azouz` is the true hop and
    `Azouz --authored-by--> mRMR` is the fact inverted — "a plausible answer against the wrong
    data", one arrowhead wide.
    """
    # Arrange
    await store.add(
        [
            _fact_node("mRMR", "authored-by", "Azouz", document="doc-a"),
            _fact_node("mRMR", "evaluated-on", "NCI", document="doc-b"),
        ]
    )

    # Act
    outcome = await GraphBridgesCommand(_SETTINGS).run(GraphBridgesArgs(), _ctx())

    # Assert
    result = _bridges_result(outcome)
    bridge = result.bridges[0]
    assert bridge.endpoints == ("Azouz", "NCI")
    assert bridge.via == "mRMR"
    assert (bridge.hops[0].source, bridge.hops[0].target) == ("mRMR", "Azouz")
    assert (bridge.hops[1].source, bridge.hops[1].target) == ("mRMR", "NCI")
    stdout = render_graph_bridges(result).stdout or ""
    assert "mRMR --authored-by--> Azouz" in stdout
    assert "Azouz --authored-by--> mRMR" not in stdout


async def test_two_entities_that_share_a_chunk_are_not_a_bridge(store: GraphStore) -> None:
    """The edge case that decides what the command is measuring. Once one node names both
    endpoints, a single passage can answer the question and the pair stops being evidence — the
    walk still exists, and it is no longer a *bridge*."""
    # Arrange
    await _two_document_bridge(store)
    await store.add([_fact_node("Azouz", "used", "NCI", document="doc-c")])

    # Act
    outcome = await GraphBridgesCommand(_SETTINGS).run(GraphBridgesArgs(), _ctx())

    # Assert
    assert [bridge.endpoints for bridge in _bridges_result(outcome).bridges] == []


async def test_a_corpus_with_relations_but_no_bridge_reports_it_rather_than_refusing(
    store: GraphStore,
) -> None:
    """`11.10`'s own measured finding, made printable: a corpus every one of whose relations is
    answerable from a single chunk has **no** question on which the graph must win, and saying so
    is the diagnostic answer rather than a failure."""
    # Arrange
    await store.add([_fact_node("Azouz", "authored", "mRMR", document="doc-a")])

    # Act
    outcome = await GraphBridgesCommand(_SETTINGS).run(GraphBridgesArgs(), _ctx())

    # Assert
    result = _bridges_result(outcome)
    assert result.bridges == ()
    assert result.relations_examined == 1


async def test_a_corpus_with_no_relations_at_all_refuses_naming_the_rung_to_run(
    store: GraphStore,
) -> None:
    """The other cause, and the other remedy — `weft_kg.schema.propose_schema`'s own split. A
    corpus that produced no relation needs indexing; telling that operator their corpus is too
    small is advice for a problem they do not have."""
    # Arrange / Act / Assert
    with pytest.raises(NoRelationsToBridgeError, match="index-with-facts"):
        await GraphBridgesCommand(_SETTINGS).run(GraphBridgesArgs(), _ctx())
    del store


# ------------------------------------------------------------- the ceiling ---


async def test_the_vector_ceiling_is_measured_for_every_bridge(store: GraphStore) -> None:
    """*"prints the vector ceiling on the same question"* — the best any single-passage retriever
    could reach, which is a fact about the corpus rather than about an embedder."""
    # Arrange
    await _two_document_bridge(store)

    # Act
    outcome = await GraphBridgesCommand(_SETTINGS).run(GraphBridgesArgs(), _ctx())

    # Assert
    ceiling = _bridges_result(outcome).bridges[0].ceiling
    assert ceiling.chunks_holding_both == 0
    assert ceiling.best_single_chunk_endpoints == 1
    assert ceiling.chunks_holding_either == 2


def test_a_ceiling_that_disagreed_with_the_walk_is_refused() -> None:
    """The check's own teeth, and the reason the ceiling is a second query. The walk says these
    endpoints share no chunk; this `chunks_by_entity` says they share one. One of the two is
    wrong, and printing either number would be printing a measurement nothing checked."""
    # Arrange
    candidates = (_candidate(),)
    chunks_by_entity = {"e-azouz": frozenset({"n-1"}), "e-nci": frozenset({"n-1", "n-2"})}

    # Act / Assert
    with pytest.raises(CeilingDisagreesError, match="Azouz"):
        bridges_from(candidates, chunks_by_entity=chunks_by_entity)


def test_the_ceiling_agrees_when_the_two_queries_agree() -> None:
    """The same comparison's other verdict, so the test above is known to be about disagreement
    rather than about `bridges_from` refusing everything."""
    # Arrange
    candidates = (_candidate(),)
    chunks_by_entity = {"e-azouz": frozenset({"n-1"}), "e-nci": frozenset({"n-2"})}

    # Act
    bridges = bridges_from(candidates, chunks_by_entity=chunks_by_entity)

    # Assert
    assert bridges[0].ceiling == VectorCeiling(
        endpoints=("Azouz", "NCI"),
        chunks_holding_both=0,
        chunks_holding_either=2,
        best_single_chunk_endpoints=1,
    )


# -------------------------------------------------------- what gets written ---


async def test_write_emits_the_json_weft_eval_run_reads(store: GraphStore, tmp_path: Path) -> None:
    """The clause that turns `01` → Phase 11's Exit into a measurement, asserted **through the
    real reader** rather than against a copy of its field names: `weft_cli.eval_scoring.
    load_questions` is what `weft eval run --questions` calls, and it forbids extra keys."""
    # Arrange
    await _two_document_bridge(store)
    path = tmp_path / "bridges.json"

    # Act
    outcome = await GraphBridgesCommand(_SETTINGS).run(GraphBridgesArgs(write=str(path)), _ctx())

    # Assert
    assert _bridges_result(outcome).written_to == str(path)
    questions = load_questions(path)
    assert len(questions) == 1
    assert questions[0].kind == QUESTION_KIND
    assert set(questions[0].relevant_documents) == {"doc-a", "doc-b"}
    assert "Azouz" in questions[0].query and "NCI" in questions[0].query


async def test_nothing_is_written_when_the_corpus_yields_no_bridge(
    store: GraphStore, tmp_path: Path
) -> None:
    """An empty question file is worse than none: `weft eval run --questions` would accept it and
    score nothing, and a comparison over nothing reports `n=0` rather than saying why."""
    # Arrange
    await store.add([_fact_node("Azouz", "authored", "mRMR", document="doc-a")])
    path = tmp_path / "bridges.json"

    # Act
    outcome = await GraphBridgesCommand(_SETTINGS).run(GraphBridgesArgs(write=str(path)), _ctx())

    # Assert
    assert _bridges_result(outcome).written_to == ""
    assert not path.exists()


def test_the_written_questions_are_a_json_list_of_the_shape_the_reader_forbids_extras_in() -> None:
    """The pure half, with no container: what `questions_as_json` produces is a JSON **list**,
    which is the one structural thing `load_questions` checks before it validates anything."""
    # Arrange
    bridges = bridges_from(
        (_candidate(),),
        chunks_by_entity={"e-azouz": frozenset({"n-1"}), "e-nci": frozenset({"n-2"})},
    )

    # Act
    parsed = json.loads(questions_as_json(bridges))

    # Assert
    assert isinstance(parsed, list)
    assert parsed[0]["kind"] == QUESTION_KIND


# ---------------------------------------------- diagnostic, never V2 truth ---


def test_the_pasteable_toml_is_refused_by_the_v2_reader() -> None:
    """*"Generated questions are diagnostic, never V2 ground truth."* Asserted through
    `eval/check_questions.py` itself — the reader the gate runs — so the guard is the real one and
    not a restatement of it here. It is refused on **both** counts: no reference answer, and a
    kind V2 does not have."""
    # Arrange
    bridges = bridges_from(
        (_candidate(),),
        chunks_by_entity={"e-azouz": frozenset({"n-1"}), "e-nci": frozenset({"n-2"})},
    )
    entry = tomllib.loads(_toml_of(bridges))["question"][0]

    # Act / Assert
    with pytest.raises(ValidationError) as caught:
        GroundTruthQuestion.model_validate(entry)
    reported = str(caught.value)
    assert "reference_answer" in reported
    assert "kind" in reported


def test_filling_the_reference_answer_alone_does_not_make_it_ground_truth() -> None:
    """The half a reader would otherwise get wrong. The ledger line says the empty
    `reference_answer` is what V2 refuses; it is refused on the *kind* as well, and that second
    refusal is the one that cannot be filled in — promoting one of these is a person deciding it
    is a V2 question of a V2 kind, not a person completing a form."""
    # Arrange
    bridges = bridges_from(
        (_candidate(),),
        chunks_by_entity={"e-azouz": frozenset({"n-1"}), "e-nci": frozenset({"n-2"})},
    )
    entry = dict(tomllib.loads(_toml_of(bridges))["question"][0])
    entry["reference_answer"] = "Azouz authored mRMR, which was evaluated on NCI."
    entry["notes"] = "written by hand from doc-a and doc-b"

    # Act / Assert
    with pytest.raises(ValidationError, match="kind"):
        GroundTruthQuestion.model_validate(entry)


def test_the_toml_carries_no_quote_because_a_fact_is_not_the_chunk_s_own_words() -> None:
    """**11.14's sentence, arriving where it is first load-bearing.** A citation on a fact is a
    citation on a claim *derived from* a chunk. V2 verifies a quote by finding it verbatim in the
    extracted document; a span taken off a fact node is the model's rendering of a triple and is
    in no document, so writing one would be ground truth that is false about the corpus."""
    # Arrange
    bridges = bridges_from(
        (_candidate(),),
        chunks_by_entity={"e-azouz": frozenset({"n-1"}), "e-nci": frozenset({"n-2"})},
    )

    # Act
    rendered = _toml_of(bridges)

    # Assert
    assert "quote" not in _toml_keys(rendered)
    assert "derived from" in rendered


# ------------------------------------------------------------- the surface ---


async def test_the_ceiling_is_printed_before_the_path_it_is_the_ceiling_for(
    store: GraphStore,
) -> None:
    """*"and prints the vector ceiling on the same question **first**"* — the order is the
    argument. A reader who meets the path first has already been told the graph found something;
    the ceiling is what says the vector baseline could not have."""
    # Arrange
    await _two_document_bridge(store)
    outcome = await GraphBridgesCommand(_SETTINGS).run(GraphBridgesArgs(), _ctx())

    # Act
    stdout = render_graph_bridges(_bridges_result(outcome)).stdout or ""

    # Assert
    assert stdout.index("vector ceiling") < stdout.index("authored")


def test_the_command_declares_its_permission_class() -> None:
    """`WRITE`, not `READ` — `weft eval run`'s own footing. `--write` creates a questions file,
    and a permission class is a fact about what a command *can* do, never about which flags this
    invocation happened to carry."""
    # Arrange / Act / Assert
    assert GraphBridgesCommand(_SETTINGS).permission_class is PermissionClass.WRITE


def test_the_pack_discloses_the_file_this_command_writes() -> None:
    """`02` §2 → *The trust model*: a pack that writes files while declaring none answers the
    question wrongly rather than not at all — `11.11`'s own finding, one command later."""
    # Arrange
    from weft_kg import DISCLOSURE

    # Act
    declared = " ".join(DISCLOSURE.filesystem)

    # Assert
    assert "graph bridges" in declared


# ------------------------------------------------------------------ helpers ---


def _candidate() -> BridgeCandidate:
    """One `BridgeCandidate` as `GraphStore.two_hop_bridges` returns it, built by hand so the
    pure half can be exercised with no container — the same split `test_schema.py` uses for
    `propose_schema`.
    """
    return BridgeCandidate(
        source_entity="e-azouz",
        source_name="Azouz",
        via_name="mRMR",
        target_entity="e-nci",
        target_name="NCI",
        first=BridgeHop(
            source="Azouz",
            predicate="authored",
            target="mRMR",
            node_id="n-1",
            documents=("doc-a",),
        ),
        second=BridgeHop(
            source="mRMR",
            predicate="evaluated-on",
            target="NCI",
            node_id="n-2",
            documents=("doc-b",),
        ),
    )


def _toml_of(bridges: tuple[Bridge, ...]) -> str:
    return bridges_as_question_toml(bridges)


def _toml_keys(rendered: str) -> frozenset[str]:
    return frozenset(tomllib.loads(rendered)["question"][0])
