"""Unit tests for `weft_generate.__init__`.

Mirrors `packages/weft-generate/src/weft_generate/__init__.py`. Task 2.4 published
`Generator` and registered nothing under it — that emptiness was itself a stated fact,
held until task 2.9 shipped the first plugin (`cited-answer`) and, in the same commit,
the `weft.packs` entry point fitness function 2 requires of a distribution that is active
*and contributing*. Same shape as `tests/unit/weft_retrieve/test_init.py`, whose 2.13/2.7
tests this update carries forward one pack over.
"""

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

_PYPROJECT = Path(__file__).resolve().parents[3] / "packages" / "weft-generate" / "pyproject.toml"


def test_the_contract_this_distribution_publishes_is_exported() -> None:
    # Act / Assert
    assert "Generator" in weft_generate.__all__
    assert weft_generate.Generator is Generator


def test_the_pack_entry_point_is_declared_now_that_something_is_registered() -> None:
    # Arrange
    with _PYPROJECT.open("rb") as handle:
        document = tomllib.load(handle)

    # Act / Assert — the line lands in the commit that ships the first plugin (2.9)
    assert document["project"]["entry-points"]["weft.packs"] == {
        "generate": "weft_generate:register"
    }


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
    # Arrange
    with _PYPROJECT.open("rb") as handle:
        generate = tomllib.load(handle)
    retrieve_pyproject = _PYPROJECT.parent.parent / "weft-retrieve" / "pyproject.toml"
    with retrieve_pyproject.open("rb") as handle:
        retrieve = tomllib.load(handle)

    # Act / Assert — `weft-generate` may depend on `weft-retrieve`; the reverse would make
    # the first-party graph cyclic, which is why `Answer` is published here and reached
    # from a retrieval-shaped technique through `StageLookup` rather than through an import.
    assert "weft-retrieve" in generate["project"]["dependencies"]
    assert "weft-generate" not in retrieve["project"]["dependencies"]


def test_the_distribution_declares_the_packs_whose_types_its_contracts_name() -> None:
    # Arrange
    with _PYPROJECT.open("rb") as handle:
        document = tomllib.load(handle)

    # Act / Assert — `weft-llm` and `weft-prompts` joined at task 2.9: `cited-answer` asks
    # a registered prompt and answers through the run's `LLM` service, upstream of this
    # pack on `.phase2-design.md` §2's one-way chain. `weft-store` was already here for
    # `Citation.uri` resolution through `NodeStore.get_source`.
    assert set(document["project"]["dependencies"]) == {
        "weft-kernel",
        "weft-store",
        "weft-retrieve",
        "weft-llm",
        "weft-prompts",
    }
