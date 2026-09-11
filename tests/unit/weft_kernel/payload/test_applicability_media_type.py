"""`Applies` can constrain a node's media type — ledger task 9.2's missing half.

`Applies` has wrapped an `ExtModel` subclass and nothing else since task 1.6, and `media_type` is
a field on `Node` rather than a namespaced fact. So *"a node whose media type is not text reaches
the store whole"* — the property `9.2` requires — was not expressible by any `applies_to` a plugin
could write, even though `9.2`'s own evidence paragraph states the mechanism already exists
(`docs/internal/lessons.md` `L9.42`).

**Why this belongs in the kernel and names no capability.** `MediaType` is a kernel type
(`weft_kernel.payload.media_type`), and `media_type` is a field the kernel already puts on every
`Node`. Constraining on it is the applicability grammar reaching a fact the payload model already
carries — not the kernel learning what a chunker, a store or an extractor is. The alternative
considered and rejected was a `splits` declaration on the `Chunker` contract, which would have made
the runner evaluate a capability-specific declaration and put the word *chunker* one import away
from `weft_kernel.runner`.

**Absence keeps its existing meaning.** A stage that declares no `applies_to` still applies to
everything, so nothing written before this task changes — the same safe-side reading
`weft_kernel.runner`'s own docstring already states for the empty tuple. That property is not
re-asserted here: `tests/unit/weft_kernel/test_runner.py` already pins it against the runner
itself, which is where absence acquires its meaning, and a second copy in this file would have
to reach through a private name to say anything the first does not.
"""

import pytest

from weft_kernel.payload.applicability import Applies
from weft_kernel.payload.ext import ExtModel
from weft_kernel.payload.media_type import MediaType
from weft_kernel.payload.node import Node


class _Language(ExtModel):
    """A fact declared at module level, because `_FactRef` persists `module:QualName` and a
    function-local class's qualname (`...<locals>._Language`) resolves against no module.
    """

    __namespace__ = "test-applicability-roundtrip"
    __schema_version__ = "1.0.0"

    code: str = "en"


def _node(*, media_type: MediaType) -> Node:
    return Node.synthetic(content="x", media_type=media_type, reason="a test subject")


def test_a_media_type_constraint_matches_a_node_of_that_type() -> None:
    """The happy path: `Applies(media_type=MediaType.TEXT)` claims a text node."""
    # Arrange
    applies = Applies(media_type=MediaType.TEXT)

    # Act / Assert
    assert applies.matches(_node(media_type=MediaType.TEXT))


def test_a_media_type_constraint_does_not_match_another_type() -> None:
    """The property `9.2` exists for: a `TABLE` node is *not* claimed by a text-only stage, so the
    runner routes it past rather than splitting it.
    """
    # Arrange
    applies = Applies(media_type=MediaType.TEXT)

    # Act / Assert
    assert not applies.matches(_node(media_type=MediaType.TABLE))
    assert not applies.matches(_node(media_type=MediaType.IMAGE))


def test_several_media_types_may_be_claimed_at_once() -> None:
    """A stage that handles more than one media type declares both rather than two `Applies`.

    Two separate `Applies` in one tuple are conjunctive — every one must match — so a node cannot
    be two media types and the two-entry spelling would claim nothing at all. That failure would be
    silent, which is the class `02` §3 rules out everywhere else.
    """
    # Arrange
    applies = Applies(media_type=(MediaType.TEXT, MediaType.IMAGE))

    # Act / Assert
    assert applies.matches(_node(media_type=MediaType.TEXT))
    assert applies.matches(_node(media_type=MediaType.IMAGE))
    assert not applies.matches(_node(media_type=MediaType.TABLE))


def test_a_media_type_constraint_is_refused_beside_a_fact() -> None:
    """One `Applies` states one kind of constraint.

    A fact constraint narrows an `ExtModel` a node may carry; a media-type constraint narrows a
    field every node has. Allowing both in one object would give the tuple two conjunction rules
    to mean at once, and the reader no way to tell which applied.
    """

    # Arrange — a local fact, so this kernel test imports no pack
    class _Fact(ExtModel):
        __namespace__ = "test-applicability"
        __schema_version__ = "1.0.0"

        code: str = "x"

    # Act / Assert
    with pytest.raises(ValueError, match="media_type"):
        Applies(_Fact, media_type=MediaType.TEXT)


def test_a_media_type_constraint_survives_a_round_trip_through_json() -> None:
    """The failure this module has already paid for once, in the other half of the grammar.

    `_FactRef`'s own docstring records it: the serialiser "worked from the day it was written, so
    nothing ever failed while records were being created; the failure arrived later and somewhere
    else, in three commands that merely *read* the directory those records live in." A media-type
    constraint that dumps to `["text"]` and reads back as the string `"text"` matches no node at
    all — and matching nothing is how a stage that should have run is skipped in silence.
    """
    # Arrange
    applies = Applies(media_type=(MediaType.TEXT, MediaType.IMAGE))

    # Act
    reread = Applies.model_validate(applies.model_dump(mode="json"))

    # Assert
    assert reread.matches(_node(media_type=MediaType.IMAGE))
    assert not reread.matches(_node(media_type=MediaType.TABLE))
    assert repr(reread) == repr(applies)


def test_a_fact_constraint_still_survives_the_same_round_trip() -> None:
    """The half that already worked, asserted here because 9.2 changed the field it travels in."""
    # Arrange
    applies = Applies(_Language, code="pl")

    # Act
    reread = Applies.model_validate(applies.model_dump(mode="json"))

    # Assert
    assert reread.fact is _Language
    assert reread.constraints == (("code", "pl"),)


def test_applies_stating_no_constraint_at_all_is_refused() -> None:
    """`fact` stopped being a required field so a media-type-only `Applies` could exist, and a
    model that requires nothing accepts everything. `Applies()` would otherwise construct an
    object that matches no node and reports no problem — the silent-fallback class `CLAUDE.md`
    rules out, arriving as a stage that quietly never runs.
    """
    # Act / Assert
    with pytest.raises((TypeError, ValueError)):
        Applies()
