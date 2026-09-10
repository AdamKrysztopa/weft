"""`weft_kg` registers the way every other pack does. Ledger task **11.5**.

Mirrors `packages/weft-rag/src/weft_kg/__init__.py`. `11.4` published the traversal contract and
deliberately registered nothing; this is the task where the pack becomes an *installed*, reachable
thing — one `weft.packs` entry point, its own `[packs.graph]` namespace, its own `plugins doctor`
row, and nothing it receives that a third party's pack does not.

**Two plugin names for one capability, and the reason is two separate rules pulling opposite
ways.** Fitness function 18 forbids one name under two contracts — `weft_cli.compile._contract_for`
scans every registered contract for a document's `use:` name and refuses when more than one
answers, so such a plugin is registered, listed, and placeable by nobody. And `[services] graph`
resolves through `registry.entry(GraphTraversal, <name>)` (`weft_cli.run_services.
selected_role_instances`), so a registration under `GraphTraversal` is exactly what makes the role
selectable. Two names it is, and they are qualified rather than bare, per `10` §2.1 rule 6: the
family-membership deferral in `01` names `weft-neo4j` as the sibling this pack is waiting for, so
`graph` unqualified would be the first implementation seizing the namespace.

**Two *classes*, though, and that is a finding rather than a style.** `weft_cli.fanout.
participants_for` narrows `NodeStore` to `store_names` with `if contract is NodeStore` and then
deduplicates participants **by class**, walking contracts in `__qualname__` order. One class
registered under both `GraphTraversal` and `NodeStore` is therefore reached as a `GraphTraversal`
first — `G` sorts before `N` — joins the fan-out there, and has its `NodeStore` registration
dropped as a duplicate, so the store filter never runs and the pack participates in every project
whether or not anything names it. `docs/lessons.md` `L11.23`. `GraphStore` and `GraphWalk` are two
classes over one schema, which keeps that shape out of the tree.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest
from pydantic import ValidationError

from weft_cli.pipeline_catalogue import load_pipeline_document
from weft_cli.run_services import class_provides
from weft_enhance.contract import Enhancer
from weft_index.contract import Expander
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_kg import GRAPH_ROLE, Settings, register
from weft_kg.contract import Entity, EntityId, GraphTraversal
from weft_kg.payload import (
    CooccurrenceGraph,
    ExtractedFact,
    ExtractionTally,
    MentionedEntity,
)
from weft_kg.prompts import ADJUDICATE_ENTITIES_NAME, EXTRACT_FACTS_NAME
from weft_kg.retrieval import NAME as GRAPH_WALK_NAME
from weft_kg.store import GraphDsnNotConfiguredError, GraphStore
from weft_kg.traversal import GraphWalk
from weft_prompts.contract import Prompt
from weft_retrieve.contract import Retriever
from weft_store.contract import NodeStore, Reconcilable, SourceDeletable


def _registered() -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")
    register(registrar, Settings())
    registrar.commit()
    return registry


def test_register_adds_the_store_under_node_store() -> None:
    # Act
    registry = _registered()

    # Assert — the name a document's store stage writes, and the distribution it came from.
    entry = registry.entry(NodeStore, "pgvector-graph")
    assert entry.distribution == "weft-rag"


def test_register_adds_the_walk_under_the_traversal_protocol() -> None:
    """The registration `[services] graph = "pgvector-traversal"` resolves through.

    `weft_cli.run_services.selected_role_instances` builds a role with
    `registry.entry(role.contract, services.roles[key]).factory(None)`, so a role is selectable
    only where something registered a name under that role's own contract.
    """
    # Act
    registry = _registered()

    # Assert
    entry = registry.entry(GraphTraversal, "pgvector-traversal")
    assert entry.distribution == "weft-rag"


def test_the_two_registrations_are_two_classes() -> None:
    """`L11.23`: one class under both contracts escapes the fan-out's `NodeStore` filter.

    Asserted against the registry rather than against the modules, because what
    `weft_cli.fanout.participants_for` deduplicates is the registered *class* — the thing this
    test has to be about is what a fan-out would find, not what the source files look like.
    """
    # Act
    registry = _registered()

    # Assert
    store = registry.entry(NodeStore, "pgvector-graph").factory
    walk = registry.entry(GraphTraversal, "pgvector-traversal").factory
    assert store is not walk


def test_no_name_answers_to_both_contracts() -> None:
    """Fitness function 18's property, asserted here as well because this is the pack that made
    it a live question: a name under two contracts cannot be selected by a document at all.
    """
    # Act
    registry = _registered()

    # Assert
    assert registry.names_for(NodeStore).isdisjoint(registry.names_for(GraphTraversal))


def test_the_pack_declares_the_graph_service_role() -> None:
    """`[services] graph` exists because this pack declares it, with no kernel line — ledger
    `9.0`'s form, and `weft_kernel.discovery._read_service_roles` reads `SERVICE_ROLES` off the
    module at import, before settings are validated.
    """
    # Arrange
    import weft_kg

    # Assert
    assert weft_kg.SERVICE_ROLES == (GRAPH_ROLE,)
    assert GRAPH_ROLE.key == "graph"
    assert GRAPH_ROLE.contract is GraphTraversal


def test_the_pack_discloses_the_database_it_reaches() -> None:
    """`02` §2: a disclosure carries a concrete string an operator can act on, never a boolean.

    The setting is named, never its value — `dsn` is a `SecretStr` and the credential inside it
    is not this pack's to print.
    """
    # Arrange
    import weft_kg

    # Assert
    assert weft_kg.DISCLOSURE.network
    assert any("[packs.graph] dsn" in reach for reach in weft_kg.DISCLOSURE.network)
    assert weft_kg.DISCLOSURE.subprocess == ()


def test_register_opens_no_connection_with_no_settings_at_all() -> None:
    """`[packs.graph] dsn` is optional, and `register()` must run on a machine with no `weft.toml`.

    `weft-store`'s `dsn` is mandatory, so that pack reports `FAILED` where none is configured —
    correct for the store an operator is *required* to configure. The graph store is not that: a
    project that never names it should see an ordinary `active` row, not a failure it has to read
    past. So the default is empty and the refusal moves to the first call that genuinely needs a
    connection, which is what `test_a_call_needing_a_connection_names_the_setting` asserts.
    """
    # Act — a bare `Settings()`, exactly what discovery hands a pack with no `[packs.graph]` table.
    registry = _registered()

    # Assert — built, not merely registered: constructing must not dial anything either.
    instance = registry.entry(NodeStore, "pgvector-graph").factory(None)
    assert isinstance(instance, GraphStore)
    walk = registry.entry(GraphTraversal, "pgvector-traversal").factory(None)
    assert isinstance(walk, GraphWalk)


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})


def test_the_store_satisfies_the_three_contracts_it_registers_and_fans_out_under() -> None:
    """Structural, on the class — the same question `weft_cli.fanout.participants_for` asks.

    That function checks `issubclass` against the registered *class*, never a constructed
    instance, so nothing is built to find out whether it should have been.

    **Here rather than in `test_store.py`**, which is skipped whole when the container is down:
    this asks nothing of a database, and a check that stops reporting whenever Postgres is
    stopped is a check that reports on the days it is least needed (`L11.22`).
    """
    # Assert — through `class_provides`, which is `weft_cli.run_services`' own wrapper around
    # `issubclass` and the function the fan-out actually calls. A bare `issubclass` against a
    # Protocol carrying a non-method `version` is what a type checker refuses, and reaching for
    # the tree's existing helper is what `L11.17` asks for instead of writing a second one.
    assert class_provides(GraphStore, NodeStore)
    assert class_provides(GraphStore, SourceDeletable)
    assert class_provides(GraphStore, Reconcilable)


def test_the_walk_satisfies_the_traversal_contract_and_is_not_a_node_store() -> None:
    """`L11.23`: the two capabilities are two classes precisely so that the fan-out's
    `NodeStore` filter cannot be escaped by whichever contract sorts first.
    """
    # Assert
    assert class_provides(GraphWalk, GraphTraversal)
    assert not class_provides(GraphWalk, NodeStore)


def test_the_entity_model_the_walk_answers_with_carries_two_fields() -> None:
    """`11.4` fixed `Entity` at `id` and `name` so `11.8` stays free to design the table.

    Asserted here as well as at `11.4` because this is the task where a real backend fills the
    model, and a store is exactly the place a storage-shaped third field would arrive from.
    """
    # Assert
    assert set(Entity.model_fields) == {"id", "name"}
    assert Entity(id=EntityId("e1"), name="x").id == EntityId("e1")


async def test_a_call_needing_a_connection_names_the_setting_when_the_dsn_is_unset() -> None:
    """The error case, and it needs no container: `register()` must succeed with no settings at
    all, so the refusal lands at the first call that genuinely dials.

    It names `[packs.graph] dsn` and the environment variable an operator most likely already
    has, because a refusal an operator cannot act on is a crash with better manners.
    """
    # Arrange — a bare `Settings()`, exactly what discovery hands a pack with no config.
    instance = GraphStore(Settings())

    # Act / Assert
    with pytest.raises(GraphDsnNotConfiguredError) as raised:
        await instance.count()
    assert "[packs.graph] dsn" in str(raised.value)
    assert "WEFT_DATABASE_URL" in str(raised.value)


def test_register_adds_the_cooccurrence_builder_under_enhancer() -> None:
    """Ledger `11.6` — the no-model rung's one new stage, registered like any other."""
    # Act
    registry = _registered()

    # Assert
    entry = registry.entry(Enhancer, "cooccurrence-graph")
    assert entry.distribution == "weft-rag"


def test_the_pack_declares_its_ext_model_for_rehydration() -> None:
    """Fitness function 14's property, asserted at the pack: a node carrying this pack's ext data
    survives a round trip through *any* store, because `register()` told the shared registry the
    namespace exists. A model declared and never registered comes back as a bare mapping and the
    only symptom is a downstream `AttributeError`.
    """
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    assert CooccurrenceGraph in registrar.ext_models


def test_the_pack_contributes_the_document_that_makes_its_store_reachable() -> None:
    """Fitness function 16's subject: `NodeStore` inherits `Stage`, so a registered store is a
    pipeline position, and a position no shipped document names is a rung with no floor.

    The document is `index-with-graph` — `index-text` with the graph store inserted after the
    ordinary one, which is `02` §4's own *"sits beside the vector store"* written as data.
    """
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")

    # Act — `PackRegistrar.commit` returns `None`; `pipeline_resources` is a property on the
    # registrar itself, which is how `tests/unit/weft_kernel/test_discovery.py` reads it.
    register(registrar, Settings())
    registrar.commit()

    # Assert
    assert [(r.package, r.resource) for r in registrar.pipeline_resources] == [
        ("weft_kg", "pipelines/index-with-graph.yaml"),
        ("weft_kg", "pipelines/index-with-cooccurrence.yaml"),
        ("weft_kg", "pipelines/index-with-facts.yaml"),
        ("weft_kg", "pipelines/graph-then-generate.yaml"),
        ("weft_kg", "pipelines/graph-2hop-then-generate.yaml"),
        ("weft_kg", "pipelines/graph-and-vector-rrf.yaml"),
        ("weft_kg", "pipelines/graph-then-rerank.yaml"),
        ("weft_kg", "pipelines/index-with-facts-openai.yaml"),
    ]


def test_the_pack_ships_a_rung_whose_entity_vectors_a_resolution_pass_can_use() -> None:
    """Carried repair **`R11.5`**, and it is a rung decision rather than a defect.

    `index-with-facts` extends `index-with-graph` extends `index-text`, and `index-text` names
    `embed: hash`. A `--pipeline` run deliberately does not read `[services] embed` — `run_index`'s
    own *"Q3, settled"*, and the right rule, because a document that says `hash` must not silently
    become `openai` because a file elsewhere said so. The consequence measured at `11.9`: every
    alias vector on the shipped rung is a content hash, so `11.8`'s blended score collapses to its
    lexical third and the entity-resolution pass the phase built has no rung on which its vector
    term means anything.

    This rung is the other end of that: one `replace:` block naming a real embedder, so the pass
    is reachable without an operator deriving a document by hand first. The credential requirement
    is the cost, stated on the document itself — `index-openai`'s own precedent, one family over.
    """
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    assert ("weft_kg", "pipelines/index-with-facts-openai.yaml") in [
        (r.package, r.resource) for r in registrar.pipeline_resources
    ]


# --- ledger task 11.7: the model-calling rung --------------------------------------------


def test_register_adds_the_fact_extractor_under_expander() -> None:
    """`llm-facts` is an `Expander` — every node handed in continues and facts are added beside
    it — registered exactly the way `weft_index`'s two already are, from a different pack.
    """
    # Act
    registry = _registered()

    # Assert
    entry = registry.entry(Expander, "llm-facts")
    assert entry.distribution == "weft-rag"


def test_register_adds_the_extraction_prompt_under_its_own_name() -> None:
    """The text this pack sends to a provider is a listed, versioned, translatable plugin.

    It is registered even though `weft_kg.extraction` constructs the class directly: this is the
    stage whose `Disclosure` says chunk content leaves the machine, and the prompt is the only
    artefact that says *what leaves*. Hiding it from `weft plugins list` and from
    `manual/contract-reference.md` to avoid one wart would trade a documented limitation for an
    undocumented one. The wart, stated where a reader meets it: a `[plugins]` pin on this name
    changes the listing and does not change what the stage asks, because the ingest path
    publishes no by-name capability lookup (`weft_cli.run_services.build_index_services`).
    """
    # Act
    registry = _registered()

    # Assert
    entry = registry.entry(Prompt, EXTRACT_FACTS_NAME)
    assert entry.distribution == "weft-rag"


def test_the_question_the_expensive_pass_asks_is_registered_under_its_own_name() -> None:
    """Ledger **11.9** — the same argument `extract-facts` makes one task over, for the second
    text this pack sends to a provider.

    `GraphStore.reconcile` constructs `AdjudicateEntitiesPrompt` directly, for the identical
    reason `llm-facts` constructs its own: a reconcile pass is not a pipeline stage and reaches
    no `StageLookup`. It is registered anyway, because this pack's `Disclosure` says two surface
    forms leave the machine under `full` and this class is the only artefact that says *how they
    are asked about* — an unregistered prompt would put that text out of reach of
    `weft plugins list` and of `manual/contract-reference.md` alike. The same wart applies and
    is stated in `weft_kg.prompts`: a `[plugins]` pin on this name changes the listing and does
    not change what the pass asks.
    """
    # Act
    registry = _registered()

    # Assert
    entry = registry.entry(Prompt, ADJUDICATE_ENTITIES_NAME)
    assert entry.distribution == "weft-rag"


def test_the_pack_declares_every_ext_model_it_writes() -> None:
    """Fitness function 14's property at the pack: a model declared and never registered comes
    back off a store as a bare mapping, and the only symptom is a downstream `AttributeError`.

    All four, in one assertion, so a fifth model added without its registration fails here —
    which is the shape a per-model test cannot have.
    """
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    assert set(registrar.ext_models) >= {
        CooccurrenceGraph,
        ExtractedFact,
        MentionedEntity,
        ExtractionTally,
    }


def test_the_pack_discloses_that_chunk_content_leaves_through_the_configured_provider() -> None:
    """`11.7`'s own line: documented, never derived.

    Egress is a property of the *selected provider*, not of this pack — `weft_llm/scripted.py`
    makes no call at all — so no import rule and no static check can answer it here. The import
    rule already catches a provider pack (`tests/architecture/test_network_packs_disclose.py`);
    what it cannot say is that a stage in *this* pack hands a chunk's text to whichever provider
    `[llm.roles]` names. A `Disclosure.note` is exactly the seam `02` §2 provides for a fact an
    operator must be told and the kernel cannot check.
    """
    # Arrange
    import weft_kg

    # Assert
    note = weft_kg.DISCLOSURE.note
    assert "llm-facts" in note
    assert "provider" in note


def test_the_model_calling_stage_is_inserted_before_the_embedder() -> None:
    """Ledger `8.2`/`8.10`'s rule, and the one arrangement fact this document has to get right:
    **a model-calling stage placed after `embed` produces nodes that are stored unsearchable.**

    Checked from two independently edited sources, so the comparison can actually disagree
    (`docs/lessons.md` L5.6): the child says which stage id it anchors to, and `index-text` —
    a different pack's document — says where that id sits relative to `embed`. Asserting the
    anchor alone would pass on a parent that had since moved `chunk` after `embed`.

    `extends: index-with-graph` rather than `index-text`, on `index-with-cooccurrence`'s own
    footing: the graph store stage this rung needs already exists one document down, and `02` §3's
    derivation model is that a rung is one operator block on top of a rung that already exists,
    never a fresh copy of its ancestor's stage list.
    """
    # Arrange — the shipped resources, read through the real parser.
    child = load_pipeline_document(
        Path(str(resources.files("weft_kg").joinpath("pipelines/index-with-facts.yaml")))
    )
    root = load_pipeline_document(
        Path(str(resources.files("weft_retrieve").joinpath("pipelines/index-text.yaml")))
    )

    # Act
    [inserted] = [operator for operator in child.insert if operator.stage.use == "llm-facts"]
    order = [stage.id for stage in root.stages]

    # Assert
    assert child.extends == "index-with-graph"
    assert inserted.after is not None, "the stage is anchored to nothing, so it lands at the top"
    assert order.index(inserted.after) < order.index("embed")


# --- ledger task 11.10: the query side, and the four rungs that make it reachable ---------


def test_the_pack_registers_its_retriever_under_the_query_path_contract() -> None:
    """`weft_kg` becomes a query-path pack here, and that is what widens fitness function 16's
    scope over it: FF16's subject is every plugin a *pipeline-shipping* distribution registers
    into a pipeline position, and `Retriever` is one. From this registration, a `graph-walk`
    no shipped document names is a rung with no floor and FF16 goes red — which is exactly the
    property `11.10`'s line asks for, so the four documents below are not decoration.
    """
    # Act
    registry = _registered()

    # Assert
    entry = registry.entry(Retriever, GRAPH_WALK_NAME)
    assert entry.distribution == "weft-rag"


def test_every_rung_the_pack_ships_names_the_retriever_it_was_written_for() -> None:
    """Read out of the shipped documents rather than asserted as a list here, so a rung renamed
    or a `replace:` block edited fails at this test rather than at FF16's whole-tree sweep,
    where the message names a pair and not a file.

    `graph-2hop-then-generate` deliberately does **not** appear: it inherits the retriever from
    its parent and changes one number, which is the whole demonstration of requirement 6 — a
    rung that re-declared `use:` would be a copy of its parent rather than a parameterisation
    of it.
    """
    # Arrange
    from importlib import resources

    from weft_cli.pipeline_catalogue import load_pipeline_document

    # Act
    named: dict[str, set[str]] = {}
    for resource in ("graph-then-generate", "graph-and-vector-rrf", "graph-then-rerank"):
        path = Path(str(resources.files("weft_kg").joinpath(f"pipelines/{resource}.yaml")))
        document = load_pipeline_document(path)
        named[resource] = {
            *(stage.use for stage in document.stages),
            *(operator.use for operator in document.replace),
            *(inserted.stage.use for inserted in document.insert),
        }

    # Assert
    assert GRAPH_WALK_NAME in named["graph-then-generate"]
    assert "multi-retriever" in named["graph-and-vector-rrf"]
    # `graph-then-rerank` names no retriever at all: it extends `graph-then-generate` and only
    # inserts a reranker, which is `11.1`'s property read forwards — a fact is a node, so
    # `llm-rerank` works on one with no new code.
    assert "llm-rerank" in named["graph-then-rerank"]
    assert GRAPH_WALK_NAME not in named["graph-then-rerank"]


def test_the_two_hop_rung_parameterises_rather_than_replaces() -> None:
    """Requirement 6, as a fact about the document: `set:` changes a number on an inherited
    stage; `replace:` would change the plugin. The ledger line names `set:` for this rung, and
    the difference is what makes the pair a demonstration rather than two similar files.
    """
    # Arrange
    from importlib import resources

    from weft_cli.pipeline_catalogue import load_pipeline_document

    # Act
    path = Path(str(resources.files("weft_kg").joinpath("pipelines/graph-2hop-then-generate.yaml")))
    document = load_pipeline_document(path)

    # Assert
    assert document.extends == "graph-then-generate"
    assert document.replace == ()
    assert any(operator.id == "retrieve" for operator in document.set)
