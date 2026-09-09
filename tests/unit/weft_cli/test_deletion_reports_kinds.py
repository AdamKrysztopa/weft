"""`weft delete` distinguishes what each participant removed — ledger task `9.3`.

`Removed` gains a per-kind breakdown in the same task; this file is about the half of the property
that lives in the CLI, because a field a participant fills and nothing reads is `L6.14`'s shape
with the sides swapped. Measured 2026-09-06 before this task:
`weft_cli.deletion._delete_from` ended `return removed.node_count`
(`packages/weft-rag/src/weft_cli/deletion.py:129`), so the `Removed` a participant answered with
was discarded at the first frame that saw it, and no field added to that model could reach an
operator at all.

The property in the ledger's own words: *a blob store that reaped forty blobs and a node store that
removed no node are distinguishable in `weft delete`'s output*. Two participants, two answers, one
rendered result that tells them apart.

**The unchanged line is asserted exactly and the new one is not.** `pgvector (weft-rag): 6 node(s)
removed` is existing, pinned behaviour reproduced in shipped transcripts, so it is compared byte for
byte. What a participant reporting kinds renders is a new decision, and pinning its full text here
would hand a format to the implementer rather than the fact; what is asserted is that the count and
the kind both reach the reader and that the two participants read differently.
"""

from __future__ import annotations

from weft_cli.commands import DeleteCommandResult
from weft_cli.deletion import ParticipantOutcome, delete_everywhere, participants
from weft_cli.exit_codes import ExitCode
from weft_cli.render import Rendered, render_outcome
from weft_kernel.payload import Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import Removed, SourceDeletable


class _NodeParticipant:
    """A participant that removes nodes and nothing else — every participant before this task."""

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: SourceId) -> Removed:
        return Removed(source_id=source_id, node_count=6)


class _BlobParticipant:
    """The case `9.4` makes ordinary: forty things gone, not one of them a node."""

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: SourceId) -> Removed:
        return Removed(source_id=source_id, node_count=0, removed={"blob": 40})


def _rendered(*outcomes: ParticipantOutcome) -> Rendered:
    result = DeleteCommandResult(source_id="doc-1", participants=outcomes)
    return render_outcome(Produced(value=result))


def _rendered_lines(*outcomes: ParticipantOutcome) -> list[str]:
    stdout = _rendered(*outcomes).stdout
    assert stdout is not None, "the delete renderer answered with no stdout at all"
    return stdout.splitlines()


async def test_the_fan_out_carries_each_participants_kinds_through() -> None:
    """The chain: what a participant answered survives as far as the command's own result."""
    # Arrange
    registry = Registry()
    registry.add(SourceDeletable, "pgvector", _NodeParticipant, distribution="weft-rag")
    registry.add(SourceDeletable, "blobfs", _BlobParticipant, distribution="weft-blob")
    targets = participants(registry=registry, store_names=frozenset({"pgvector"}))

    # Act
    outcomes = await delete_everywhere(SourceId("doc-1"), targets=targets)

    # Assert
    by_plugin = {outcome.plugin: outcome for outcome in outcomes}
    assert dict(by_plugin["blobfs"].removed) == {"blob": 40}
    assert by_plugin["blobfs"].node_count == 0
    assert dict(by_plugin["pgvector"].removed) == {}
    assert by_plugin["pgvector"].node_count == 6


def test_a_participant_reporting_only_nodes_renders_exactly_as_it_always_did() -> None:
    """Existing, pinned output — a shipped transcript reproduces it, so it is compared exactly."""
    # Arrange
    outcome = ParticipantOutcome(
        contract="SourceDeletable", plugin="pgvector", distribution="weft-rag", node_count=6
    )

    # Act
    lines = _rendered_lines(outcome)

    # Assert
    assert "  pgvector (weft-rag): 6 node(s) removed" in lines


def test_a_participant_reporting_kinds_is_distinguishable_from_one_that_does_not() -> None:
    """9.3's property, read off the rendered answer an operator actually sees."""
    # Arrange
    nodes = ParticipantOutcome(
        contract="SourceDeletable", plugin="pgvector", distribution="weft-rag", node_count=6
    )
    blobs = ParticipantOutcome(
        contract="SourceDeletable",
        plugin="blobfs",
        distribution="weft-blob",
        node_count=0,
        removed={"blob": 40},
    )

    # Act
    lines = _rendered_lines(nodes, blobs)

    # Assert
    blob_line = next(line for line in lines if "blobfs" in line)
    node_line = next(line for line in lines if "pgvector" in line)
    assert "40" in blob_line
    assert "blob" in blob_line.removeprefix("  blobfs (weft-blob):")
    assert blob_line != node_line


def test_several_kinds_all_reach_the_reader() -> None:
    """Phase 11 counts entities and facts through this same field, so two kinds is the shape."""
    # Arrange
    outcome = ParticipantOutcome(
        contract="SourceDeletable",
        plugin="graph",
        distribution="weft-kg",
        node_count=0,
        removed={"entity": 12, "relation": 30},
    )

    # Act
    line = next(line for line in _rendered_lines(outcome) if "graph" in line)

    # Assert
    assert "12" in line
    assert "entity" in line
    assert "30" in line
    assert "relation" in line


class _ReservedKeyParticipant:
    """A participant whose own `delete_source` violates the reserved-key rule.

    The mistake this models is a real one an author can make: reporting the node count twice,
    once under `node_count` and once as a kind. `Removed`'s validator refuses it — inside the
    participant's own frame, so the exception the fan-out sees comes from the participant.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: SourceId) -> Removed:
        return Removed(source_id=source_id, node_count=6, removed={"node": 6})


async def test_a_participant_refused_by_the_reserved_key_is_named_and_the_others_still_run() -> (
    None
):
    """The whole chain 9.3's reserved key sits on, end to end rather than in three pieces.

    Before this test the raise, the catch, the naming and the surviving participant were each
    covered alone and the chain only by one manual run of the binary, which `ci-checks` cannot
    repeat. `_ask`'s broad `except Exception` is what turns the `ValidationError` into data about
    that participant instead of control flow that ends the fan-out, and that is the behaviour
    being pinned — not the exception type.
    """
    # Arrange
    registry = Registry()
    registry.add(SourceDeletable, "pgvector", _NodeParticipant, distribution="weft-rag")
    registry.add(SourceDeletable, "reserved", _ReservedKeyParticipant, distribution="weft-bad")
    targets = participants(registry=registry, store_names=frozenset({"pgvector"}))

    # Act
    outcomes = await delete_everywhere(SourceId("doc-1"), targets=targets)
    rendered = _rendered(*outcomes)
    lines = _rendered_lines(*outcomes)

    # Assert — the good participant still ran, the bad one is named, and the refusal says where
    # the number already lives rather than merely that something was wrong.
    by_plugin = {outcome.plugin: outcome for outcome in outcomes}
    assert by_plugin["pgvector"].node_count == 6
    assert by_plugin["reserved"].failed
    assert "node_count" in (by_plugin["reserved"].error or "")
    assert "  pgvector (weft-rag): 6 node(s) removed" in lines
    assert "  reserved (weft-bad): failed" in lines
    assert "node_count" in (rendered.stderr or "")
    assert rendered.exit_code is ExitCode.OPERATION_FAILED


def test_a_failing_participant_reports_no_kinds_rather_than_a_wrong_count() -> None:
    """The error case: a participant that raised removed nothing anyone can name."""
    # Arrange
    outcome = ParticipantOutcome(
        contract="SourceDeletable",
        plugin="broken",
        distribution="weft-broken",
        error="RuntimeError: connection refused",
    )

    # Act
    lines = _rendered_lines(outcome)

    # Assert
    assert dict(outcome.removed) == {}
    assert "  broken (weft-broken): failed" in lines
    assert _rendered(outcome).exit_code is ExitCode.OPERATION_FAILED
