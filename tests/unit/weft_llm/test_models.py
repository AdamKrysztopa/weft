"""Unit tests for `weft_llm.models`.

Mirrors `packages/weft-rag/src/weft_llm/models.py`. Covers the two-field distinction (what
the operator asked for versus what is handed to the vendor), the four-step runtime match, and
the two loud refusals — a provider prefix that disagrees with the role's provider, and a
model string a provider's catalogue cannot resolve to exactly one entry. The `meta-llama/…`
case is the edge the whole disambiguation exists for: a slash is not evidence of a prefix.
"""

import pytest

from weft_llm.models import (
    AmbiguousModelError,
    ModelProviderMismatchError,
    ModelRef,
    UnknownModelError,
    find_runtime_match,
    model_ref,
)


def test_a_provider_qualified_string_splits_into_the_two_fields() -> None:
    # Arrange / Act
    ref = model_ref(provider="openai", requested="openai/gpt-4o-mini", providers=("openai",))

    # Assert — `requested` keeps what was written, `model` is what the vendor is handed.
    assert ref == ModelRef(requested="openai/gpt-4o-mini", provider="openai", model="gpt-4o-mini")


def test_a_bare_string_is_the_runtime_model_and_the_role_supplies_the_provider() -> None:
    # Arrange / Act
    ref = model_ref(provider="scripted", requested=None)

    # Assert — a provider with exactly one model has nothing to disambiguate.
    assert (ref.provider, ref.model, ref.requested) == ("scripted", "", "")


def test_a_slash_in_a_model_id_is_not_read_as_a_provider_prefix() -> None:
    # Arrange / Act — `meta-llama` names no provider this deployment mapped, so the whole
    # string is the model id, exactly as a vendor's own catalogue writes it.
    ref = model_ref(provider="together", requested="meta-llama/Llama-3-8B", providers=("together",))

    # Assert
    assert ref.model == "meta-llama/Llama-3-8B"


def test_a_prefix_disagreeing_with_the_roles_provider_is_refused_by_name() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ModelProviderMismatchError) as raised:
        model_ref(
            provider="scripted", requested="openai/gpt-4o-mini", providers=("openai", "scripted")
        )
    message = str(raised.value)
    assert "openai" in message
    assert "scripted" in message


def test_the_runtime_match_prefers_an_exact_catalogue_entry() -> None:
    # Arrange
    ref = model_ref(provider="acme", requested="acme/small-v2", providers=("acme",))

    # Act
    matched = find_runtime_match(ref, ("small-v2", "large-v2"))

    # Assert
    assert matched.model == "small-v2"


def test_the_runtime_match_resolves_a_unique_suffix() -> None:
    # Arrange — the operator wrote the short name a vendor's own docs use.
    ref = model_ref(provider="acme", requested="small-v2", providers=("acme",))

    # Act
    matched = find_runtime_match(ref, ("acme/small-v2", "acme/large-v2"))

    # Assert
    assert matched.model == "acme/small-v2"


def test_a_model_no_catalogue_entry_matches_is_refused_listing_every_option() -> None:
    # Arrange
    ref = model_ref(provider="acme", requested="tiny", providers=("acme",))

    # Act / Assert
    with pytest.raises(UnknownModelError) as raised:
        find_runtime_match(ref, ("small-v2", "large-v2"))
    message = str(raised.value)
    assert "tiny" in message
    assert "small-v2" in message
    assert "large-v2" in message


def test_a_suffix_two_catalogue_entries_share_is_refused_rather_than_guessed() -> None:
    # Arrange
    ref = model_ref(provider="acme", requested="small-v2", providers=("acme",))

    # Act / Assert
    with pytest.raises(AmbiguousModelError) as raised:
        find_runtime_match(ref, ("eu/small-v2", "us/small-v2"))
    message = str(raised.value)
    assert "eu/small-v2" in message
    assert "us/small-v2" in message
