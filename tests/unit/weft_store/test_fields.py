"""Unit tests for `weft_store.fields`.

Mirrors `packages/weft-store/src/weft_store/fields.py`. This module is what
stops two stores disagreeing about what a `Filter` means, so its tests are
deliberately about the *refusals*: what a path may name, and which operator each
kind of field admits. The agreement itself — that two engines answer the same
filter identically — is `tests/integration/test_store_conformance.py`'s subject
and needs both containers; everything here is a pure function over a string.

Covers the happy path (a core field and an extension path parse to what they
name), the edge case (an `ext` path with no key inside the namespace, which
`exists` is the honest use of), and the error cases (a path reaching nothing, and
each of the three operator refusals a second backend forced).
"""

import pytest

from weft_store.contract import Filter, FilterOp
from weft_store.fields import (
    FieldKind,
    FilterOpMismatchError,
    NodeField,
    UnaddressableFieldError,
    field_for,
    leaves,
    parse_field_path,
)


def test_a_core_field_parses_to_the_field_it_names() -> None:
    # Act
    path = parse_field_path("lineage.sources")

    # Assert
    assert path.core is NodeField.SOURCES
    assert path.kind is FieldKind.TEXT_SET
    assert path.namespace == ""


def test_an_extension_path_parses_into_its_namespace_and_the_keys_inside_it() -> None:
    # Act
    path = parse_field_path("ext.weft-pdf.starts")

    # Assert
    assert path.kind is FieldKind.EXTENSION
    assert path.namespace == "weft-pdf"
    assert path.keys == ("starts",)


def test_a_namespace_with_no_key_addresses_the_whole_extension_value() -> None:
    # Arrange — the edge case: "does this pack's data exist on this node at all", which is
    # a question with no field inside the namespace to name.
    path = parse_field_path("ext.weft-pdf")

    # Assert
    assert path.kind is FieldKind.EXTENSION
    assert path.keys == ()


def test_a_path_reaching_nothing_is_refused_naming_every_core_field() -> None:
    # Act / Assert — `01` requirement 5: a filter matching nothing looks exactly like a
    # corpus holding nothing, and the difference is the question the operator asked.
    with pytest.raises(UnaddressableFieldError) as raised:
        parse_field_path("metadata.author")
    message = str(raised.value)
    assert "metadata.author" in message
    for core in NodeField:
        assert core.value in message


def test_equality_against_a_set_is_refused_and_names_contains() -> None:
    # Act / Assert — a document store matches a payload array element-wise, so `eq` here
    # would mean membership there and whole-list equality in SQL: one spelling, two
    # meanings, no error.
    with pytest.raises(FilterOpMismatchError, match="contains"):
        field_for(FilterOp.EQ, "lineage.sources")


def test_contains_against_a_string_is_refused_because_that_is_text_search() -> None:
    # Act / Assert
    with pytest.raises(FilterOpMismatchError, match="TextSearch"):
        field_for(FilterOp.CONTAINS, "content")


def test_an_ordered_comparison_against_a_core_field_is_refused_naming_collation() -> None:
    # Act / Assert — the value-side half of this rule lives on `Filter` itself; this is the
    # field-side half, and both exist because two engines had to agree.
    with pytest.raises(FilterOpMismatchError, match="collation"):
        field_for(FilterOp.GT, "content")


def test_leaves_flattens_a_tree_down_to_its_comparisons() -> None:
    # Arrange
    tree = Filter(
        op=FilterOp.AND,
        clauses=(
            Filter(op=FilterOp.EQ, field="content", value="alpha"),
            Filter(
                op=FilterOp.NOT,
                clauses=(Filter(op=FilterOp.EXISTS, field="ext.weft-pdf.backend"),),
            ),
        ),
    )

    # Act
    found = leaves(tree)

    # Assert
    assert tuple(leaf.op for leaf in found) == (FilterOp.EQ, FilterOp.EXISTS)
