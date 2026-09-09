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

import pytest
from pydantic import ValidationError

from weft_cli.run_services import class_provides
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_kg import GRAPH_ROLE, Settings, register
from weft_kg.contract import Entity, EntityId, GraphTraversal
from weft_kg.store import GraphDsnNotConfiguredError, GraphStore
from weft_kg.traversal import GraphWalk
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
    [resource] = registrar.pipeline_resources
    assert resource.package == "weft_kg"
    assert resource.resource == "pipelines/index-with-graph.yaml"
