"""Unit tests for exact-key aliasing by demand — ledger task 9.0, **property (ii)**, alone.

Property (i) is `test_service_roles.py`; property (iii) is
`test_service_role_needs_store.py`. The task line requires each to be tested without the
others standing in for it, because they fail independently: a role can be selected correctly
and still be unreachable, and it can be reachable under one contract and refused under the
capability a stage actually demands of it.

**What makes this property necessary at all.** `weft_kernel.context.ServiceRegistry` keys by
**exact type** (`packages/weft-kernel/src/weft_kernel/context.py:105`; `add` at `:119`,
`resolve` at `:133`), so an instance registered under `NodeStore` answers no `ctx.require` for
anything else it happens to satisfy. Selecting a role therefore makes its instance reachable
under exactly one name, and every other capability that instance really does provide stays
invisible. Aliasing is what closes that gap.

**And it is by demand, never by satisfaction.** A selected instance is aliased under a
capability *because a stage in the resolved pipeline declared it needs it* — not because the
instance happens to satisfy it. The deletion fan-out is why: `SourceDeletable` is a **fan-out**
capability, satisfied by many participants at once, discovered by walking the factory registry
(`packages/weft-rag/src/weft_cli/fanout.py:59`, `deletion.py:67`) and never through
`ServiceRegistry`. A single-valued `ctx.require(SourceDeletable)` could only answer with one
arbitrary participant, which is a wrong answer wearing a type. Nothing demands it, so nothing
aliases it.
"""

import pytest

from weft_cli.service_roles import RoleTable
from weft_kernel.context import ServiceRegistry, ServiceRole, UnresolvedServiceError


class _BlobStore:
    """A stranger pack's contract. Nothing in `weft-cli` names it."""


class _Readable:
    """A capability a stage may demand of whatever fills the `blobs` role."""


class _Reapable:
    """A **fan-out** capability — many participants satisfy it at once, so a single-valued
    `ctx.require` for it could only answer with one arbitrary participant.
    `SourceDeletable`'s shape, named here as a stand-in so this file names no real capability.
    """


class _FsBlobs(_BlobStore, _Readable, _Reapable):
    """Satisfies its role's contract, one capability a stage can demand, and one fan-out
    capability nothing may demand — all three at once, which is the whole point.
    """


class _Sidecar:
    """A second, unrelated role contract — a distinct role, not a second claim on `_BlobStore`."""


class _OtherBlobs(_Sidecar, _Readable):
    """Fills a different role and satisfies the same demandable capability. Two roles cannot
    share one contract — `ServiceRegistry.add` refuses that outright — so the ambiguity this
    tests is two *different* roles both providing one demanded capability.
    """


def _table(*roles: ServiceRole) -> RoleTable:
    return RoleTable(roles={role.key: role for role in roles})


BLOBS = ServiceRole(key="blobs", contract=_BlobStore)
OTHER = ServiceRole(key="other", contract=_Sidecar)


def test_a_selected_instance_answers_under_its_own_roles_contract() -> None:
    """The floor. Selecting a role makes its instance reachable under the contract the
    declaring pack published — the plain case aliasing is built on top of.
    """
    # Arrange
    from weft_cli.run_services import register_selected_roles

    instance = _FsBlobs()
    registered = ServiceRegistry()

    # Act
    register_selected_roles(
        registered, selected={"blobs": instance}, table=_table(BLOBS), demanded=()
    )

    # Assert
    assert registered.resolve(_BlobStore) is instance


def test_a_selected_instance_also_answers_under_a_capability_a_stage_demands_of_it() -> None:
    """The property itself: one instance, reachable under two exact keys.

    `ServiceRegistry` keys by exact type, so without this a retriever that declared it needs
    `_Readable` would get `UnresolvedServiceError` for a capability the configured instance
    demonstrably has.
    """
    # Arrange
    from weft_cli.run_services import register_selected_roles

    instance = _FsBlobs()
    registered = ServiceRegistry()

    # Act
    register_selected_roles(
        registered, selected={"blobs": instance}, table=_table(BLOBS), demanded=(_Readable,)
    )

    # Assert
    assert registered.resolve(_BlobStore) is instance
    assert registered.resolve(_Readable) is instance


def test_a_capability_the_instance_satisfies_but_nothing_demands_is_not_reachable() -> None:
    """Aliasing is by **demand**, never by satisfaction.

    `_FsBlobs` really does satisfy `_Reapable`, and it is still not resolvable, because no
    stage asked for it. This is the fan-out case: `SourceDeletable` is satisfied by many
    participants at once and is discovered by walking the factory registry
    (`weft_cli/fanout.py:59`), so a single-valued answer would be one arbitrary participant
    presented as *the* answer. An `UnresolvedServiceError` naming what the run does offer is
    the honest reply.
    """
    # Arrange
    from weft_cli.run_services import register_selected_roles

    instance = _FsBlobs()
    registered = ServiceRegistry()

    # Act
    register_selected_roles(
        registered, selected={"blobs": instance}, table=_table(BLOBS), demanded=(_Readable,)
    )

    # Assert
    with pytest.raises(UnresolvedServiceError) as caught:
        registered.resolve(_Reapable)

    assert "_Reapable" in str(caught.value)


def test_a_capability_two_selected_instances_both_satisfy_is_refused_naming_both() -> None:
    """Ambiguity is refused at assembly, before anything runs, naming both claimants.

    The alternative is `ServiceRegistry.add`'s own `DuplicateServiceError` at whichever
    registration happened to come second — which reports the collision but not the two role
    keys that caused it, so an operator learns that something is ambiguous and not what to
    change. `01` requirement 5: a refusal names what was wanted and what the options are.
    """
    # Arrange
    from weft_cli.run_services import AmbiguousCapabilityError, register_selected_roles

    registered = ServiceRegistry()

    # Act / Assert
    with pytest.raises(AmbiguousCapabilityError) as caught:
        register_selected_roles(
            registered,
            selected={"blobs": _FsBlobs(), "other": _OtherBlobs()},
            table=_table(BLOBS, OTHER),
            demanded=(_Readable,),
        )

    message = str(caught.value)
    assert "_Readable" in message
    assert "blobs" in message, "the refusal names the role keys, not just the instances"
    assert "other" in message


def test_an_unselected_role_registers_nothing_rather_than_a_placeholder() -> None:
    """A role nobody configured contributes no service.

    `CLAUDE.md`: an empty answer is not a fact about the world, and a silent fallback is worse
    than a failure. A stage reaching for the contract gets `UnresolvedServiceError` naming what
    this run does offer, which is the seam where somebody who genuinely needs it comes and asks.
    """
    # Arrange
    from weft_cli.run_services import register_selected_roles

    registered = ServiceRegistry()

    # Act
    register_selected_roles(registered, selected={}, table=_table(BLOBS), demanded=(_Readable,))

    # Assert
    with pytest.raises(UnresolvedServiceError):
        registered.resolve(_BlobStore)
