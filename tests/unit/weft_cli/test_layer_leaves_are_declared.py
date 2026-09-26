"""Repair **R43.22** — a layer never takes a fact or mention node as a leaf.

Found by Phase 43c's opening audit and confirmed by running the binary: over an
`index-with-facts` base, `weft index --layers enrich-with-questions` derived 48 of its 54
questions from fact and mention nodes, because `weft_cli.layers.layer_leaf_filter` excluded
only nodes carrying `weft_index.payload.Representation`.

An ext model now declares that a node carrying it is not a leaf — `not_a_leaf = True` on the
class, read with `getattr` the way a contract's `layer_stage` is — and the filter excludes every
model registered in `weft_store.rehydrate.ext_models` that declares it. So `weft_cli` names no
pack's model (fitness function 28), and a stranger's model is excluded on the same terms as the
graph pack's. The filter is evaluated by `tests.unit.weft_cli.leaf_selection`.
"""

from tests.unit.weft_cli.leaf_selection import (
    SOURCE,
    DeclaredNotALeaf,
    Undeclared,
    chunk_node,
    ensure_registered,
    selects,
)
from weft_cli.layers import layer_leaf_filter
from weft_index.payload import Representation
from weft_kg.payload import CooccurrenceGraph, ExtractedFact, MentionedEntity
from weft_store.contract import FilterOp
from weft_store.fields import FieldKind, field_for


def test_the_graph_packs_fact_and_mention_models_declare_they_are_not_leaves() -> None:
    # Arrange
    declared = (ExtractedFact, MentionedEntity)

    # Act
    verdicts = {model.__name__: getattr(model, "not_a_leaf", False) for model in declared}

    # Assert
    assert verdicts == {"ExtractedFact": True, "MentionedEntity": True}


def test_the_cooccurrence_graph_rides_on_a_chunk_so_it_does_not_declare_itself_not_a_leaf() -> None:
    # Arrange / Act
    verdict = getattr(CooccurrenceGraph, "not_a_leaf", False)

    # Assert
    assert verdict is False


def test_a_layers_leaves_exclude_fact_and_mention_nodes_and_keep_the_chunk() -> None:
    # Arrange
    ensure_registered(ExtractedFact, MentionedEntity)
    chunk = chunk_node()
    fact = chunk.derive(content="Marie Curie discovered polonium", ordinal=0).with_ext(
        ExtractedFact(
            source="Marie Curie",
            source_type="Person",
            predicate="discovered",
            target="polonium",
            target_type="Element",
        )
    )
    mention = chunk.derive(content="Marie Curie", ordinal=1).with_ext(
        MentionedEntity(name="Marie Curie", entity_type="Person")
    )
    enhanced_chunk = chunk.derive(content="Paris is where she worked.", ordinal=2).with_ext(
        CooccurrenceGraph()
    )
    question = chunk.derive(content="Who discovered polonium?", ordinal=3).with_ext(
        Representation(technique="hypothetical-questions")
    )
    filter = layer_leaf_filter((SOURCE,))

    # Act
    selected = {
        node.content
        for node in (chunk, fact, mention, enhanced_chunk, question)
        if selects(node, filter)
    }

    # Assert
    assert selected == {chunk.content, enhanced_chunk.content}


def test_a_strangers_model_that_declares_itself_not_a_leaf_is_excluded_and_its_twin_is_not() -> (
    None
):
    # Arrange
    ensure_registered(DeclaredNotALeaf, Undeclared)
    chunk = chunk_node()
    declared = chunk.derive(content="a stranger's derived node", ordinal=0).with_ext(
        DeclaredNotALeaf(note="derived")
    )
    undeclared = chunk.derive(content="a stranger's enriched node", ordinal=1).with_ext(
        Undeclared(note="derived")
    )
    filter = layer_leaf_filter((SOURCE,))

    # Act
    selected = {node.content for node in (declared, undeclared) if selects(node, filter)}

    # Assert
    assert selected == {undeclared.content}


def test_every_field_the_selection_names_is_one_a_store_can_address() -> None:
    # Arrange
    ensure_registered(ExtractedFact, MentionedEntity, DeclaredNotALeaf)
    filter = layer_leaf_filter((SOURCE,))
    pending = [filter]
    fields: list[tuple[FilterOp, str]] = []
    while pending:
        current = pending.pop()
        pending.extend(current.clauses)
        if current.field is not None:
            fields.append((current.op, current.field))

    # Act
    kinds = {field: field_for(op, field).kind for op, field in fields}

    # Assert
    assert kinds["lineage.sources"] is FieldKind.TEXT_SET
    assert any(field.startswith("ext.weft-kg-fact.") for field in kinds)
    assert any(field.startswith("ext.weft-kg-mention.") for field in kinds)
