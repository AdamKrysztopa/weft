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
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from weft_cli.services import ServiceSelection

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANUAL_DIR: Final[Path] = REPO_ROOT / "manual"
CONFIG_EXAMPLE: Final[Path] = REPO_ROOT / "weft.toml.example"

#: `08` §3's named-waiver convention for this check: a `[services]` key a manual names on purpose
#: while it is not yet a field. **Pinned empty** — a key that does not exist is not a remedy, and
#: documenting one ahead of the task that builds it is the drift this test was written for.
SERVICES_KEYS_DOCUMENTED_BEFORE_THEY_EXIST: Final[frozenset[str]] = frozenset()

#: `[services] embed` written inline in prose, the form a remedy sentence uses.
_INLINE = re.compile(r"\[services\][ \t]+([A-Za-z_][A-Za-z0-9_]*)")
#: A `[services]` table header, and the assignments that follow it until the next table or blank.
_TABLE_HEADER = re.compile(r"^#?\s*\[services\]\s*$")
_ASSIGNMENT = re.compile(r"^#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _documents() -> tuple[Path, ...]:
    return (*sorted(MANUAL_DIR.glob("*.md")), CONFIG_EXAMPLE)


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
    """A remedy naming a key `weft.toml` refuses is a remedy that fails on the operator."""
    # Arrange
    accepted = frozenset(ServiceSelection.model_fields) | SERVICES_KEYS_DOCUMENTED_BEFORE_THEY_EXIST

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
