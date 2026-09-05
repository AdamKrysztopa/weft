"""Unit tests for `weft_generate.__init__`.

Mirrors `packages/weft-rag/src/weft_generate/__init__.py`. Task 2.4 published
`Generator` and registered nothing under it — that emptiness was itself a stated fact,
held until task 2.9 shipped the first plugin (`cited-answer`) and, in the same commit,
the `weft.packs` entry point fitness function 2 requires of a distribution that is active
*and contributing*. Same shape as `tests/unit/weft_retrieve/test_init.py`, whose 2.13/2.7
tests this update carries forward one pack over.
"""

import ast
import tomllib
from pathlib import Path

import weft_generate
from weft_generate.cited_answer import CitedAnswer
from weft_generate.contract import Generator
from weft_generate.contradiction import ContradictionCheck
from weft_generate.prompts import (
    ANSWER_WITH_CITATIONS_NAME,
    CONTRADICTION_ANSWER_NAME,
    CONTRADICTION_CRITIC_NAME,
    AnswerWithCitationsPrompt,
    ContradictionAnswerPrompt,
    ContradictionCriticPrompt,
)
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_prompts.contract import Prompt

_PYPROJECT = Path(__file__).resolve().parents[3] / "packages" / "weft-rag" / "pyproject.toml"

#: The distribution that ships this pack — `weft-generate` until 2026-09-05, `weft-rag` since,
#: which carries fourteen packs in one wheel (`packages/weft-rag/pyproject.toml`).
_SRC = Path(__file__).resolve().parents[3] / "packages" / "weft-rag" / "src"


def _first_party_imports(package: str) -> set[str]:
    """Every first-party top-level module `package`'s own source imports.

    **This replaces a manifest read.** The dependency assertions below used to read
    `packages/weft-rag/pyproject.toml`'s `dependencies` list, which stopped existing when
    the fourteen packs became one distribution — there is no longer a declaration between two
    of them to omit. What the manifest was a proxy for is the real rule
    (`.phase2-design.md` §2's one-way chain), and that rule is about *imports*, so this reads
    them directly. Strictly closer to the property than the list it replaces, and weaker in one
    stated way: an undeclared dependency can no longer break an install, because there is no
    install boundary between these packs any more.
    """
    modules: set[str] = set()
    for path in sorted((_SRC / package).rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return {name for name in modules if name.startswith("weft_") and name != package}


def test_the_contract_this_distribution_publishes_is_exported() -> None:
    # Act / Assert
    assert "Generator" in weft_generate.__all__
    assert weft_generate.Generator is Generator


def test_the_pack_entry_point_is_declared_now_that_something_is_registered() -> None:
    # Arrange
    with _PYPROJECT.open("rb") as handle:
        document = tomllib.load(handle)

    # Act / Assert — the line landed in the commit that shipped the first plugin (2.9), and
    # moved into `weft-rag`'s own manifest with the code on 2026-09-05. The pack name is
    # unchanged, because a pack's identity is its entry-point name and never its distribution.
    assert document["project"]["entry-points"]["weft.packs"]["generate"] == "weft_generate:register"


def test_register_adds_cited_answer_and_the_prompt_it_asks() -> None:
    # Arrange — one `register()`, no privileged path: the `Prompt` goes through the same
    # `PackRegistrar` the `Generator` does, because a prompt belongs to the plugin that
    # asks the question (the 2.10 ledger line), exactly as `weft_retrieve.register` does.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-generate")

    # Act
    weft_generate.register(registrar, weft_generate.Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Generator, "cited-answer")
    assert entry.distribution == "weft-generate"
    assert isinstance(entry.factory(None), CitedAnswer)
    assert isinstance(
        registry.entry(Prompt, ANSWER_WITH_CITATIONS_NAME).factory(None),
        AnswerWithCitationsPrompt,
    )


def test_register_adds_contradiction_check_and_the_two_prompts_it_asks() -> None:
    # Arrange — task 2.22's own plugin, registered the same way and through the same
    # `PackRegistrar` as `cited-answer` above: no privileged path for a built-in.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-generate")

    # Act
    weft_generate.register(registrar, weft_generate.Settings())
    registrar.commit()

    # Assert
    entry = registry.entry(Generator, "contradiction-check")
    assert entry.distribution == "weft-generate"
    assert isinstance(entry.factory(None), ContradictionCheck)
    assert isinstance(
        registry.entry(Prompt, CONTRADICTION_CRITIC_NAME).factory(None),
        ContradictionCriticPrompt,
    )
    assert isinstance(
        registry.entry(Prompt, CONTRADICTION_ANSWER_NAME).factory(None),
        ContradictionAnswerPrompt,
    )


def test_the_dependency_runs_one_way_along_the_pipeline_and_never_back() -> None:
    # Act / Assert — `weft_generate` may import `weft_retrieve`; the reverse would make the
    # first-party graph cyclic, which is why `Answer` is published here and reached from a
    # retrieval-shaped technique through `StageLookup` rather than through an import.
    #
    # **Checked against imports, not against two manifests.** Both packs ship in one wheel now,
    # so there is no dependency declaration between them left to read — and the cycle the rule
    # forbids was always a cycle of imports. `.phase2-design.md` §2's one-way chain is
    # unaffected by how the code is wheeled.
    assert "weft_retrieve" in _first_party_imports("weft_generate")
    assert "weft_generate" not in _first_party_imports("weft_retrieve")


def test_the_pack_imports_exactly_the_packs_whose_types_its_contracts_name() -> None:
    # Act / Assert — `weft_llm` and `weft_prompts` joined at task 2.9: `cited-answer` asks a
    # registered prompt and answers through the run's `LLM` service, upstream of this pack on
    # `.phase2-design.md` §2's one-way chain. `weft_store` was already here for `Citation.uri`
    # resolution through `NodeStore.get_source`. Read from imports — see `_first_party_imports`.
    assert _first_party_imports("weft_generate") == {
        "weft_kernel",
        "weft_store",
        "weft_retrieve",
        "weft_llm",
        "weft_prompts",
    }
