"""Unit tests for `weft_kernel.payload.applicability`.

Mirrors `packages/weft-kernel/src/weft_kernel/payload/applicability.py`. Task **1.6**:
*an atomic node passes the chunker unsplit without the chunker knowing what atomic
means, because applicability is declared and routed at the seam* (`docs/02-extension-
model.md` §3 → *Applicability*; `docs/11-multimodal.md` §2). This file covers `Applies`
itself — construction, the unknown-field refusal, and `matches()`'s three cases (fact
absent, fact present unconstrained, fact present with a field mismatch). Routing —
splitting and recombining a batch — is `weft_kernel.runner`'s own, covered in
`tests/unit/weft_kernel/test_runner.py`.
"""

import pytest

from weft_kernel.payload.applicability import Applies
from weft_kernel.payload.ext import ExtModel
from weft_kernel.payload.media_type import MediaType
from weft_kernel.payload.node import Node


class _Language(ExtModel):
    """`02` §3's own worked example: a fact about a node, not about the pipeline."""

    __namespace__ = "weft-test-pack"
    __schema_version__ = "1.0.0"

    code: str


class _Prose(ExtModel):
    """A fact an ordinary chunker cares about, for reasons that have nothing to do with
    tables — the mechanism `docs/11-multimodal.md` §2 describes: the chunker declares
    what it needs, and an atomic node simply never carries it."""

    __namespace__ = "weft-test-pack"
    __schema_version__ = "1.0.0"


class _Locale(ExtModel):
    """A fact with two independent fields — nothing in the tree exercised `Applies` with
    more than one keyword constraint before this repair, so a regression from "every
    field must equal" (`all(...)`) to "any field may equal" (`any(...)`) in `Applies.
    matches` would have passed every existing test in this file."""

    __namespace__ = "weft-test-pack-locale"
    __schema_version__ = "1.0.0"

    language: str
    region: str


def _node(*, ext: ExtModel | None = None) -> Node:
    node = Node.synthetic(content="hello", media_type=MediaType.TEXT, reason="test fixture")
    return node.with_ext(ext) if ext is not None else node


def test_applies_with_no_fields_matches_any_node_carrying_the_fact() -> None:
    # Arrange
    applies = Applies(_Language)
    carrying = _node(ext=_Language(code="pl"))

    # Act
    result = applies.matches(carrying)

    # Assert
    assert result is True


def test_applies_narrowed_by_field_rejects_a_node_whose_field_disagrees() -> None:
    # Arrange — same fact, present, but the wrong value: "unknown language flows past".
    applies = Applies(_Language, code="pl")
    english = _node(ext=_Language(code="en"))

    # Act
    result = applies.matches(english)

    # Assert
    assert result is False


def test_applies_fails_to_the_safe_side_when_the_fact_is_entirely_absent() -> None:
    # Arrange — no `_Prose` fact at all, the atomic-node story: the stage never sees it.
    applies = Applies(_Prose)
    atomic = _node()

    # Act
    result = applies.matches(atomic)

    # Assert
    assert result is False


def test_applies_refuses_an_unknown_field_name_naming_the_fields_that_exist() -> None:
    # Arrange / Act / Assert — a typo must not become a stage that silently never applies.
    with pytest.raises(TypeError) as excinfo:
        Applies(_Language, contry="pl")  # noqa: RUF100 - deliberate typo under test

    message = str(excinfo.value)
    assert "contry" in message
    assert "code" in message


def test_applies_narrowed_by_two_fields_rejects_a_node_agreeing_on_only_one() -> None:
    # Arrange — `region` disagrees; `language` alone matching must not be enough. An `any()`
    # regression in `Applies.matches` would let this node through.
    applies = Applies(_Locale, language="en", region="US")
    partial_match = _node(ext=_Locale(language="en", region="GB"))

    # Act
    result = applies.matches(partial_match)

    # Assert
    assert result is False


def test_applies_narrowed_by_two_fields_matches_only_when_both_agree() -> None:
    # Arrange — the positive case a two-field regression to `any()` would not distinguish
    # from the rejection above, since both would also pass this one.
    applies = Applies(_Locale, language="en", region="US")
    full_match = _node(ext=_Locale(language="en", region="US"))

    # Act
    result = applies.matches(full_match)

    # Assert
    assert result is True


def test_two_applies_built_with_the_same_fields_in_different_order_compare_equal() -> None:
    # Arrange — printable, comparable data, never a callable: construction order must not
    # leak into equality, or two resolutions of one pipeline could disagree by accident.
    first = Applies(_Language, code="pl")
    second = Applies(_Language, code="pl")

    # Act / Assert
    assert first == second
