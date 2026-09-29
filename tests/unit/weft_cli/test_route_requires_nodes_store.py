"""Carried repair **R44.13b** — which node requirements a store satisfies, asked of the store.

A rung's `route.requires-nodes` is satisfied when the store's own `matching` finds one node for
the requirement's filter: the question the rung's retrieval will ask, asked before it is offered.
A store that cannot filter satisfies none, so a rung it could never serve is not offered.
"""

from tests.unit.weft_cli.corpus_build_doubles import GenerationStore
from tests.unit.weft_cli.leaf_selection import chunk_node
from weft_cli.route_ask import satisfied_node_requirements
from weft_index.payload import Representation

_RAPTOR = "ext.weft-index.technique=raptor"
_QUESTIONS = "ext.weft-index.technique=questions"


async def _store_with(*, summary: bool) -> GenerationStore:
    chunk = chunk_node()
    nodes = [chunk]
    if summary:
        nodes.append(
            chunk.derive(content="a summary", ordinal=0).with_ext(
                Representation(technique="raptor")
            )
        )
    store = GenerationStore()
    await store.add(nodes)
    return store


class _UnfilterableStore:
    """A store with no `matching`: it cannot say whether a node exists."""


async def test_a_store_holding_a_matching_node_satisfies_that_requirement_only() -> None:
    # Arrange
    store = await _store_with(summary=True)

    # Act
    satisfied = await satisfied_node_requirements(store, frozenset({_RAPTOR, _QUESTIONS}))

    # Assert
    assert satisfied == frozenset({_RAPTOR})


async def test_a_store_holding_only_leaves_satisfies_none() -> None:
    # Arrange
    store = await _store_with(summary=False)

    # Act
    satisfied = await satisfied_node_requirements(store, frozenset({_RAPTOR}))

    # Assert
    assert satisfied == frozenset()


async def test_a_store_that_cannot_filter_satisfies_none() -> None:
    # Act
    satisfied = await satisfied_node_requirements(_UnfilterableStore(), frozenset({_RAPTOR}))

    # Assert
    assert satisfied == frozenset()


async def test_no_requirement_asks_the_store_nothing() -> None:
    # Act / Assert
    assert await satisfied_node_requirements(_UnfilterableStore(), frozenset()) == frozenset()
