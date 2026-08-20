"""Unit tests for `weft_cli.config_surface`.

Mirrors `packages/weft-cli/src/weft_cli/config_surface.py`. Task **3.7**'s own `--origin`
proof: covers the happy path (no `weft.toml` at all — every key defaults), the edge case the
reference's sentinel bug could not express — a value **explicitly** set to what the default
would have been anyway, distinguished from a key genuinely absent — and the error cases of
an unknown key and an illegal `[permissions]` value. `set_config_text` is proven separately:
replacing an existing key, inserting into an existing section, appending a whole new section,
and a round trip through `tomllib` that a comment survives untouched.
"""

from __future__ import annotations

import tomllib

import pytest

from weft_cli.config_surface import (
    CONFIG_KEYS,
    ConfigOrigin,
    UnknownConfigKeyError,
    config_entry,
    effective_config,
    set_config_text,
    validate_set_value,
)
from weft_kernel.errors import WeftError

# --- effective_config / config_entry ----------------------------------------------------


def test_no_document_at_all_defaults_every_key() -> None:
    entries = effective_config(None)

    assert {entry.key for entry in entries} == set(CONFIG_KEYS)
    assert all(entry.origin is ConfigOrigin.DEFAULT for entry in entries)


def test_a_value_explicitly_set_to_the_default_is_still_origin_file() -> None:
    # The reference's own sentinel bug (`.phase3-design.md` §2.6) could not tell this case apart
    # from "never set at all" — an explicit `embed = "hash"` is indistinguishable from
    # nothing being said, because comparing the merged value against the default throws the
    # provenance away. This is the property that check structurally cannot have.
    document: dict[str, object] = {"services": {"embed": "hash"}}  # "hash" is the default

    entry = config_entry(document, "services.embed")

    assert entry.value == "hash"
    assert entry.origin is ConfigOrigin.FILE


def test_a_key_the_file_never_mentions_is_origin_default() -> None:
    document: dict[str, object] = {"services": {"store": "qdrant"}}  # embed left unmentioned

    entry = config_entry(document, "services.embed")

    assert entry.value == "hash"
    assert entry.origin is ConfigOrigin.DEFAULT


def test_config_entry_refuses_an_unknown_key_naming_the_valid_ones() -> None:
    with pytest.raises(UnknownConfigKeyError) as exc_info:
        config_entry(None, "services.bogus")

    assert exc_info.value.valid_options == CONFIG_KEYS


# --- validate_set_value ------------------------------------------------------------------


def test_validate_set_value_accepts_a_plugin_name_for_a_services_key() -> None:
    validate_set_value("services.embed", "openai")  # does not raise


def test_validate_set_value_refuses_an_empty_plugin_name() -> None:
    with pytest.raises(WeftError, match="services.embed"):
        validate_set_value("services.embed", "")


def test_validate_set_value_refuses_an_illegal_permissions_value() -> None:
    with pytest.raises(WeftError, match="allow.*ask"):
        validate_set_value("permissions.destroy", "sometimes")


def test_validate_set_value_refuses_an_unknown_key() -> None:
    with pytest.raises(UnknownConfigKeyError):
        validate_set_value("services.bogus", "x")


# --- set_config_text ----------------------------------------------------------------------


def test_set_config_text_replaces_an_existing_key_in_place() -> None:
    text = '[services]\nembed = "hash"\nstore = "pgvector"\n'

    result = set_config_text(text, section="services", key="embed", value="openai")

    assert result == '[services]\nembed = "openai"\nstore = "pgvector"\n'
    assert tomllib.loads(result)["services"]["embed"] == "openai"


def test_set_config_text_inserts_a_missing_key_into_an_existing_section() -> None:
    text = '[services]\nstore = "pgvector"\n\n[permissions]\ndestroy = "ask"\n'

    result = set_config_text(text, section="services", key="embed", value="openai")

    assert tomllib.loads(result) == {
        "services": {"embed": "openai", "store": "pgvector"},
        "permissions": {"destroy": "ask"},
    }
    # the other section is untouched, byte for byte
    assert '[permissions]\ndestroy = "ask"\n' in result


def test_set_config_text_appends_a_new_section_and_preserves_comments() -> None:
    text = '# a project comment weft config set must never discard\n[packs.weft-store]\ndsn = "x"\n'

    result = set_config_text(text, section="services", key="embed", value="openai")

    assert "# a project comment weft config set must never discard" in result
    assert tomllib.loads(result)["services"]["embed"] == "openai"
    assert tomllib.loads(result)["packs"]["weft-store"]["dsn"] == "x"


def test_set_config_text_on_an_empty_file_writes_a_minimal_document() -> None:
    result = set_config_text("", section="services", key="embed", value="openai")

    assert tomllib.loads(result) == {"services": {"embed": "openai"}}


def test_set_config_text_never_matches_a_commented_out_key() -> None:
    text = '[services]\n# embed = "openai"\nstore = "pgvector"\n'

    result = set_config_text(text, section="services", key="embed", value="hash")

    # the comment survives untouched, and the real key is inserted freshly
    assert '# embed = "openai"' in result
    assert tomllib.loads(result)["services"]["embed"] == "hash"
