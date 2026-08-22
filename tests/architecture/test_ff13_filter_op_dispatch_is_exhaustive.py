"""Fitness function 13 — every dispatch over a published `Enum` is exhaustive by construction.

Ledger task **5.2b**, and `docs/09-release.md` §2.3's own words: "A version bump does not
fix silence, so silence is a separate defect. Adding an `Enum` member is textbook-additive
and, in this tree, makes a backend answer the wrong query without erroring... A published
`Enum` must therefore be dispatched exhaustively by construction, with no fall-through
default — requirement 5 applied to a closed vocabulary instead of an open one."

**A new numbered function, not a clause of FF4.** `01` → *Fitness functions* item 4 is the
closest neighbour — "no closed enumeration of registry keys... expressed as a runtime
property" — and its own proof technique is the inverse of this one's: FF4(b) manufactures a
name *nothing was told about* (a UUID) and proves the system can still select and run it,
which is what makes a registry key space *open*. `FilterOp` is not a registry — there is no
`FilterOp.keys()` to compare a dispatch against, because the vocabulary is not names
resolved against a plugin set, it is a closed enum serialised into stored data. The property
this file proves is the mirror image of FF4(b)'s: manufacture an *operator nothing was told
about* and prove every dispatch **refuses** it, which is what makes a closed vocabulary
actually closed rather than a comment saying so. Filing it as a new function rather than a
third clause of FF4 keeps FF4's own subject — registry keys, the open case — from growing a
clause about the opposite case, a closed one, which the ledger entry and `01`'s edit both
record as the argument for the split.

**The five sites `docs/09-release.md` §2.3 names, plus three more this task's own audit
found.** The five: `weft_qdrant.store._condition` (an unknown operator answered as `eq`),
`_range` (as `gte`), `to_qdrant_filter` (an unknown *combinator* would be routed through
`_condition` as a leaf), `weft_store.contract.Filter._shape_matches_op` (answered as `not`),
and `weft_store.fields`'s `_ADMITTED[FieldKind.EXTENSION]`, derived from the enum and so
silently *widening* rather than falling through. The three more: `weft_store.pgvector_store`
publishes its own translator over the identical `FilterOp` vocabulary — `_predicate`,
`_text_predicate`, `_text_set_predicate` and `_extension_predicate` — and every one of them
had the same shape, undiscovered by the ledger's own list because it names only
`weft_qdrant.store` and `weft_store.contract`/`fields`, never pgvector's SQL side of the
identical translation task 2.6 built. `docs/lessons.md` L5.14 records the omission.

**The mechanism chosen at each site, and why.** `Filter._shape_matches_op`,
`weft_qdrant.store`'s three functions and `weft_store.pgvector_store`'s four all move to
`match self.op: ... case _: raise UnhandledFilterOpError(...)` — a `match` reads as an
enumeration of the operators a site handles, and Python enforces nothing about it being
complete, which is exactly why the mandatory `case _:` arm is the mechanism rather than an
ornament: it is what turns "every branch I wrote happens to cover today's members" into "an
operator no branch names is refused, always." `weft_store.fields._ADMITTED[FieldKind.
EXTENSION]` needed a different fix — not a raise, because `field_for` already raises
`FilterOpMismatchError` for an operator missing from this table; the defect was that the
table *widened itself*. `docs/lessons.md` L5.6's shape one level up from a version
constant: a permitted set computed from the enum it is supposed to gate does not narrow as
the vocabulary grows, it grows with it. The fix states the nine members by hand.

**Why a runtime check, and what it manufactures.** A static grep for "case _: raise" would
pass a `match` that raises for the wrong reason, or a hand-written membership check that
raises correctly for a typo but not for a genuinely new member, and it could not check
`_ADMITTED`'s widening at all — that defect has no `else` to grep for. The property this
file actually needs is FF2's and FF4(b)'s own standard: a fact about what the code *does*,
not what it is shaped like. `_unknown_op()` builds a `FilterOp`-shaped `StrEnum` value —
same base type, same `.value` machinery, a string no real member holds — standing in for
"the operator this dispatch predates," and every dispatch above is driven with it and
asserted to raise `UnhandledFilterOpError` (or, for `_ADMITTED`, asserted absent from the
permitted set) rather than to answer. `test_the_check_can_actually_fail` proves the
assertion is not vacuous by running the pre-fix shape of `_range` inline and showing it
answers `"gte"` instead of raising — the defect this function exists to catch, reproduced
rather than described.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, cast

import pytest
from psycopg import sql

import weft_qdrant.store as qdrant_store
import weft_store.fields as fields_module
import weft_store.pgvector_store as pgvector_store
from weft_store.contract import Filter, FilterOp, UnhandledFilterOpError
from weft_store.fields import FieldKind, FieldPath, NodeField


def _unknown_op() -> FilterOp:
    """A `FilterOp`-shaped value none of the twelve real members equal.

    A functional `StrEnum` built fresh, not a bare `cast(FilterOp, "some-string")`: several
    sites under test read `.value` off it (every real `WeftError` message below does), and a
    plain `str` has no such attribute unless it happens to share `FilterOp`'s own machinery.
    Built as its own tiny enum, once per call, rather than a module-level constant, so a test
    that mutates or monkeypatches around it cannot leak a stale identity into another.
    """
    return cast(FilterOp, StrEnum("_UnknownFilterOp", {"UNSEEN": "unseen-operator"}).UNSEEN)


def _private(target: object, name: str) -> Any:
    """Reach a module- or instance-private symbol by its exact name, untyped.

    This file's whole subject is the module-private dispatch functions task 5.2b changed —
    `_condition`, `_range`, `_shape_matches_op` and the rest — because the property under
    test (does this exact branch raise for an operator it has never seen) is not reachable
    through any public entry point without first passing `weft_store.fields.field_for`'s own,
    separate admission check. `getattr` with a string literal types as `Any` rather than
    tripping pyright's `reportPrivateUsage` — there is no static attribute-access expression
    for it to flag — which is what keeps every call site below free of a suppression comment.
    """
    return getattr(target, name)


def _field_for_stub_qdrant(op: FilterOp, field: str) -> None:
    """Stands in for `weft_store.fields.field_for` inside `weft_qdrant.store`'s namespace,
    so `_condition`'s own dispatch is exercised in isolation from `field_for`'s admission
    check, which would otherwise refuse the manufactured operator first and for an unrelated
    reason (a lookup-table miss, not "no case for this").
    """
    del op, field


def _field_for_stub_pgvector(op: FilterOp, field: str) -> FieldPath:
    """The pgvector equivalent of `_field_for_stub_qdrant` — `_predicate` needs a `FieldPath`
    back, not `None`, to route into `_text_predicate`'s own dispatch rather than fail before
    it gets there.
    """
    del op, field
    return FieldPath(kind=FieldKind.TEXT, core=NodeField.CONTENT)


class TestContractShapeValidatorRaises:
    """`weft_store.contract.Filter._shape_matches_op` — the site pre-fix would have
    validated an unknown operator as if it were `not`, silently, given exactly one clause.
    """

    def test_an_unseen_op_with_one_clause_is_refused_not_accepted_as_not(self) -> None:
        # Arrange — pydantic's own field validation can never produce this: `op: FilterOp`
        # refuses any string that is not a real member before this validator ever runs, so
        # the only way to drive it is `model_construct`, which bypasses that validation —
        # standing in for a future member pydantic *would* accept once it exists.
        leaf = Filter.model_construct(op=FilterOp.EQ, field="content", value="x", clauses=())
        bogus = Filter.model_construct(op=_unknown_op(), field=None, value=None, clauses=(leaf,))

        # Act / Assert — pre-fix, this shape (exactly one clause, no field, no value) is
        # precisely what `not` requires, so the validator returned `self` unchanged rather
        # than raising anything at all.
        with pytest.raises(UnhandledFilterOpError):
            _private(bogus, "_shape_matches_op")()

    def test_a_real_filter_still_validates(self) -> None:
        assert Filter(op=FilterOp.EQ, field="content", value="x").op is FilterOp.EQ


class TestQdrantTranslatorRaises:
    """`weft_qdrant.store` — the two sites `docs/09-release.md` §2.3 names by name, plus
    `to_qdrant_filter`'s own top-level routing, which the release note does not call out but
    is the same shape one level up.
    """

    def test_to_qdrant_filter_refuses_an_unseen_op(self) -> None:
        bogus = Filter.model_construct(op=_unknown_op(), field="content", value="x", clauses=())

        with pytest.raises(UnhandledFilterOpError):
            qdrant_store.to_qdrant_filter(bogus)

    def test_condition_refuses_an_unseen_op(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(qdrant_store, "field_for", _field_for_stub_qdrant)
        bogus = Filter.model_construct(op=_unknown_op(), field="content", value="x", clauses=())

        with pytest.raises(UnhandledFilterOpError):
            _private(qdrant_store, "_condition")(bogus)

    def test_range_refuses_an_unseen_op(self) -> None:
        with pytest.raises(UnhandledFilterOpError):
            _private(qdrant_store, "_range")(_unknown_op(), 1.0)

    def test_a_real_filter_still_translates(self) -> None:
        translated = qdrant_store.to_qdrant_filter(
            Filter(op=FilterOp.EQ, field="content", value="x")
        )
        assert translated.must is not None


class TestPgvectorTranslatorRaises:
    """`weft_store.pgvector_store` — the sixth through ninth sites: the SQL half of task
    2.6's translation, which `docs/09-release.md` §2.3's five named sites never mention.
    Every one of its four `FilterOp`-dispatching functions had the identical shape.
    """

    def test_predicate_refuses_an_unseen_op(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pgvector_store, "field_for", _field_for_stub_pgvector)
        bogus = Filter.model_construct(op=_unknown_op(), field="content", value="x", clauses=())

        with pytest.raises(UnhandledFilterOpError):
            _private(pgvector_store, "_predicate")(bogus, {})

    def test_text_predicate_refuses_an_unseen_op(self) -> None:
        column = sql.Identifier("content")
        value = sql.Placeholder("f0")

        with pytest.raises(UnhandledFilterOpError):
            _private(pgvector_store, "_text_predicate")(_unknown_op(), column, value)

    def test_text_set_predicate_refuses_an_unseen_op(self) -> None:
        column = sql.Identifier("sources")
        value = sql.Placeholder("f0")

        with pytest.raises(UnhandledFilterOpError):
            _private(pgvector_store, "_text_set_predicate")(_unknown_op(), column, value)

    def test_extension_predicate_refuses_an_unseen_op(self) -> None:
        path = FieldPath(kind=FieldKind.EXTENSION, namespace="weft-pdf", keys=("starts",))

        with pytest.raises(UnhandledFilterOpError):
            _private(pgvector_store, "_extension_predicate")(_unknown_op(), path, 1, {})

    def test_a_real_filter_still_translates(self) -> None:
        values: dict[str, object] = {}
        composed = _private(pgvector_store, "_predicate")(
            Filter(op=FilterOp.EQ, field="content", value="x"), values
        )
        assert values == {"f0": "x"}
        assert "content" in composed.as_string(None)


class TestExtensionAdmittedSetDoesNotWiden:
    """`weft_store.fields._ADMITTED[FieldKind.EXTENSION]` — the one site whose defect is not
    a fall-through answer but a permitted set that grows with the enum instead of by hand.
    """

    def test_an_unseen_op_is_admitted_by_no_field_kind(self) -> None:
        bogus = _unknown_op()

        admitted = _private(fields_module, "_ADMITTED")
        for kind in FieldKind:
            assert bogus not in admitted[kind], (
                f"'{bogus.value}' is admitted for {kind}, which means the permitted set "
                f"widened to include an operator nobody stated on purpose"
            )


def test_the_check_can_actually_fail() -> None:
    """Reproduces the pre-fix shape of `weft_qdrant.store._range` to prove the assertions
    above are not vacuously true against a translator that no longer has anything to break.

    `docs/09-release.md` §2.3, verbatim: "`weft_qdrant.store` reinterprets an unknown
    `FilterOp` as ... `gte` in `_range`." The stand-in below is exactly that shape — three
    named branches and an unconditional `return` — run against the identical unseen
    operator the tests above use, to show it answers rather than raises.
    """

    def _pre_fix_range(op: FilterOp) -> str:
        if op is FilterOp.LT:
            return "lt"
        if op is FilterOp.LTE:
            return "lte"
        if op is FilterOp.GT:
            return "gt"
        return "gte"  # the silent default task 5.2b's fix removed

    answered = _pre_fix_range(_unknown_op())

    assert answered == "gte", (
        "this stand-in must silently answer for an operator it has never seen, or it does "
        "not reproduce the defect the assertions above prove is gone from the real code"
    )
    with pytest.raises(UnhandledFilterOpError):
        _private(qdrant_store, "_range")(_unknown_op(), 1.0)
