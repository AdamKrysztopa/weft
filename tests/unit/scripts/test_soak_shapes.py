"""Task 43.41: the soak's layer shapes — what each writes and what each calls a violation."""

from __future__ import annotations

import json
import re
import tomllib

import pytest
import soak_shapes
from soak_layers import Backend, Snapshot, Source, StoredNode
from soak_shapes import Shape

_PG = Backend(kind="pgvector", database="weft_soak_pgvector_1")
_QD = Backend(kind="qdrant", database="weft_soak_qdrant_1")


def _node(
    node_id: str, *, sources: tuple[str, ...] = ("a",), layer: str | None = None
) -> StoredNode:
    return StoredNode(
        id=node_id,
        sources=frozenset(sources),
        parents=(),
        generations=frozenset({""}),
        summary=False,
        checkpoint=False,
        layer=layer,
    )


def _snap(statuses: dict[str, dict[str, str]], nodes: tuple[StoredNode, ...]) -> Snapshot:
    return Snapshot(
        generations=(),
        sources=tuple(Source(id=s, layers=layers) for s, layers in statuses.items()),
        nodes=nodes,
    )


def test_each_shape_names_the_layers_it_soaks() -> None:
    assert soak_shapes.shape_layers(Shape.RAPTOR_SOURCE) == ("raptor-source",)
    assert soak_shapes.shape_layers(Shape.QUESTIONS) == ("enrich-with-questions",)
    assert soak_shapes.shape_layers(Shape.FACTS) == ("facts-scripted",)
    assert soak_shapes.shape_layers(Shape.STACKED) == (
        "raptor-corpus",
        "raptor-source",
        "enrich-with-questions",
        "facts-scripted",
    )


@pytest.mark.parametrize("shape", list(Shape))
@pytest.mark.parametrize("backend", [_PG, _QD], ids=["pgvector", "qdrant"])
def test_the_configuration_makes_no_paid_call_and_names_the_run_s_own_stores(
    shape: Shape, backend: Backend
) -> None:
    config = tomllib.loads(soak_shapes.shape_toml(backend, shape))

    assert {role["provider"] for role in config["llm"]["roles"].values()} == {"scripted"}
    assert config["services"]["embed"] == "hash"
    assert config["packs"]["store"]["dsn"].endswith(f"/{backend.database}")
    graph = config["packs"].get("graph")
    assert (graph is not None) is soak_shapes.uses_graph_base(shape)
    if graph is not None:
        assert graph["dsn"].endswith(f"/{backend.database}")


@pytest.mark.parametrize("shape", [Shape.FACTS, Shape.STACKED])
def test_facts_are_answered_by_their_own_role_with_a_reply_that_parses(shape: Shape) -> None:
    """Measured at 43f's opening: the scripted echo degrades every fact, so the soak built none."""
    config = tomllib.loads(soak_shapes.shape_toml(_PG, shape))
    documents = soak_shapes.shape_documents(_PG, shape)

    reply = json.loads(config["llm"]["roles"]["facts"]["settings"]["reply"])
    assert reply["facts"]
    assert re.search(
        r"\{\s*id:\s*facts,\s*with:\s*\{\s*role:\s*facts", documents["facts-scripted.yaml"]
    )


def test_the_source_scoped_raptor_layer_types_its_threshold() -> None:
    """Measured at 43f's opening: `auto` finds no threshold under `hash` on half the sources."""
    document = soak_shapes.shape_documents(_PG, Shape.RAPTOR_SOURCE)["raptor-source.yaml"]

    assert "extends: enrich-with-raptor" in document
    assert "auto" not in document
    assert "layer.scope" not in document


@pytest.mark.parametrize("shape", list(Shape))
def test_a_project_holds_only_the_documents_its_run_uses(shape: Shape) -> None:
    """Measured at 43f's opening: an unused document naming `qdrant` pulled it into the fan-out."""
    pg_documents = soak_shapes.shape_documents(_PG, shape)
    qd_documents = soak_shapes.shape_documents(_QD, shape)

    assert not any("qdrant" in text for text in pg_documents.values())
    assert ("index-qdrant-graph.yaml" in qd_documents) is soak_shapes.uses_graph_base(shape)


def test_every_index_of_a_graph_shape_names_its_base_and_no_other_does() -> None:
    assert soak_shapes.base_argv(_PG, Shape.FACTS) == ("--pipeline", "index-with-graph")
    assert soak_shapes.base_argv(_QD, Shape.FACTS) == ("--pipeline", "index-qdrant-graph")
    assert soak_shapes.base_argv(_PG, Shape.QUESTIONS) == ()
    assert soak_shapes.base_argv(_QD, Shape.RAPTOR_SOURCE) == ()


def test_the_participant_count_follows_the_stores_the_project_names() -> None:
    """Measured at 43f's opening: a Qdrant graph base counts pgvector too (`index-text`)."""
    assert soak_shapes.expected_participants(_PG, Shape.QUESTIONS) == 1
    assert soak_shapes.expected_participants(_QD, Shape.QUESTIONS) == 1
    assert soak_shapes.expected_participants(_PG, Shape.FACTS) == 2
    assert soak_shapes.expected_participants(_QD, Shape.FACTS) == 3


def test_a_document_runs_to_several_chunks_of_sentences_it_does_not_repeat() -> None:
    """One chunk builds no per-source tree, and a repeated sentence trips the loop guard."""
    text = soak_shapes.long_document("radium", 0)
    sentences = [s for s in re.split(r"(?<=\.)\s+", text.strip()) if s]

    assert len(text) > 3 * 512
    assert len(set(sentences)) == len(sentences)
    assert soak_shapes.long_document("radium", 0, revision=1) != text
    assert soak_shapes.long_document("radium", 1) != text


def test_a_layer_s_nodes_are_the_ones_stamped_with_it() -> None:
    snap = _snap(
        {}, (_node("c1"), _node("q1", layer="enrich-with-questions"), _node("s1", layer="x"))
    )

    assert soak_shapes.layer_nodes(snap, "enrich-with-questions") == frozenset({"q1"})


def test_a_build_leaves_every_layer_active_everywhere_with_nodes_of_its_own() -> None:
    clean = _snap(
        {"a": {"L": "active"}, "b": {"L": "active"}}, (_node("n1", sources=("a",), layer="L"),)
    )
    half = _snap({"a": {"L": "active"}, "b": {"L": "indexing"}}, (_node("n1", layer="L"),))
    empty = _snap({"a": {"L": "active"}}, (_node("c1"),))

    assert soak_shapes.check_built(clean, ("L",)) == []
    assert any("'L' not active on every source" in p for p in soak_shapes.check_built(half, ("L",)))
    assert any("'L' built no node" in p for p in soak_shapes.check_built(empty, ("L",)))


def test_a_re_parse_takes_its_source_s_layer_and_leaves_every_other_source_s_alone() -> None:
    before = _snap(
        {"a": {"L": "active"}, "b": {"L": "active"}},
        (_node("na", sources=("a",), layer="L"), _node("nb", sources=("b",), layer="L")),
    )
    good = _snap({"a": {}, "b": {"L": "active"}}, (_node("nb", sources=("b",), layer="L"),))
    kept = _snap({"a": {"L": "active"}, "b": {"L": "active"}}, before.nodes)
    moved = _snap({"a": {}, "b": {"L": "active"}}, (_node("nb2", sources=("b",), layer="L"),))

    assert soak_shapes.check_reparsed(before, good, "L", reparsed="a") == []
    assert any(
        "kept its record" in p for p in soak_shapes.check_reparsed(before, kept, "L", reparsed="a")
    )
    assert any("changed" in p for p in soak_shapes.check_reparsed(before, moved, "L", reparsed="a"))


def test_a_released_source_leaves_no_node_naming_it() -> None:
    clean = _snap({"b": {"L": "active"}}, (_node("nb", sources=("b",), layer="L"),))
    left = _snap({"b": {"L": "active"}}, (_node("na", sources=("a", "b"), layer="L"),))

    assert soak_shapes.check_released(clean, "a") == []
    assert any("still names 'a'" in p for p in soak_shapes.check_released(left, "a"))


def test_a_source_record_reading_indexing_is_what_an_interrupt_waits_for() -> None:
    snap = _snap({"a": {"L": "active"}, "b": {"L": "indexing"}, "c": {}}, ())

    assert soak_shapes.indexing_sources(snap, "L") == frozenset({"b"})
