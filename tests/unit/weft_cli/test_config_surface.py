"""Unit tests for `weft_cli.config_surface`.

Mirrors `packages/weft-rag/src/weft_cli/config_surface.py`. Task **3.7**'s own `--origin`
proof: covers the happy path (no `weft.toml` at all — every key defaults), the edge case a
sentinel-comparison approach cannot express — a value **explicitly** set to what the default
would have been anyway, distinguished from a key genuinely absent — and the error cases of
an unknown key and an illegal `[permissions]` value. `set_config_text` is proven separately:
replacing an existing key, inserting into an existing section, appending a whole new section,
and a round trip through `tomllib` that a comment survives untouched.
"""

from __future__ import annotations

import tomllib

import pytest

from weft_cli.config_surface import (
    ConfigOrigin,
    UnknownConfigKeyError,
    config_entry,
    config_keys_for,
    effective_config,
    set_config_text,
    validate_set_value,
)
from weft_cli.service_roles import RoleTable
from weft_cli.services import UnknownServiceKeyError
from weft_kernel.context import ServiceRole
from weft_kernel.errors import WeftError

# --- effective_config / config_entry ----------------------------------------------------


#: The roles a real installation declares. Stated rather than defaulted: task **9.0** removed
#: `effective_config`'s ability to guess a key set, because a guess that names `embed` and
#: `store` is the closed key space the task deletes, put back one layer down.
_INSTALLED = RoleTable(
    roles={
        "embed": ServiceRole(key="embed", contract=object),
        "store": ServiceRole(key="store", contract=object),
    }
)


def test_no_document_at_all_defaults_every_key() -> None:
    entries = effective_config(None, table=_INSTALLED)

    assert {entry.key for entry in entries} == set(config_keys_for(_INSTALLED))
    assert all(entry.origin is ConfigOrigin.DEFAULT for entry in entries)


def test_a_value_explicitly_set_to_the_default_is_still_origin_file() -> None:
    # A sentinel-comparison approach (`.phase3-design.md` §2.6) could not tell this case apart
    # from "never set at all" — an explicit `embed = "hash"` is indistinguishable from
    # nothing being said, because comparing the merged value against the default throws the
    # provenance away. This is the property that check structurally cannot have.
    document: dict[str, object] = {"services": {"embed": "hash"}}  # "hash" is the default

    entry = config_entry(document, "services.embed", table=_INSTALLED)

    assert entry.value == "hash"
    assert entry.origin is ConfigOrigin.FILE


def test_a_key_the_file_never_mentions_is_origin_default() -> None:
    document: dict[str, object] = {"services": {"store": "qdrant"}}  # embed left unmentioned

    entry = config_entry(document, "services.embed", table=_INSTALLED)

    assert entry.value == "hash"
    assert entry.origin is ConfigOrigin.DEFAULT


def test_config_entry_refuses_an_unknown_key_naming_the_valid_ones() -> None:
    """The set named is **this run's**, not a module constant.

    Repaired at ledger task 9.0, found by running the binary: `weft config get` printed
    `services.route` while `weft config get --key services.route` refused it as "not a key weft
    config reads or writes", because the refusal read the static `CONFIG_KEYS` while the listing
    read the declared role set. Two halves of one command disagreeing, with 2,103 tests green.
    Asserting against `config_keys_for` here is not comparing the check to itself: the point is
    that the refusal and the listing answer from **one** source, and this test fails the moment
    they answer from two.
    """
    with pytest.raises(UnknownConfigKeyError) as exc_info:
        config_entry(None, "services.bogus", table=_INSTALLED)

    assert exc_info.value.valid_options == config_keys_for(_INSTALLED)
    assert "services.route" in exc_info.value.valid_options


def test_reconcile_mode_defaults_to_full_with_no_document() -> None:
    # Task 5.1c: `[reconcile] mode` joins the surface, unchanged default from `weft
    # reconcile`'s own pre-5.1c hardcoded `full`.
    entry = config_entry(None, "reconcile.mode", table=_INSTALLED)

    assert (entry.value, entry.origin) == ("full", ConfigOrigin.DEFAULT)


def test_reconcile_mode_explicitly_set_to_repair_is_origin_file() -> None:
    document: dict[str, object] = {"reconcile": {"mode": "repair"}}

    entry = config_entry(document, "reconcile.mode", table=_INSTALLED)

    assert (entry.value, entry.origin) == ("repair", ConfigOrigin.FILE)


# --- validate_set_value ------------------------------------------------------------------


def test_validate_set_value_accepts_a_plugin_name_for_a_services_key() -> None:
    validate_set_value("services.embed", "openai", table=_INSTALLED)  # does not raise


def test_validate_set_value_refuses_an_empty_plugin_name() -> None:
    with pytest.raises(WeftError, match="services.embed"):
        validate_set_value("services.embed", "", table=_INSTALLED)


def test_validate_set_value_refuses_an_illegal_permissions_value() -> None:
    with pytest.raises(WeftError, match="allow.*ask"):
        validate_set_value("permissions.destroy", "sometimes", table=_INSTALLED)


def test_validate_set_value_accepts_a_legal_reconcile_mode() -> None:
    validate_set_value("reconcile.mode", "repair", table=_INSTALLED)  # does not raise


def test_validate_set_value_refuses_an_illegal_reconcile_mode() -> None:
    with pytest.raises(WeftError, match="full.*repair"):
        validate_set_value("reconcile.mode", "sometimes", table=_INSTALLED)


def test_validate_set_value_refuses_an_unknown_key() -> None:
    with pytest.raises(UnknownConfigKeyError):
        validate_set_value("services.bogus", "x", table=_INSTALLED)


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
    text = '# a project comment weft config set must never discard\n[packs.store]\ndsn = "x"\n'

    result = set_config_text(text, section="services", key="embed", value="openai")

    assert "# a project comment weft config set must never discard" in result
    assert tomllib.loads(result)["services"]["embed"] == "openai"
    assert tomllib.loads(result)["packs"]["store"]["dsn"] == "x"


def test_set_config_text_on_an_empty_file_writes_a_minimal_document() -> None:
    result = set_config_text("", section="services", key="embed", value="openai")

    assert tomllib.loads(result) == {"services": {"embed": "openai"}}


def test_set_config_text_never_matches_a_commented_out_key() -> None:
    text = '[services]\n# embed = "openai"\nstore = "pgvector"\n'

    result = set_config_text(text, section="services", key="embed", value="hash")

    # the comment survives untouched, and the real key is inserted freshly
    assert '# embed = "openai"' in result
    assert tomllib.loads(result)["services"]["embed"] == "hash"


#: A role a pack declares and `ServiceSelection` has no field for — `blob`, `graph` and
#: `describe` are all this shape in a real installation. `_INSTALLED` above holds only `embed`
#: and `store`, which have defaults, so `plugin_for` can never fail against it: the fixture is
#: symmetric in exactly the dimension the two tests below vary (`docs/lessons.md` `L12.6`).
_WITH_AN_UNSELECTED_ROLE = RoleTable(
    roles={
        "embed": ServiceRole(key="embed", contract=object),
        "store": ServiceRole(key="store", contract=object),
        "blob": ServiceRole(key="blob", contract=object),
    }
)


def test_a_declared_role_nothing_selects_is_absent_rather_than_a_crash() -> None:
    # Carried repair **R9.4**, and this is the half no test could see and the binary showed in
    # one command. `weft config get` with no arguments — its default, flagless invocation, on a
    # project with no `weft.toml` at all — exited **1** with
    # `[services] holds no selection for 'blob'. Selected: (none).` Every real installation
    # declares `blob`, `graph` and `describe`, none of which `ServiceSelection` has a field for,
    # so this was every project that had not selected all three: the command was unusable and
    # 2,543 tests were green, because every fixture declared only the two roles that default.
    #
    # `ServiceSelection.roles`' own comment already states the answer — "a key with nothing
    # selected for it is simply absent, never guessed" — so an effective-config listing omits it.
    # An effective configuration is what is *in effect*, and nothing is in effect for that role.
    entries = effective_config(None, table=_WITH_AN_UNSELECTED_ROLE)

    keys = {entry.key for entry in entries}
    assert "services.blob" not in keys
    assert {"services.embed", "services.store", "services.route"} <= keys, (
        "omitting the unselected role took the selected ones with it."
    )
    assert "permissions.overwrite" in keys, "the blocks that name no role are untouched."


def test_asking_for_that_role_by_name_still_says_why_rather_than_unknown_key() -> None:
    # The other side of the same repair, and the reason the listing omits rather than prints a
    # placeholder: `services.blob` **is** a key this run reads — it is in `config_keys_for` and
    # `weft config set` writes it — so answering `UnknownConfigKeyError` would be false. What is
    # missing is a selection, and `ServiceSelection.plugin_for`'s own message names the key and
    # what *is* selected, which is the loud failure correctly located.
    # **Asserted as the exact class, not as the family.** The first version of this test said
    # `pytest.raises(WeftError)` and looked for `"blob"` in the message — and passed against a
    # build where `weft config get --key services.blob` answered *"is not a key weft config
    # reads or writes"* while `weft config set services.blob filesystem` wrote it happily.
    # `UnknownConfigKeyError` is a `WeftError` and its message contains the key, so the loose
    # assertion accepted the sibling error that says the opposite of the truth. The binary
    # found it in one command pair.
    with pytest.raises(UnknownServiceKeyError) as caught:
        config_entry(None, "services.blob", table=_WITH_AN_UNSELECTED_ROLE)

    message = str(caught.value)
    assert "holds no selection" in message, (
        "the refusal must say a *selection* is missing. Saying the key is unknown is false — "
        "`weft config set` writes it — and sends an operator looking for a typo."
    )
    assert not isinstance(caught.value, UnknownConfigKeyError), (
        "`services.blob` is a key this run reads; only its selection is absent."
    )
    assert "services.blob" in config_keys_for(_WITH_AN_UNSELECTED_ROLE), (
        "the key vanished from the vocabulary as well, which would make `weft config set "
        "services.blob` refuse a key an operator is entitled to write."
    )
