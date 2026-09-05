"""Unit tests for `weft_llm.errors`.

Mirrors `packages/weft-rag/src/weft_llm/errors.py`. Covers the shape every consumer of this
taxonomy actually depends on: `LLMTransientError` leaves are `transient=True` without the
caller having to set it, `LLMPermanentError` leaves are `transient=False` the same way, and
`provider`/`model` survive onto the instance alongside `WeftError`'s own four attribution
fields — because the retry wrapper (`.phase2-design.md` §7) decides on `isinstance(exc,
LLMTransientError)` alone, and a leaf that forgot to inherit the right branch would silently
stop being retried with nothing here to catch it.
"""

import pytest

from weft_kernel.errors import WeftError
from weft_llm.errors import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMCompletionError,
    LLMConnectionError,
    LLMContentFilterError,
    LLMContextLengthError,
    LLMError,
    LLMNotFoundError,
    LLMPermanentError,
    LLMPermissionDeniedError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMTimeoutError,
    LLMTransientError,
)

#: The fourteen classes `.phase2-design.md` §7 names, and the shape a test per row proves.
_ALL_CLASSES = (
    LLMError,
    LLMTransientError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMConnectionError,
    LLMServiceUnavailableError,
    LLMPermanentError,
    LLMAuthenticationError,
    LLMPermissionDeniedError,
    LLMBadRequestError,
    LLMNotFoundError,
    LLMContentFilterError,
    LLMContextLengthError,
    LLMCompletionError,
)

_TRANSIENT_LEAVES = (
    LLMRateLimitError,
    LLMTimeoutError,
    LLMConnectionError,
    LLMServiceUnavailableError,
)

_PERMANENT_LEAVES = (
    LLMAuthenticationError,
    LLMPermissionDeniedError,
    LLMBadRequestError,
    LLMNotFoundError,
    LLMContentFilterError,
    LLMContextLengthError,
)


def test_the_taxonomy_has_exactly_fourteen_classes_all_rooted_at_weft_error() -> None:
    # Assert — the floor: a class dropped from this tuple by mistake is a smaller, silently
    # narrower taxonomy, which is exactly the drift `manual/troubleshooting.md`'s coverage
    # check exists to catch one commit later than this test would.
    assert len(_ALL_CLASSES) == 14
    assert len(set(_ALL_CLASSES)) == 14
    assert all(issubclass(cls, WeftError) for cls in _ALL_CLASSES)


@pytest.mark.parametrize("cls", _TRANSIENT_LEAVES)
def test_every_transient_leaf_is_marked_transient_without_the_caller_setting_it(
    cls: type[LLMTransientError],
) -> None:
    # Act
    exc = cls("boom", provider="openai", model="gpt-4o-mini")

    # Assert
    assert exc.transient is True
    assert isinstance(exc, LLMTransientError)
    assert exc.provider == "openai"
    assert exc.model == "gpt-4o-mini"


@pytest.mark.parametrize("cls", _PERMANENT_LEAVES)
def test_every_permanent_leaf_is_marked_not_transient_without_the_caller_setting_it(
    cls: type[LLMPermanentError],
) -> None:
    # Act
    exc = cls("boom", provider="openai", model="gpt-4o-mini")

    # Assert
    assert exc.transient is False
    assert isinstance(exc, LLMPermanentError)


def test_completion_error_defaults_to_not_transient_and_is_not_under_either_branch() -> None:
    # Arrange / Act — the vendor answered; retrying the identical call fixes nothing, and
    # `LLMCompletionError` must not accidentally satisfy the retry wrapper's `isinstance`
    # check for either branch.
    exc = LLMCompletionError("could not parse anything usable", provider="openai", model="m")

    # Assert
    assert exc.transient is False
    assert not isinstance(exc, LLMTransientError)
    assert not isinstance(exc, LLMPermanentError)


def test_attribution_fields_pass_through_alongside_provider_and_model() -> None:
    # Arrange / Act — the four `WeftError` fields the registration seam fills in must still
    # be reachable on an `LLMError`, not shadowed by the two new ones.
    exc = LLMRateLimitError(
        "too many requests",
        provider="openai",
        model="gpt-4o-mini",
        pack="weft-openai",
        contract="LLMProvider",
        plugin="openai",
        stage="generate",
    )

    # Assert
    assert exc.pack == "weft-openai"
    assert exc.contract == "LLMProvider"
    assert exc.plugin == "openai"
    assert exc.stage == "generate"
    assert exc.provider == "openai"
    assert exc.model == "gpt-4o-mini"
