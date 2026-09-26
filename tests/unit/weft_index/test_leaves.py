"""Ledger task **43.47** — one definition of a leaf serves the layer loop and the query path.

`whole-corpus` (43.49) reads every leaf of a store at query time. The only definition of a leaf
was `weft_cli.layers.layer_leaf_filter`, narrowed to a batch's sources and living in the CLI,
which a `weft_retrieve` plugin must not import. `weft_index.leaves.leaf_filter` is that
definition over a whole store; the layer loop's filter is it narrowed to a batch.
"""

import subprocess
import sys

import pytest

import weft_index.leaves as leaves_module
from tests.unit.weft_cli.leaf_selection import (
    DeclaredNotALeaf,
    chunk_node,
    ensure_registered,
    selects,
)
from weft_cli.layers import layer_leaf_filter
from weft_index.leaves import leaf_filter
from weft_index.payload import Representation
from weft_kernel.payload import MediaType, Node, SourceId
from weft_kg.payload import ExtractedFact

_ELSEWHERE = SourceId("file:///corpus/elsewhere.md")


def _chunk_of(source: SourceId) -> Node:
    return Node.synthetic(
        content=f"a chunk of {source}",
        media_type=MediaType.TEXT,
        reason="43.47 fixture chunk",
        sources=frozenset({source}),
    )


def _population() -> tuple[Node, ...]:
    chunk = chunk_node()
    return (
        chunk,
        _chunk_of(_ELSEWHERE),
        chunk.derive(content="a summary", ordinal=0).with_ext(Representation(technique="raptor")),
        chunk.derive(content="a fact", ordinal=1).with_ext(
            ExtractedFact(
                source="Marie Curie",
                source_type="Person",
                predicate="discovered",
                target="polonium",
                target_type="Element",
            )
        ),
        chunk.derive(content="a stranger's derived node", ordinal=2).with_ext(
            DeclaredNotALeaf(note="derived")
        ),
    )


def test_a_stores_leaves_are_every_underived_node_whatever_its_source() -> None:
    # Arrange
    ensure_registered(ExtractedFact, DeclaredNotALeaf)
    nodes = _population()

    # Act
    selected = {node.content for node in nodes if selects(node, leaf_filter())}

    # Assert
    assert selected == {chunk_node().content, f"a chunk of {_ELSEWHERE}"}


def test_a_layers_leaves_are_the_stores_leaves_narrowed_to_its_batch() -> None:
    # Arrange
    ensure_registered(ExtractedFact, DeclaredNotALeaf)
    nodes = _population()
    batch = next(iter(chunk_node().lineage.sources))

    # Act
    by_layer = {node.content for node in nodes if selects(node, layer_leaf_filter((batch,)))}
    by_store = {node.content for node in nodes if selects(node, leaf_filter())}

    # Assert
    assert by_layer == {chunk_node().content}
    assert by_layer < by_store


def test_the_leaf_definition_loads_without_the_command_line() -> None:
    # Arrange
    probe = "import sys, weft_index.leaves; print('weft_cli' in sys.modules)"

    # Act
    result = subprocess.run(  # noqa: S603 — sys.executable, a literal probe, no shell
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )

    # Assert
    assert result.stdout.strip() == "False"


def test_with_no_model_declaring_itself_not_a_leaf_both_filters_still_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — an install where no registered ext model declares `not_a_leaf`, so the store's
    # selection has one clause. Before this was pinned the suite passed only when an earlier test
    # had registered the graph pack's models, and failed run alone.
    monkeypatch.setattr(leaves_module, "not_a_leaf_namespaces", lambda: ())
    nodes = _population()
    batch = next(iter(chunk_node().lineage.sources))

    # Act
    by_store = {node.content for node in nodes if selects(node, leaf_filter())}
    by_layer = {node.content for node in nodes if selects(node, layer_leaf_filter((batch,)))}

    # Assert
    assert by_store == {
        chunk_node().content,
        f"a chunk of {_ELSEWHERE}",
        "a fact",
        "a stranger's derived node",
    }
    assert by_layer == {chunk_node().content, "a fact", "a stranger's derived node"}
