"""Writing a store plugin needs no Docker — ledger task **26.6**.

`01` → *Runtime shape* has required this since Phase 0 and no ledger task ever owned it:

> **An ephemeral in-memory store exists, and is not a backend.** A dict with brute-force cosine,
> never persisted, used by the conformance kit and by pack authors' unit tests so writing a plugin
> does not require Docker. It forgets everything on exit, deliberately, so nobody deploys on it and
> there is no migration path to fight.

`07` §2's canonical-four table already promises it — file 4 is *"the pack's own tests, against the
conformance kit and the ephemeral in-memory store"* — and carried repair `R19.5` records that
neither existed. `26.4` published the kit; this is the other half, and without it the kit a
stranger can now import still needs two containers before it will say anything.

**`NodeStore` and `VectorSearch`, and not `MetadataFilter`.** Settled by the owner 2026-09-13 on a
measurement: no in-Python filter evaluator exists anywhere in the tree — pgvector translates a
`Filter` to SQL and Qdrant to its own filter language — so `matching` would mean writing a third
evaluator from scratch and keeping it correct against two others. `01` asks this store for a dict
and brute-force cosine, which is exactly `NodeStore` plus `VectorSearch`. Task `26.5`'s selector is
what makes that a first-class store rather than a failing one: it is offered the checks it can
answer and told which it cannot, with the capability each needs.

**Not a backend, and the tests below are where that is enforced rather than asserted in prose.** It
holds no connection, writes no file, and forgetting everything when the process ends is the
property — a store somebody could deploy on is the failure mode, not a missing feature.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest

from weft_kernel.payload import MediaType, Node, SourceId, Vector
from weft_store.contract import STORE_CONTRACT_VERSION, SourceRecord


def _node(content: str, vector: tuple[float, ...], source: str = "s-a") -> Node:
    """Built the way the published kit builds its own — `Node.synthetic` then `with_embedding`,
    because `synthetic` takes no `embedding` and a double written from the signature I expected
    rather than the one that exists is `L11.17`."""
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="memory store test",
        sources=frozenset({SourceId(source)}),
    ).with_embedding(Vector(values=vector))


async def _failure_of(check: Callable[..., Awaitable[None]], store: object) -> str | None:
    """`None` when `check` passes against `store`, else the message it refused with.

    A helper rather than a `try` inside the loop below, so one failing check does not hide the
    next — the whole point of running a conformance suite is the *set* that disagreed.
    """
    try:
        await check(store)
    except AssertionError as exc:
        return f"{check.__name__}: {exc}"
    return None


async def test_a_node_survives_a_round_trip_through_memory() -> None:
    """The happy path: it is a store before it is anything else."""
    # Arrange
    from weft_store.memory import MemoryStore

    store = MemoryStore()
    node = _node("alpha", (1.0, 0.0, 0.0))

    # Act
    await store.add([node])
    await store.flush()
    found = await store.get([node.id])

    # Assert
    assert len(found) == 1
    assert found[0].content == "alpha"
    assert await store.count() == 1


async def test_brute_force_cosine_ranks_the_nearest_vector_first() -> None:
    """`01` names *brute-force cosine*, so the ranking is the property rather than an incidental.

    Three vectors, not two: with two, a ranking that reverses and one that is correct are
    distinguishable only by which end you read, and any comparator returning a constant orders two
    items consistently. The middle vector is what makes the order a fact.
    """
    # Arrange
    from weft_store.memory import MemoryStore

    store = MemoryStore()
    near = _node("near", (1.0, 0.0, 0.0))
    middle = _node("middle", (0.7, 0.7, 0.0))
    far = _node("far", (0.0, 1.0, 0.0))
    await store.add([far, middle, near])
    await store.flush()

    # Act
    ranked = await store.search_vector(Vector(values=(1.0, 0.0, 0.0)), top_k=3)

    # Assert
    assert [scored.value.content for scored in ranked] == ["near", "middle", "far"]
    assert ranked[0].score > ranked[1].score > ranked[2].score


async def test_it_answers_the_conformance_checks_its_capabilities_cover() -> None:
    """The point of building it: the published kit runs against it with no container anywhere.

    Driven through `checks_for`, which is `26.5`'s seam — so this asserts the two halves of the
    phase compose, which is the conjunction `L8.29` says to check first and which neither task's
    own tests could show.
    """
    # Arrange
    from weft_store.conformance import checks_for, register_conformance_ext_models
    from weft_store.memory import MemoryStore

    register_conformance_ext_models()
    offered = [
        check
        for check in checks_for(MemoryStore())
        if "label" not in check.__code__.co_varnames[: check.__code__.co_argcount]
    ]

    # Act — a fresh store per check, because the kit owns no lifecycle (`26.4`'s own rule).
    failures = [f for check in offered if (f := await _failure_of(check, MemoryStore()))]

    # Assert
    assert offered, "the kit offered this store nothing, so this comparison is vacuous"
    assert not failures, "\n".join(failures)


async def test_it_is_told_which_checks_it_cannot_answer_rather_than_failing_them() -> None:
    """The control for the test above. A store offered *every* check would satisfy that assertion
    only by accident, and this is what says the selection actually happened.
    """
    # Arrange
    from weft_store.conformance import unsupported_checks
    from weft_store.memory import MemoryStore

    # Act
    skipped = {capability for _check, capability in unsupported_checks(MemoryStore())}

    # Assert — the two it deliberately does not have, and not the one it does.
    assert {"MetadataFilter", "Reconcilable"} <= skipped
    assert "VectorSearch" not in skipped


async def test_two_stores_share_nothing_so_a_pack_authors_tests_cannot_leak() -> None:
    """The edge case, and the reason it is *ephemeral* rather than merely *in memory*.

    A module-level dict would pass every test above and quietly join two test cases together — the
    defect that makes an in-memory double worse than no double, because it then fails
    intermittently in somebody else's suite.
    """
    # Arrange
    from weft_store.memory import MemoryStore

    first, second = MemoryStore(), MemoryStore()

    # Act
    await first.add([_node("only in the first", (1.0, 0.0, 0.0))])
    await first.flush()

    # Assert
    assert await first.count() == 1
    assert await second.count() == 0


async def test_a_source_record_round_trips_and_deleting_it_takes_its_nodes() -> None:
    """The base contract's other half, which `search_vector` would otherwise hide."""
    # Arrange
    from weft_store.memory import MemoryStore

    store = MemoryStore()
    await store.add(
        [
            _node("kept", (1.0, 0.0, 0.0), source="s-keep"),
            _node("doomed", (0.0, 1.0, 0.0), source="s-drop"),
        ]
    )
    await store.put_source(
        SourceRecord(
            id=SourceId("s-drop"),
            uri="file:///drop.txt",
            content_hash="h",
            indexed_at=datetime(2026, 9, 13, tzinfo=UTC),
            pipeline="index-text",
        )
    )

    # Act
    removed = await store.delete_source(SourceId("s-drop"))

    # Assert
    assert removed.node_count == 1
    assert await store.count() == 1
    assert await store.get_source(SourceId("s-drop")) is None


def test_it_declares_the_contract_version_it_was_written_against() -> None:
    """A store that does not say which contract it satisfies cannot be checked against a
    later one."""
    from weft_store.memory import MemoryStore

    assert MemoryStore.version == STORE_CONTRACT_VERSION


async def test_it_refuses_a_query_vector_of_the_wrong_width() -> None:
    """The error case. Cosine over mismatched widths is either a crash or a silent lie depending on
    how it is written, and a store that answers anyway is the plausible-wrong-answer failure.
    """
    # Arrange
    from weft_store.memory import MemoryStore

    store = MemoryStore()
    await store.add([_node("three wide", (1.0, 0.0, 0.0))])

    # Act / Assert
    with pytest.raises(ValueError, match="width"):
        await store.search_vector(Vector(values=(1.0, 0.0)), top_k=1)
