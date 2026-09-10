"""Every `[services]` key the shipped manuals name is a key `weft.toml` actually accepts.

`docs/08-manuals.md` §3's rule — a manual is checked, not trusted — applied to the one thing a
troubleshooting page does that no other document does: it tells an operator what to *edit*. A
remedy naming a configuration key that does not exist is worse than no remedy, because
`weft_cli.services.service_selection_from_config` refuses an unknown `[services]` key **by name**
— so following the shipped fix for a shipped error lands the operator in a second, unrelated hard
failure with nothing connecting the two.

This test was written for a reviewer finding against task 2.5: `manual/troubleshooting.md`'s
`StoreCapabilityMissingError` entry offered "`[services] store` in `weft.toml`" when no such key
existed, so following the shipped fix for a shipped error landed the operator in a second failure.
The key exists now — 2.6's own repair added it, for the opposite reason: `weft-qdrant` had shipped
a second registered `NodeStore` that nothing could select. That the check survived the key arriving
is the point of deriving the accepted set from the model instead of listing it here.

**The accepted set is derived from the model, never retyped**, so a key added to
`ServiceSelection` needs no edit here and a key removed from it fails this test rather than
rotting in a manual. Both spellings the documents use are read: the inline `` `[services] embed` ``
prose form, and a `[services]` table inside a fenced block.

**Widened at ledger 11.10, because the model stopped being the whole answer at ledger 9.0.**
`[services]` has not accepted only `ServiceSelection`'s own fields since `9.0`: any installed pack
may declare a **role**, and `weft_cli.services.service_selection_from_config` builds its accepted
key set as `set(table.declared) | {"route"}` — the fields *plus* every role every installed pack
publishes. So a document naming a real, pack-declared key was refused here while `weft.toml`
accepted it, which inverts what this test is for: it existed to stop a manual promising a key that
does not exist, and it had begun refusing keys that do. Found by `weft.toml.example` documenting
`[services] graph`, the role `weft_kg` declares against its own traversal contract.

This is `docs/lessons.md` `L6.4` aimed at a check rather than at a marker: the accepted set is
whatever the **live population** of installed packs declares, not what one model states, and
reading the declaration was right until a task made the population bigger than it. The set is now
read the way the production code reads it — through a real `discover()` pass and
`role_table_from_reports` — so a pack that adds a role needs no edit here either.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from tests.discovery import installed_packs_except_the_canary
from weft_cli.config_surface import config_keys_for
from weft_cli.service_roles import RoleTable, role_table_from_reports
from weft_cli.services import ServiceSelection, accepted_service_keys
from weft_kernel.context import ServiceRole
from weft_kernel.discovery import discover
from weft_kernel.registry import Registry

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANUAL_DIR: Final[Path] = REPO_ROOT / "manual"
CONFIG_EXAMPLE: Final[Path] = REPO_ROOT / "weft.toml.example"
#: **`03` is the document that defines this vocabulary**, and until carried repair `R9.4` this
#: check globbed `manual/*.md` and never opened it — so the one document whose word is final on
#: what `[services]` accepts was the one document not checked against the code. `docs/lessons.md`
#: `L9.35`.
CLI_DOCUMENT: Final[Path] = REPO_ROOT / "docs" / "03-cli.md"

#: `08` §3's named-waiver convention for this check: a `[services]` key a manual names on purpose
#: while it is not yet a field. **Pinned empty** — a key that does not exist is not a remedy, and
#: documenting one ahead of the task that builds it is the drift this test was written for.
SERVICES_KEYS_DOCUMENTED_BEFORE_THEY_EXIST: Final[frozenset[str]] = frozenset()

#: The never-dialled DSN `tests/discovery.py` and fitness functions 11 and 16 all use, for the
#: reason all three state: a store's `__init__` opens no connection, so `register()` runs without
#: a container and every pack's role declaration is a real one here.
_PLACEHOLDER_PACK_SETTINGS: Final[dict[str, dict[str, object]]] = {
    "store": {"dsn": "postgresql://config-keys-placeholder/placeholder"},
    "graph": {"dsn": "postgresql://config-keys-placeholder/placeholder"},
    "blob": {"root": "/nonexistent-blob-root"},
}


def _live_role_table() -> RoleTable:
    """The `RoleTable` a real run builds — `_role_keys`'s own pass, returned whole.

    Carried repair **R9.4** needs the table itself rather than its key set: the property under
    test is that two *surfaces* answer the same question from it, and handing each a different
    table would compare two answers to two questions.
    """
    reports = discover(
        Registry(),
        allow=installed_packs_except_the_canary(),
        pack_settings=_PLACEHOLDER_PACK_SETTINGS,
    )
    return role_table_from_reports(reports)


#: `[services] embed` written inline in prose, the form a remedy sentence uses.
_INLINE = re.compile(r"\[services\][ \t]+([A-Za-z_][A-Za-z0-9_]*)")
#: A `[services]` table header, and the assignments that follow it until the next table or blank.
_TABLE_HEADER = re.compile(r"^#?\s*\[services\]\s*$")
_ASSIGNMENT = re.compile(r"^#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _documents() -> tuple[Path, ...]:
    return (*sorted(MANUAL_DIR.glob("*.md")), CONFIG_EXAMPLE, CLI_DOCUMENT)


def _keys_named_in(text: str) -> frozenset[str]:
    """Every `[services]` key `text` names, in either spelling."""
    named = set(_INLINE.findall(text))
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not _TABLE_HEADER.match(line):
            continue
        for following in lines[index + 1 :]:
            if not following.strip() or following.lstrip("# ").startswith(("[", "```")):
                break
            match = _ASSIGNMENT.match(following)
            if match is not None:
                named.add(match.group(1))
    return frozenset(named)


def _keys_named_in_the_documents() -> dict[Path, frozenset[str]]:
    return {path: _keys_named_in(path.read_text(encoding="utf-8")) for path in _documents()}


def test_at_least_one_services_key_is_found_in_the_documents() -> None:
    """The floor: a scan that matched nothing would pass this file's real check by being blind."""
    # Arrange / Act
    found: frozenset[str] = frozenset[str]().union(*_keys_named_in_the_documents().values())

    # Assert
    assert found, f"no [services] key found in any of {[str(path) for path in _documents()]}"


def test_every_documented_services_key_is_one_weft_toml_accepts() -> None:
    """A remedy naming a key `weft.toml` refuses is a remedy that fails on the operator.

    **Read from `accepted_service_keys` since carried repair `R9.4`, and that closed a gap this
    docstring already forbade.** The set was `ServiceSelection.model_fields | _role_keys()`, and
    `model_fields` carries `roles` — the *mapping* every non-`embed`/`store` selection lives in,
    not a key a `weft.toml` may write. So a manual documenting `[services] roles` would have
    passed here and been refused by `service_selection_from_config` on the operator's machine,
    which is the exact failure the sentence above names. Three expressions of one vocabulary is
    what `R9.4` was filed for; this was the third.
    """
    # Arrange
    accepted = (
        accepted_service_keys(_live_role_table()) | SERVICES_KEYS_DOCUMENTED_BEFORE_THEY_EXIST
    )

    # Act
    unknown = {
        path.relative_to(REPO_ROOT): sorted(named - accepted)
        for path, named in _keys_named_in_the_documents().items()
        if named - accepted
    }

    # Assert
    assert not unknown, (
        f"documents name [services] key(s) weft.toml does not accept: {unknown}. "
        f"[services] accepts {sorted(accepted)}."
    )


def test_a_key_that_does_not_exist_would_be_caught() -> None:
    """The check's own teeth: the scan finds a made-up key in the shape the manuals write."""
    # Arrange
    text = "configure it with `[services] nosuchkey` in `weft.toml`.\n"

    # Act
    named = _keys_named_in(text)

    # Assert
    assert "nosuchkey" in named
    assert "nosuchkey" not in ServiceSelection.model_fields


def test_one_derivation_answers_which_services_keys_exist() -> None:
    # Carried repair **R9.4**, and the property its four lessons share: `[services]`'s key
    # vocabulary had **three** expressions of itself. `weft_cli.services` validated a `weft.toml`
    # against `set(table.declared) | {"route"}`; `weft_cli.config_surface.config_keys_for` built
    # `services.<role>` from `table.declared` and then hand-added `"services.route"` a second
    # time; and this file combined `ServiceSelection.model_fields` with a discovered role set.
    # Three sets that agreed on the day each was written and had no reason to keep agreeing —
    # `config_keys_for`'s own docstring records that `_KEY_FIELDS` had already drifted once, by
    # never growing `services.route` when task 8.3 added it.
    #
    # The dimension this varies is **a role no expression hard-codes**: with only the shipped
    # roles, a hand-written set and a derived one are indistinguishable.
    class _AcmeContract:
        """A contract no pack in this repository publishes — see the comment above."""

    table = RoleTable(
        roles={
            "acme-thing": ServiceRole(key="acme-thing", contract=_AcmeContract),
        }
    )

    # Act
    accepted = accepted_service_keys(table)
    addressable = {
        key.removeprefix("services.")
        for key in config_keys_for(table)
        if key.startswith("services.")
    }

    # Assert — one derivation, so a stranger's role reaches both surfaces or neither.
    assert accepted == addressable
    assert "acme-thing" in accepted, (
        "a role a third-party pack declared is not in the accepted set, so `weft.toml` would "
        "refuse a key the pack itself published."
    )
    assert "route" in accepted, (
        "`route` names a pipeline document rather than a plugin and is accepted anyway — that "
        "is the one member no pack declares, and it belongs in the derivation rather than being "
        "added again by every caller."
    )


def test_the_shipped_key_set_is_the_one_both_surfaces_answer_with() -> None:
    # The live reading of the same property: whatever this installation actually declares, a
    # `weft.toml` and `weft config get|set` agree about which keys exist. They agreed when this
    # was written, which is the point — the check exists so that stays true rather than being
    # rediscovered by an operator whose `weft config set services.graph` is refused for a key
    # their `weft.toml` accepts.
    table = _live_role_table()

    accepted = accepted_service_keys(table)
    addressable = {
        key.removeprefix("services.")
        for key in config_keys_for(table)
        if key.startswith("services.")
    }

    assert accepted == addressable, (
        f"`weft.toml` accepts {sorted(accepted)} and `weft config` addresses "
        f"{sorted(addressable)}. One of the two is a second key space."
    )
    assert accepted, "no `[services]` key was derived at all — the discovery itself is broken."
