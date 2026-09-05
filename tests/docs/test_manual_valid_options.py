"""A `valid_options` tuple quoted in a manual is the live one — ledger task **8.16**.

`docs/lessons-archive.md` `L8.3`. `manual/troubleshooting.md` reproduces, for several errors, the
exact typed field a caller would read off the exception — `exc.valid_options == ("embed",
"store")` — and that transcript went stale when a third key was added. The whole gate was green:
`docs/08-manuals.md` §3 says a manual is checked rather than trusted, and this was the one thing
nothing checked, because a **tuple literal inside prose** is not a `[services]` key mention and
`test_manual_config_keys.py` reads only the latter.

The distinction matters and is why that check does not cover this one. `test_manual_config_keys.py`
asks *"is every key this page names one `weft.toml` accepts?"* — a subset question, which stays true
when the accepted set **grows**. This asks *"is the tuple this page prints the tuple the code
produces?"*, which is equality, and equality is what a reader copying the transcript relies on.

**Every source below is derived, never retyped.** Three come from a pydantic model's own
`model_fields` and one from the registry the CLI actually builds — so an option added or renamed
anywhere fails this test instead of rotting in a page. `_SOURCES` maps a troubleshooting section to
the derivation for its own tuple, and the two-way ratchet in
`test_every_quoted_tuple_has_a_live_source` refuses a quoted tuple this file has no source for:
without it, the next `valid_options` transcript somebody writes would simply not be checked, which
is the failure this file exists to end rather than to reproduce one level up.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
TROUBLESHOOTING: Final[Path] = REPO_ROOT / "manual" / "troubleshooting.md"

#: `exc.valid_options == ("a", "b")` as the manuals write it, wrapped or not. The page wraps at
#: 100 columns and these transcripts routinely break across a line, so the body is matched with
#: `re.DOTALL` over a whitespace-collapsed copy — `docs/lessons.md` L6.16's own correction, where
#: a sweep that could not cross a line break had a false negative built into the house style.
_QUOTED_TUPLE: Final[re.Pattern[str]] = re.compile(
    r"valid_options\s*==\s*\((?P<body>[^)]*)\)", re.DOTALL
)

#: One `### \`SomeError\`` heading.
_SECTION: Final[re.Pattern[str]] = re.compile(r"^### `(?P<name>\w+)`", re.MULTILINE)


def _service_keys() -> tuple[str, ...]:
    from weft_cli.services import ServiceSelection

    return tuple(sorted(ServiceSelection.model_fields))


def _permission_keys() -> tuple[str, ...]:
    from weft_cli.permission_policy import PermissionPolicy

    return tuple(sorted(PermissionPolicy.model_fields))


def _llm_keys() -> tuple[str, ...]:
    from weft_cli.llm_roles import LLMSection

    return tuple(sorted(LLMSection.model_fields))


def _reconcile_keys() -> tuple[str, ...]:
    from weft_cli.reconcile_policy import ReconcilePolicy

    return tuple(sorted(ReconcilePolicy.model_fields))


def _registered_embedders() -> tuple[str, ...]:
    from weft_cli.registry_bootstrap import build_dependencies
    from weft_embed import Embedder

    return tuple(sorted(build_dependencies().registry.names_for(Embedder)))


#: Troubleshooting section → the live tuple its own transcript must equal. Every entry is a
#: derivation, so nothing here is a second copy of an option list.
_SOURCES: Final[Mapping[str, Callable[[], tuple[str, ...]]]] = {
    "UnknownServiceKeyError": _service_keys,
    "UnknownPermissionKeyError": _permission_keys,
    "UnknownLLMKeyError": _llm_keys,
    "UnknownReconcileKeyError": _reconcile_keys,
    "UnresolvedPluginNameError": _registered_embedders,
}


def _quoted_tuples() -> dict[str, tuple[str, ...]]:
    """Every `### <Error>` section that quotes a `valid_options` tuple, and the tuple it quotes."""
    text = TROUBLESHOOTING.read_text(encoding="utf-8")
    headings = [(match.start(), match.group("name")) for match in _SECTION.finditer(text)]
    found: dict[str, tuple[str, ...]] = {}
    for match in _QUOTED_TUPLE.finditer(text):
        owning = [name for start, name in headings if start < match.start()]
        if not owning:
            continue
        options = tuple(
            part.strip().strip('"').strip("`")
            for part in match.group("body").split(",")
            if part.strip()
        )
        found[owning[-1]] = options
    return found


def test_every_quoted_tuple_equals_the_live_one() -> None:
    # Arrange
    quoted = _quoted_tuples()

    # Act
    wrong = {
        name: {"manual": options, "live": _SOURCES[name]()}
        for name, options in quoted.items()
        if name in _SOURCES and options != _SOURCES[name]()
    }

    # Assert
    assert not wrong, (
        f"these troubleshooting transcripts print a valid_options tuple the code no longer "
        f"produces: {wrong}. A reader copies that tuple; a stale one sends them to a name that "
        f"does not resolve, which is worse than no remedy (lessons-archive L8.3)."
    )


def test_every_quoted_tuple_has_a_live_source() -> None:
    # The ratchet. Without it a new `valid_options` transcript is simply not checked, and this
    # file would reproduce one level up the exact failure it exists to end.
    unsourced = sorted(set(_quoted_tuples()) - set(_SOURCES))
    assert not unsourced, (
        f"these sections quote a valid_options tuple and this check has no derivation for them: "
        f"{unsourced}. Add one to _SOURCES — deriving it from whatever produces the real tuple, "
        f"never retyping the options here."
    )


def test_the_sweep_found_the_transcripts() -> None:
    # `docs/lessons.md` L5.19: a sweep matching nothing passes identically to one finding
    # nothing wrong. Both halves — that tuples were found, and that each source resolves to a
    # non-empty tuple, so an equality against `()` cannot pass vacuously.
    quoted = _quoted_tuples()
    assert quoted, "no valid_options transcripts found — the sweep read nothing"
    assert set(_SOURCES) <= set(quoted), (
        f"_SOURCES names sections that quote no tuple: {sorted(set(_SOURCES) - set(quoted))}"
    )
    for name, source in _SOURCES.items():
        assert source(), f"the live source for {name} is empty, so its comparison is vacuous"


def test_the_check_can_actually_fail() -> None:
    # Plant the exact shape: a transcript whose tuple disagrees with its source.
    planted = 'catching it gives `exc.valid_options == ("nonesuch", "alsomissing")`, a typed field'

    match = _QUOTED_TUPLE.search(planted)
    assert match is not None, "the matcher does not fire on a quoted valid_options tuple"
    options = tuple(part.strip().strip('"') for part in match.group("body").split(","))
    assert options == ("nonesuch", "alsomissing")
    assert options != _service_keys(), (
        "the planted tuple equals a live source, so this self-test proves nothing"
    )
