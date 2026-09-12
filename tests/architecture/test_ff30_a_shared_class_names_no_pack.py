"""Fitness function **30** — a class two packs register names neither of them as a literal.

`docs/internal/lessons.md` **L16.5**, paid for at Phase 20a task `20.2`. `weft_openai`'s three
plugins each refused a missing credential with a sentence naming `[packs.openai]` as a literal.
That was true for as long as one pack registered them. Task `20.1` registered the same three
classes under a second account, and the refusal for an unconfigured `[packs.openai-compatible]`
read:

    no OpenAI credential is configured, so the 'openai' embedder has nothing to authenticate
    with. Add `[packs.openai] api_key = "${env:OPENAI_API_KEY}"` to weft.toml

— sending an operator to four lines that were already correct, which is `L8.3`'s rule exactly: a
remedy naming the wrong thing is worse than no remedy. Nothing failed. 2,628 tests were green,
both packs reported `active`, and the sentence was well formed. It was found by running the
binary's failure path because `20.2`'s Exit clause had been written to demand it.

**Why the check is this narrow, and the two numbers that decided it.** The wide form — *no pack
module may contain a `[packs.<name>]` literal in a runtime string* — walks **18** sites and would
fail **all 18**, every one of them correct: a pack with exactly one account is entitled to name
its own block in a disclosure or an error, and that is what `weft_kg`, `weft_qdrant`, `weft_otel`,
`weft_blob`, `weft_docling`, `weft_store` and `weft_cli` all do. A check that fails eighteen
correct sites and catches nothing is `R10.2`'s worked example, which went four-to-one against
mechanising for the same reason.

What actually makes such a literal wrong is not the string, it is the **registration**: a class
reachable from more than one pack cannot know which `[packs.*]` block configured the instance it
was handed, so any block name it composes is a guess that is right at most half the time. That
population is computable, it is small, and it is exactly where the defect lives. Walks **3**
classes today (`OpenAIEmbedder`, `OpenAILLMProvider`, `OpenAIVisionDescriber`, each registered by
`weft_openai` and `weft_openai_compatible`) and fails **0**, because the repair at `20.2` threaded
the account through all three.

**The floor matters more than usual here.** A tree where no class is shared registers nothing for
this check to walk, and the assertion would pass by describing an empty set — so
`test_at_least_one_class_is_registered_by_two_packs` is what separates "nothing is wrong" from
"nothing is being looked at".
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGES: Final[Path] = REPO_ROOT / "packages"

#: A shared class permitted to name a pack block anyway, with the fact that makes it so.
#: **Pinned empty**, and it reached empty by the repair landing rather than by being recorded —
#: an entry here is a visible act in a diff and needs a reason a reader can check.
SHARED_CLASSES_ALLOWED_TO_NAME_A_PACK: Final[frozenset[str]] = frozenset()

_BLOCK: Final[re.Pattern[str]] = re.compile(r"\[packs\.[a-z0-9-]+\]")

#: `partial(SomeClass, ...)` and `registrar.add(Contract, NAME, SomeClass)` — the two shapes a
#: `register()` in this tree uses to hand a class to the registry. Read off the source rather
#: than by importing, because an optional extra that is absent must not remove a pack from this
#: check's population: a pack invisible here is a pack whose literals go unexamined.
_HANDED_OVER: Final[re.Pattern[str]] = re.compile(
    r"partial\(\s*([A-Z][A-Za-z0-9_]*)|registrar\.add\(\s*\w+,\s*[\w.]+,\s*([A-Z][A-Za-z0-9_]*)\)"
)


def _packs_registering_each_class() -> dict[str, set[str]]:
    """`{class name: {pack module, ...}}` for every class a `register()` hands the registry."""
    found: dict[str, set[str]] = defaultdict(set)
    for init in sorted(PACKAGES.glob("*/src/*/__init__.py")):
        for match in _HANDED_OVER.finditer(init.read_text(encoding="utf-8")):
            name = match.group(1) or match.group(2)
            if name:
                found[name].add(init.parent.name)
    return found


def _runtime_strings_naming_a_pack(module: Path) -> tuple[str, ...]:
    """Every non-docstring string literal in `module` that spells a `[packs.<name>]` block.

    Docstrings are excluded deliberately: prose explaining *why* a pack's own block is shaped as
    it is belongs in the module that explains it, and it is never handed to an operator as a
    remedy. What this refuses is a block name an operator is told to go and edit.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and ast.get_docstring(node, clean=False) is not None
    }
    try:
        shown = module.relative_to(REPO_ROOT)
    except ValueError:  # a planted fixture outside the tree — `test_the_check_can_actually_fail`
        shown = module
    return tuple(
        f"{shown}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and _BLOCK.search(node.value)
    )


def _module_defining(class_name: str) -> Path | None:
    for source in sorted(PACKAGES.glob("*/src/*/*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return source
    return None


def _shared_classes() -> dict[str, set[str]]:
    return {
        name: packs
        for name, packs in _packs_registering_each_class().items()
        if len(packs) > 1 and name not in SHARED_CLASSES_ALLOWED_TO_NAME_A_PACK
    }


def test_at_least_one_class_is_registered_by_two_packs() -> None:
    """Floor — with no shared class the assertion below describes an empty set and means nothing."""
    # Arrange / Act / Assert
    assert _shared_classes(), (
        "no class in this tree is registered by more than one pack, so fitness function 30 has "
        "nothing to walk and its main assertion is vacuous"
    )


def test_no_class_two_packs_register_names_a_pack_block_in_a_runtime_string() -> None:
    # Arrange
    offenders: list[str] = []

    # Act
    for name, packs in sorted(_shared_classes().items()):
        module = _module_defining(name)
        if module is None:
            continue
        for site in _runtime_strings_naming_a_pack(module):
            offenders.append(f"{site} — {name} is registered by {sorted(packs)}")

    # Assert
    assert not offenders, (
        "a class more than one pack registers spells a `[packs.<name>]` block into a runtime "
        "string. It cannot know which block configured the instance it was handed, so that name "
        "is right for at most one of its packs and sends every other operator to a block that is "
        "already correct (`docs/internal/lessons.md` L16.5, L8.3):\n  " + "\n  ".join(offenders)
    )


def test_the_waiver_is_empty() -> None:
    # Arrange / Act / Assert — a ratchet, so widening it shows up in a diff.
    assert frozenset() == SHARED_CLASSES_ALLOWED_TO_NAME_A_PACK


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """The pre-`20.2` shape, planted: the literal this check exists to refuse."""
    # Arrange
    planted = tmp_path / "planted.py"
    planted.write_text(
        '"""A docstring naming [packs.openai], which is fine and must not be caught."""\n'
        "\n"
        "class OpenAIEmbedder:\n"
        "    def refuse(self) -> str:\n"
        '        return "Add `[packs.openai] api_key = ...` to weft.toml"\n',
        encoding="utf-8",
    )

    # Act
    sites = _runtime_strings_naming_a_pack(planted)

    # Assert — the runtime string is caught and the docstring above it is not, which is the
    # distinction the check turns on rather than an incidental detail of the fixture.
    assert len(sites) == 1, sites
    assert sites[0].endswith(":5")
