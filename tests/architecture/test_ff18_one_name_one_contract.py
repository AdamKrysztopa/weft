"""Fitness function **18** — a plugin name resolves to exactly one contract. Ledger task 8.15.

`01` → *Fitness functions* item 18 carries the argument; this file is the check. A pipeline
document selects a plugin by bare name and by nothing else — G3 settled that, and it is what keeps
pipelines data rather than packaging. The corollary went unstated for eight phases: **a name that
answers to two contracts cannot be selected by a document at all.** `weft_cli.compile._contract_for`
scans every registered contract for the name and refuses when more than one matches, because there
is nothing in the grammar that says which was meant — so such a plugin is registered, listed by
`weft plugins list`, catalogued, and placeable by nobody. `01` item 11's own shape.

**Why this is a rule and not just a repair.** Of the **107** plugin names this tree registers,
exactly **one** was ever under two contracts — `openai`, as both `Embedder` and `LLMProvider`,
found by running the binary while building task 8.8's demonstration. This check codifies what the
tree already does 106 times out of 107; it imposes nothing new on it.

**What this cannot check, stated rather than implied.** `weft_kernel.registry.Registry.add` keys on
`(contract, name)` and deliberately permits the pair — that is how a first-party pack produced the
shape in the first place — so a third party's pack can still ship it and will meet
`AmbiguousStageContractError` at document resolution rather than at discovery. Refusing it in the
kernel, or reporting it at `weft plugins doctor` on `bertscore`'s own precedent, is the stronger
answer and is filed on ledger 8.15 rather than built here: no third-party instance exists to shape
it. This check's subject is the registry *this* tree builds.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Final

from weft_cli.registry_bootstrap import build_dependencies
from weft_kernel.registry import Registry

#: Names permitted to answer to more than one contract. **Pinned empty**, and it reached empty by
#: the one real violation being renamed rather than recorded — `openai`'s `Embedder` became
#: `openai-embeddings` at ledger 8.15, leaving `openai` to the `LLMProvider` that reads as a
#: vendor because it is one. An entry here is a visible act in a diff, never a silent edit.
NAMES_UNDER_SEVERAL_CONTRACTS_WAIVED: Final[frozenset[str]] = frozenset()


def _contracts_by_name(registry: Registry) -> Mapping[str, tuple[str, ...]]:
    """Invert the registry: every registered plugin name, to the contracts answering for it.

    Read off `Registry.contracts()`/`names_for()` — the same two methods `weft_cli.compile.
    _contract_for` uses to decide a document's stage, so this asks the question the resolver
    actually asks rather than a second, hand-rolled approximation of it.
    """
    found: defaultdict[str, set[str]] = defaultdict(set)
    for contract in registry.contracts():
        for name in registry.names_for(contract):
            found[name].add(contract.__name__)
    return {name: tuple(sorted(contracts)) for name, contracts in found.items()}


def test_no_registered_name_answers_to_more_than_one_contract() -> None:
    # Arrange — the registry the CLI itself builds at process start, never a hand-assembled one:
    # the property is about what an operator's `weft` can actually resolve.
    registry = build_dependencies().registry

    # Act
    by_name = _contracts_by_name(registry)
    ambiguous = {
        name: contracts
        for name, contracts in by_name.items()
        if len(contracts) > 1 and name not in NAMES_UNDER_SEVERAL_CONTRACTS_WAIVED
    }

    # Assert
    assert not ambiguous, (
        f"these plugin names answer to more than one contract, so no pipeline document can "
        f"select them — `use: <name>` is refused by weft_cli.compile._contract_for with nothing "
        f"in the grammar to disambiguate: "
        f"{ {name: list(contracts) for name, contracts in sorted(ambiguous.items())} }. "
        f"Rename one of the two registrations; `01` -> Fitness functions item 18 and ledger 8.15 "
        f"carry why a document-side qualifier is not the answer."
    )


def test_the_registry_this_check_reads_is_the_populated_one() -> None:
    # `docs/lessons.md` L5.19: a check whose subject is empty passes while looking at nothing.
    # This one's subject is never legitimately empty — the tree registers a hundred-odd names —
    # so the guard is that the inversion actually saw them, which is what separates "no name is
    # ambiguous" from "no name was read".
    by_name = _contracts_by_name(build_dependencies().registry)

    assert len(by_name) > 50, (
        f"the registry inversion found only {len(by_name)} names, so a green from "
        f"test_no_registered_name_answers_to_more_than_one_contract would be reporting on an "
        f"almost-empty registry rather than on this tree"
    )
    assert all(contracts for contracts in by_name.values()), (
        "a name mapped to no contract at all, which means the inversion is not reading what it "
        "thinks it is reading"
    )


def test_the_check_can_actually_fail() -> None:
    # The non-vacuity question for this file is not "are there names" — it is "would the
    # inversion *notice* a name under two contracts", which is the only thing the real check
    # depends on. `docs/lessons.md` L6.29: a green from a check that cannot fire is
    # indistinguishable from a green from a check with nothing to find. So this plants the exact
    # shape and asserts the inversion reports it.
    #
    # Planted into a **fresh** `Registry` with two contracts of this test's own, not into the
    # built one. Registering a borrowed name under a borrowed contract was the first attempt and
    # the registry refused it — `MissingDestroysDeclarationError`, because `Cleaner` publishes a
    # property vocabulary every implementation must declare against. That refusal is the registry
    # working, and routing around it with a fake would have been testing something else; two
    # contracts with no declaration requirements exercise the same `Registry.add` and the same
    # `contracts()`/`names_for()` pair the real check reads, which is the whole surface here.

    class _FirstContract:
        """A contract with no property vocabulary — nothing to declare against."""

    class _SecondContract:
        """A second one, so a single name can answer to two."""

    def _factory(config: object = None) -> object:
        del config
        return object()

    registry = Registry()
    registry.add(_FirstContract, "planted", _factory, distribution="weft-planted")
    registry.add(_SecondContract, "planted", _factory, distribution="weft-planted")

    by_name = _contracts_by_name(registry)

    assert by_name["planted"] == ("_FirstContract", "_SecondContract"), (
        f"'planted' was registered under two contracts and the inversion reports "
        f"{by_name.get('planted')} — the check cannot see the defect it exists to catch"
    )
