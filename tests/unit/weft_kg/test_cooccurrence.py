"""`cooccurrence-graph` — entities and edges from a chunk's own text, no model. Ledger **11.6**.

Mirrors `packages/weft-rag/src/weft_kg/cooccurrence.py` and `weft_kg/payload.py`.

**The name, settled before the code, through `paper-to-plugin` and `10` §2.1.** There is **no
paper**: building a co-occurrence graph out of capitalised runs is ordinary practice with no work
that introduced or named it, and `10` §5 records that as a finding rather than an invented
provenance. So the name states the mechanism (rule 2) and is qualified against the sibling this
phase already has scheduled — `11.7`'s model-backed extractor (rule 6). It is deliberately **not**
`ner` or `named-entities`, which would be rule 4's overclaim with teeth: this is a regular
expression over capitalisation, and a practitioner who searched for named-entity recognition and
landed here would have been misled. None of `10` §4's reserved graph names — `grag`, `hipporag`,
`g-retriever`, `t-retriever`, `archrag` — is taken.

**What it is honest about.** Title-Case runs over-generate (a sentence-initial capitalised word that
names nothing) and under-generate (a lower-cased acronym, or a name split across a chunk boundary).
That is stated on the class, where `tests/docs/test_technique_naming.py` can see it, rather than
left for a reader to discover by running it on a real corpus.

**Why an `Enhancer` and not an `Extractor`.** It adds a fact *to* a node and never rewrites
`content`, so node identity is untouched — `weft_enhance.contract.Enhancer`'s own contrast with
`Cleaner`. The graph rows are not written here either: the enhancer attaches ext data, and
`GraphStore.add` derives entity and relation rows from it when the node is stored. That keeps the
stage free of any store access at all, which is what lets it run in a pipeline that has no graph
store configured without failing — it simply attaches a fact nothing reads.

**No entity vectors here.** `01` → Phase 11 says entity-name vectors are written by the pipeline's
embedder *"where a rung wants them"*, and this rung does not: the `hash` embedder embeds nodes, not
entity names, and giving this stage an embedder would make the one rung a laptop can climb need a
service it is defined by not needing. `kg_entities.embedding` stays unwritten until a rung asks.
"""

from __future__ import annotations

import pytest

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Produced, SourceId
from weft_kg.cooccurrence import CooccurrenceGraphBuilder, CooccurrenceSettings
from weft_kg.payload import CooccurrenceGraph


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="weft_kg's own co-occurrence test",
        sources=frozenset({SourceId("doc-a")}),
    )


async def _graph_of(
    content: str, *, config: CooccurrenceSettings | None = None
) -> CooccurrenceGraph:
    outcome = await CooccurrenceGraphBuilder(config).run([_node(content)], _ctx())
    assert isinstance(outcome, Produced)
    [node] = outcome.value
    found = node.ext_as(CooccurrenceGraph)
    assert found is not None
    return found


async def test_capitalised_runs_become_entities() -> None:
    # Arrange / Act — two multi-word names and one single-word one, in ordinary prose.
    graph = await _graph_of("Chucri and Azouz measured New York City traffic.")

    # Assert — the fact the field means: which names this chunk mentions.
    assert {entity.name for entity in graph.entities} == {"Chucri", "Azouz", "New York City"}


async def test_a_word_capitalised_only_because_it_opens_a_sentence_is_not_an_entity() -> None:
    """The over-generation this heuristic is most prone to, and the one filter worth having.

    Without it every node in a corpus mentions `The`, and a graph whose densest entity is a
    determiner is worse than no graph: it is a plausible answer against the wrong data.
    """
    # Act
    graph = await _graph_of("The corpus mentions Chucri. This matters.")

    # Assert
    assert {entity.name for entity in graph.entities} == {"Chucri"}


async def test_every_pair_in_one_chunk_co_occurs_in_a_canonical_order() -> None:
    """Co-occurrence is the whole edge rule: same chunk, therefore related, direction unknown.

    `source < target` lexicographically is the canonical spelling, so one pair is never stored
    twice under swapped endpoints — the invariant the store's own upsert depends on.
    """
    # Act
    graph = await _graph_of("Azouz and Chucri wrote about adRAP with Ott.")

    # Assert — three names, so three unordered pairs, each written low-to-high.
    pairs = {(edge.source, edge.target) for edge in graph.relations}
    assert pairs == {("Azouz", "Chucri"), ("Azouz", "Ott"), ("Chucri", "Ott")}
    assert all(edge.source < edge.target for edge in graph.relations)


async def test_a_chunk_mentioning_one_name_has_no_relations() -> None:
    """A co-occurrence needs two things to co-occur, and an edge to itself is not a fact."""
    # Act
    graph = await _graph_of("Chucri wrote it alone.")

    # Assert
    assert {entity.name for entity in graph.entities} == {"Chucri"}
    assert graph.relations == ()


async def test_a_chunk_with_no_names_still_carries_an_empty_graph() -> None:
    """An empty *result* is a real, attachable fact; only an empty *batch* is nothing to produce.

    The distinction matters downstream: a node carrying an empty `CooccurrenceGraph` has been
    looked at and holds no names, while a node carrying none was never enhanced at all, and a
    later pass has to be able to tell those apart.
    """
    # Act
    graph = await _graph_of("nothing here is capitalised at all")

    # Assert
    assert graph.entities == ()
    assert graph.relations == ()


async def test_an_empty_batch_produces_nothing() -> None:
    # Act
    outcome = await CooccurrenceGraphBuilder().run([], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_the_stage_never_rewrites_content() -> None:
    """`Enhancer`'s own contrast with `Cleaner`: it adds a fact, so node identity is untouched.

    Asserted on the id rather than on the text, because the id is what a citation, a lineage and
    a store row all key on — a rewritten `content` would silently orphan every one of them.
    """
    # Arrange
    node = _node("Chucri and Azouz wrote about adRAP.")

    # Act
    outcome = await CooccurrenceGraphBuilder().run([node], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    [enhanced] = outcome.value
    assert enhanced.id == node.id
    assert enhanced.content == node.content


async def test_a_repeated_name_is_counted_rather_than_repeated() -> None:
    """One entity per name per chunk, carrying how often it occurred.

    A list with the same name three times would make every downstream count a function of how
    the caller deduplicated rather than of the text.
    """
    # Act
    graph = await _graph_of("Chucri wrote it. Chucri revised it. Azouz read it.")

    # Assert
    counts = {entity.name: entity.count for entity in graph.entities}
    assert counts == {"Chucri": 2, "Azouz": 1}


async def test_the_run_length_is_a_configuration_field() -> None:
    """Requirement 6: shipped technique is parameterisable, and this is the one number the
    heuristic actually turns on. At `max_name_words=1` a multi-word name becomes its parts.
    """
    # Act
    narrow = await _graph_of(
        "New York City matters.", config=CooccurrenceSettings(max_name_words=1)
    )
    wide = await _graph_of("New York City matters.", config=CooccurrenceSettings(max_name_words=3))

    # Assert — the control disagrees with the subject, so the field is proven to do something.
    assert {entity.name for entity in narrow.entities} == {"New", "York", "City"}
    assert {entity.name for entity in wide.entities} == {"New York City"}


async def test_the_minimum_mention_count_drops_a_name_below_it() -> None:
    """The other knob: a corpus of prose throws off single capitalised words constantly, and an
    operator who wants only repeated names says so rather than editing a stopword list.
    """
    # Act
    graph = await _graph_of(
        "Chucri wrote it. Chucri revised it. Azouz read it.",
        config=CooccurrenceSettings(min_mentions=2),
    )

    # Assert
    assert {entity.name for entity in graph.entities} == {"Chucri"}
    assert graph.relations == ()


async def test_the_ext_model_declares_the_namespace_and_schema_version() -> None:
    """`02` §1: a pack's ext data is namespaced by the pack, and carries its own schema version —
    G9's second axis, a fact about a schema in somebody's database rather than about a contract.
    """
    # Assert
    assert CooccurrenceGraph.__namespace__ == "weft-kg"
    assert CooccurrenceGraph.__schema_version__ == "1.0.0"


async def test_the_ext_model_carries_no_field_named_technique() -> None:
    """`11.1`'s constraint, honoured one task early because this is the first `weft_kg` ext model.

    `weft_generate.representation.citable_nodes` cites a single-parent node carrying an ext model
    with a `technique: str` attribute **as its parent**, so a field of that name here would make
    anything derived from these nodes cite the chunk instead of itself, and nothing would report
    it. The constraint is `11.7`'s to honour for fact nodes; asserting it here is what stops the
    name entering the pack's vocabulary in the first place.
    """
    # Assert
    assert "technique" not in CooccurrenceGraph.model_fields


@pytest.mark.parametrize("bad", [0, -1])
async def test_a_run_length_below_one_is_refused(bad: int) -> None:
    """A loud refusal, not a silent clamp: `max_name_words=0` can only mean a mistake, and a
    stage that quietly repaired it would produce an empty graph an operator would have to
    diagnose from the absence of results.
    """
    # Act / Assert
    with pytest.raises(ValueError, match="max_name_words"):
        CooccurrenceSettings(max_name_words=bad)
