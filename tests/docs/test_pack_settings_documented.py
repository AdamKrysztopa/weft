"""Every field a shipped pack's `Settings` model exposes is named in `weft.toml.example`.

Carried repair **R9.6** (`docs/internal/lessons.md` `L9.77`). A pack's settings block is the surface
an operator configures the pack through, and `weft.toml.example` is the only place this project
shows them one after another — `manual/operations-guide.md` explains *why* a few of them exist, and
`weft plugins doctor` names one only once it has already failed. So a field absent from the example
is a field an operator has no way to discover short of reading the pack's source.

**The instance that filed it**: `[packs.openai]` documented `api_key` and not `base_url` — the
field `weft_openai.settings.Settings`, `manual/troubleshooting.md` and `10` §4 all argue decides
where every request goes, and whose whole point is that it lives in `weft.toml` rather than in
the environment. Measured when this check was written: **thirteen of fourteen** fields across
five packs were undocumented, including every one `weft_kg` shipped in Phase 11.

**Why the example rather than the manuals.** `weft.toml.example` is checked in beside the file it
is an example of, and `tests/docs/test_manual_config_keys.py` already reads it as one of the
documents `[services]` keys may be named in. A field documented in prose somewhere and absent
here is still a field the operator copying this file will not have.

**The set is read from the packs, never from a list here.** `entry_points(group="weft.packs")`
is the same source `weft_kernel.discovery` walks, so a pack added tomorrow is checked without an
edit to this file — the derivation, not an inventory (`L8.8`).
"""

from __future__ import annotations

import importlib
import re
from importlib.metadata import entry_points
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_EXAMPLE: Final[Path] = REPO_ROOT / "weft.toml.example"

#: A settings field deliberately absent from `weft.toml.example`, and why. **Pinned empty**, and
#: it reached empty by the thirteen being *written* rather than recorded. An entry here is a
#: visible act in a diff and needs a fact behind it — "an operator would never set this" is a
#: claim about somebody else's project, not about this one.
SETTINGS_FIELDS_DELIBERATELY_UNDOCUMENTED: Final[frozenset[tuple[str, str]]] = frozenset()


def _shipped_settings_fields() -> dict[str, tuple[str, ...]]:
    """`{pack: (field, ...)}` for every installed pack that exposes a `Settings` model.

    A pack whose module will not import contributes nothing and is not an error here: that is
    an extra the developer environment does not have, and `weft plugins doctor` is where that
    fact belongs. In this repository's own environment every extra is installed, so the walk
    sees all of them — which `test_the_check_can_actually_fail` asserts rather than assumes.
    """
    found: dict[str, tuple[str, ...]] = {}
    for entry in sorted(entry_points(group="weft.packs"), key=lambda e: e.name):
        fields = _settings_fields_of(entry.value.split(":")[0])
        if fields:
            found[entry.name] = fields
    return found


def _settings_fields_of(module_name: str) -> tuple[str, ...]:
    """`Settings.model_fields` for one pack module, or `()` where there is nothing to read.

    **`ImportError` alone, never a bare `except`.** An absent optional extra is exactly an
    `ImportError` (`ModuleNotFoundError` is one), and it is the single case this check is
    willing to pass over. A pack that raises something *else* at import is a real defect and
    belongs in the traceback rather than silently out of the population — `weft_kernel.discovery`
    is where "a pack's import can raise anything; that is FAILED, not a crash" is the right
    posture, and a check counting what a wheel ships is not that place.
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return ()
    settings = getattr(module, "Settings", None)
    fields = getattr(settings, "model_fields", None)
    return tuple(fields) if fields else ()


def _block_for(pack: str, example: str) -> str:
    """The `[packs.<pack>]` block of `weft.toml.example`, commented lines included.

    Bounded at the next `[` at a line start, so a field named in a *later* block cannot answer
    for this one — the failure mode a whole-file `in` test would have, and the reason this is a
    block reader rather than a substring search.
    """
    match = re.search(
        rf"^#?\s*\[packs\.{re.escape(pack)}\](.*?)(?=^#?\s*\[|\Z)", example, re.S | re.M
    )
    return match.group(1) if match else ""


def _is_named(field: str, block: str) -> bool:
    """Whether `block` names `field` as a key — `field = …`, commented out or not.

    Commented is enough on purpose: `weft.toml.example` shows most of its keys commented, so an
    operator uncomments what they need. What this refuses is a field the file never mentions.
    """
    return re.search(rf"^\s*#?\s*{re.escape(field)}\s*=", block, re.M) is not None


def test_every_shipped_pack_settings_field_is_named_in_the_example() -> None:
    example = CONFIG_EXAMPLE.read_text(encoding="utf-8")
    missing = [
        f"[packs.{pack}] {field}"
        for pack, fields in _shipped_settings_fields().items()
        for field in fields
        if (pack, field) not in SETTINGS_FIELDS_DELIBERATELY_UNDOCUMENTED
        and not _is_named(field, _block_for(pack, example))
    ]
    assert not missing, (
        "a shipped pack exposes a settings field `weft.toml.example` never names, so an "
        "operator has no way to discover it short of reading the pack's source:\n  "
        + "\n  ".join(sorted(missing))
        + "\nAdd it to that pack's block — commented out is fine — or name it in "
        "SETTINGS_FIELDS_DELIBERATELY_UNDOCUMENTED with the reason."
    )


def test_the_check_can_actually_fail() -> None:
    # Two floors. The population is non-empty and reaches the packs whose fields are optional
    # extras — a walk that quietly skipped `openai` and `qdrant` would pass while saying nothing
    # about the two packs that filed this repair. And the block reader refuses a field named in
    # somebody else's block, which is what a whole-file substring test would have accepted.
    fields = _shipped_settings_fields()
    assert fields, "no pack exposed a Settings model at all — the entry-point walk is broken."
    reachable = {pack for pack, names in fields.items() if names}
    assert {"openai", "graph"} <= reachable, (
        f"the walk did not reach `openai` and `graph`, whose undocumented fields filed this "
        f"repair. Reached with fields: {sorted(reachable)}."
    )

    example = "[packs.alpha]\nroot = 1\n\n[packs.beta]\nother = 2\n"
    assert _is_named("root", _block_for("alpha", example))
    assert not _is_named("root", _block_for("beta", example)), (
        "a field named in another pack's block answered for this one — the bound is broken."
    )
    assert _is_named("root", '# root = "/tmp/blobs"\n'), "a commented key must still count."
