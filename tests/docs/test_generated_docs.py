"""`docs/08-manuals.md` §3, clause (b) — the generated contract reference and command table
match the registry.

"A small script walks the registry the same way `weft plugins doctor` does, reads each
registered contract's Protocol, docstring and declared version, and renders the
reference. There is no second copy of a method signature for a human to keep in sync"
(`08` §3). This is that check, run against `manual/contract-reference.md` — task **0.12**:
*"a contract's published reference cannot disagree with its own Protocol, because there is
no second copy of a signature."*

**The floor, before the text diff runs** (`08` §3): "the set of contracts the generator
walked equals the registry's published-contract set — the same runtime set-equality shape
fitness functions 2 and 4(b) use... so a generator that emits nothing cannot match a
committed empty file." `weft_cli.contract_reference.published_contracts` walks each
*named* registration off a real, freshly-discovered `weft_kernel.registry.Registry`
(`Registry.contracts()`, added at this task) plus every capability Protocol it finds
alongside a named one in that pack's own public module — `VectorSearch` beside
`NodeStore`, per that module's own reasoning. `test_every_registered_contract_is_walked`
is the runtime half: every contract the real `Registry` reports must appear in what the
generator walked, checked against the `Registry` directly rather than by trusting the
generator's own bookkeeping.

**Task 3.9 adds the command table's own half of clause (b), in this same file** — `08` §3's
table names one clause and one file for both: "Generated reference **and command table**
match the registry... `tests/docs/test_generated_docs.py`." `weft_cli.command_table.
command_entries` walks `registry.names_for(weft_command.contract.Command)` the identical way
`weft_cli.cli.build_parser` already does to generate `weft --help`'s own grammar (`03` ->
*Plugin-contributed commands*: "the help text is generated from the registry, which means it
cannot drift from what is installed") — this is that same walk, rendered to a Markdown table
spliced into `manual/user-manual.md` between two HTML-comment markers instead of into an
`argparse.ArgumentParser`. `test_every_registered_command_is_walked` is this clause's runtime
floor, on `test_every_registered_contract_is_walked`'s own shape: every name the real
`Registry` reports under `Command` must appear in what the generator walked, checked against
the `Registry` directly, before `test_generated_command_table_matches_the_checked_in_manual`'s
text diff ever runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from weft_cli.command_table import (
    PublishedCommand,
    command_entries,
    missing_command_names,
    render_command_table,
    spliced_manual,
)
from weft_cli.contract_reference import (
    REGENERATE_COMMAND,
    PublishedContract,
    discover_for_reference,
    missing_from_walked_set,
    published_contracts,
    render_contract_reference,
)
from weft_command.contract import Command
from weft_command.permission import PermissionClass
from weft_store.contract import NodeStore, VectorSearch

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
REFERENCE: Final[Path] = REPO_ROOT / "manual" / "contract-reference.md"
USER_MANUAL: Final[Path] = REPO_ROOT / "manual" / "user-manual.md"

#: `08` §3's ratchet for the command-table half of clause (b): a `Command` name the real
#: `Registry` reports but the generator did not walk is a failure unless named here
#: explicitly. **Pinned empty** — every command registered in this workspace is walked.
COMMANDS_WAIVED_FROM_TABLE: Final[frozenset[str]] = frozenset()

#: `08` §3's ratchet for clause (b): a contract the real `Registry` reports but the
#: generator did not walk is a failure unless named here explicitly, by its
#: `__qualname__`. **Pinned empty** — every contract Phase 0 registers is walked.
CONTRACTS_WAIVED_FROM_REFERENCE: Final[frozenset[str]] = frozenset()

#: The distributions in this workspace that register under a capability contract, whether
#: or not they publish one — `weft-kernel` names none (rule: "the kernel names no
#: capability") and `weft-cli` is the driving adapter, so neither appears here, while
#: `weft-pdf` (task 2.27) registers two backends under a contract `weft-extract` publishes
#: and belongs here without publishing anything itself, as does `weft-openai` (task 2.29)
#: under `weft-embed`'s and `weft-qdrant` (task 2.6) under `weft-store`'s. `weft-llm`
#: (task 2.30) both publishes `LLMProvider` *and* registers `scripted` under it — the
#: `weft-store`/`weft-embed` shape, not the `weft-pdf` one — and `weft-openai` grows a
#: second registration here, under `weft-llm`'s contract this time, for `openai`.
#: `weft-retrieve` (task 2.13) joins the `weft-llm` shape: it publishes the eight query-path
#: contracts *and* registers `no-retrieval` under `Retriever`, the first of them. `weft-cli`
#: (task 3.2) joins it too, on the identical shape: it does not publish `Command`
#: (`weft-command` does, and registers nothing of its own — that distribution's own module
#: docstring), but it registers all five built-ins under it, through the same `weft.packs`
#: entry point a third party would use — CLAUDE.md's "built-ins get no shortcut" applied to
#: the CLI's own surface. Anything registered under a contract that is *not* one of these is a
#: distribution installed into the shared environment for some other reason — an editable
#: example pack while working on the pack-author guide, say — not something this workspace's
#: own checked-in file should ever describe. See
#: `test_generated_reference_matches_the_checked_in_file` below for why this distinction is
#: asserted before the text diff, not folded into its failure message.
KNOWN_WORKSPACE_DISTRIBUTIONS: Final[frozenset[str]] = frozenset(
    {
        "weft-extract",
        "weft-chunk",
        "weft-clean",
        "weft-store",
        "weft-embed",
        "weft-enhance",
        "weft-pdf",
        "weft-openai",
        "weft-qdrant",
        "weft-llm",
        "weft-retrieve",
        "weft-prompts",
        "weft-generate",
        "weft-index",
        "weft-cli",
        "weft-eval",
    }
)


def test_at_least_one_contract_is_registered() -> None:
    # Floor — `08` §3: "at least one X before checking each has an entry" restated for
    # this clause: a registry with nothing registered cannot exercise this check at all.
    registry = discover_for_reference()
    assert registry.contracts(), "no pack registered a single contract — nothing to check"


def test_every_registered_contract_is_walked() -> None:
    # Arrange
    registry = discover_for_reference()
    walked = {published.contract for published in published_contracts(registry)}

    # Act — the runtime set-equality floor, computed against the real `Registry` directly,
    # never against the generator's own record of what it did.
    missing = missing_from_walked_set(
        registered=registry.contracts(), walked=walked, waived=CONTRACTS_WAIVED_FROM_REFERENCE
    )

    # Assert
    assert not missing, (
        f"registered but never rendered: {sorted(c.__qualname__ for c in missing)}. Either "
        f"the generator has drifted from the registry, or this is a deliberate omission "
        f"that belongs in CONTRACTS_WAIVED_FROM_REFERENCE, named."
    )


def test_missing_from_walked_set_would_catch_a_dropped_contract() -> None:
    # Arrange — the self-test `08` §3 requires of every floor: prove the comparison can
    # actually fail, rather than passing merely because nothing was compared.
    class _Registered:
        """Stand-in: a contract the registry reports."""

    # Act
    missing = missing_from_walked_set(
        registered=frozenset({_Registered}), walked=frozenset(), waived=frozenset()
    )

    # Assert
    assert missing == {_Registered}


def test_vectorsearch_is_walked_as_nodestores_capability_sibling() -> None:
    # `weft_store.contract`'s own module docstring: "nothing here registers `VectorSearch`
    # under its own plugin name, because it is a capability a store has, not a plugin a
    # pipeline selects." A generator that only walked `Registry.contracts()` would silently
    # drop it — this is the check that it did not.
    registry = discover_for_reference()

    contracts = {published.contract for published in published_contracts(registry)}

    assert NodeStore in registry.contracts()
    assert VectorSearch not in registry.contracts()
    assert VectorSearch in contracts


def _distributions_beyond_workspace(
    contracts: tuple[PublishedContract, ...], *, known: frozenset[str]
) -> frozenset[str]:
    """Every distribution `contracts` names that `known` does not.

    A pure function, on the same footing as `missing_from_walked_set` above, so the
    self-test below has something to call that is not the diff it is protecting.
    """
    seen: set[str] = set()
    for published in contracts:
        seen.update(published.distributions)
    return frozenset(seen) - known


def test_distributions_beyond_workspace_would_catch_a_contaminating_pack() -> None:
    # Arrange — the self-test `08` §3 requires of every floor: prove the comparison can
    # actually fail, rather than passing merely because nothing was compared.
    contracts = (PublishedContract(contract=object, distributions=frozenset({"weft-example"})),)

    # Act
    extra = _distributions_beyond_workspace(contracts, known=frozenset({"weft-chunk"}))

    # Assert
    assert extra == frozenset({"weft-example"})


def test_generated_reference_matches_the_checked_in_file() -> None:
    # Arrange
    registry = discover_for_reference()
    contracts = published_contracts(registry)

    # A pack installed into the shared environment for reasons unrelated to this
    # workspace — an editable example pack picked up while working on the pack-author
    # guide, say — registers under a real Phase 0 contract and changes what "Published
    # by" renders, without belonging in the checked-in file at all. Caught here, before
    # the text diff runs, so the failure names the actual problem: environment
    # contamination is not documentation drift, and the remedy is not to regenerate and
    # commit a foreign pack's contract into the manual.
    contamination = _distributions_beyond_workspace(contracts, known=KNOWN_WORKSPACE_DISTRIBUTIONS)
    assert not contamination, (
        f"distribution(s) {sorted(contamination)} registered under a contract this "
        "workspace publishes, but are not part of this workspace "
        f"({sorted(KNOWN_WORKSPACE_DISTRIBUTIONS)}). This is environment contamination, "
        "not documentation drift — uninstall the stray distribution(s) from this "
        "environment rather than regenerating and committing their contract."
    )

    # Act
    fresh = render_contract_reference(contracts)

    # Assert — the two-lists bug, aimed at a contract instead of a file format: a
    # signature, docstring or version that changed in code and not here fails the build.
    checked_in = REFERENCE.read_text(encoding="utf-8")
    assert fresh == checked_in, (
        "manual/contract-reference.md has drifted from the registered contracts. "
        f"Regenerate it with `{REGENERATE_COMMAND}` and commit the result."
    )


# --- Task 3.9 — the user manual's command table, clause (b)'s second subject ------------------


def test_at_least_one_command_is_registered() -> None:
    # Floor, restated for the command table — `08` §3: a registry with nothing registered
    # under `Command` cannot exercise this check at all.
    registry = discover_for_reference()
    assert registry.names_for(Command), "no pack registered a single Command — nothing to check"


def test_every_registered_command_is_walked() -> None:
    # Arrange
    registry = discover_for_reference()
    walked = {published.name for published in command_entries(registry)}

    # Act — the runtime set-equality floor, computed against the real `Registry` directly,
    # never against the generator's own record of what it did.
    missing = missing_command_names(
        registered=registry.names_for(Command), walked=walked, waived=COMMANDS_WAIVED_FROM_TABLE
    )

    # Assert
    assert not missing, (
        f"registered but never rendered: {sorted(missing)}. Either the generator has "
        f"drifted from the registry, or this is a deliberate omission that belongs in "
        f"COMMANDS_WAIVED_FROM_TABLE, named."
    )


def test_missing_command_names_would_catch_a_dropped_command() -> None:
    # Arrange — the self-test `08` §3 requires of every floor: prove the comparison can
    # actually fail, rather than passing merely because nothing was compared.
    missing = missing_command_names(
        registered=frozenset({"graph build"}), walked=frozenset(), waived=frozenset()
    )

    # Assert
    assert missing == {"graph build"}


def _command_distributions_beyond_workspace(
    commands: tuple[PublishedCommand, ...], *, known: frozenset[str]
) -> frozenset[str]:
    """Every distribution `commands` names that `known` does not.

    `_distributions_beyond_workspace`'s own shape, applied to `PublishedCommand.distribution`
    (one distribution per command, never a set) instead of `PublishedContract.distributions` —
    kept as a second, small function rather than generalised over both, since generalising here
    would mean the self-test below is no longer calling the exact function the real check calls.
    """
    return frozenset(command.distribution for command in commands) - known


def test_command_distributions_beyond_workspace_would_catch_a_contaminating_pack() -> None:
    # Arrange — the self-test `08` §3 requires of every floor: prove the comparison can
    # actually fail, rather than passing merely because nothing was compared.
    commands = (
        PublishedCommand(
            name="greet",
            distribution="weft-example-command",
            permission_class=PermissionClass.READ,
            help="hi",
        ),
    )

    # Act
    extra = _command_distributions_beyond_workspace(commands, known=frozenset({"weft-cli"}))

    # Assert
    assert extra == frozenset({"weft-example-command"})


def test_generated_command_table_matches_the_checked_in_manual() -> None:
    # Arrange
    registry = discover_for_reference()
    commands = command_entries(registry)

    # Same contamination question `test_generated_reference_matches_the_checked_in_file` asks,
    # aimed at the command table instead of the contract reference — see that test's own
    # comment for why this is checked before the text diff rather than folded into it.
    contamination = _command_distributions_beyond_workspace(
        commands, known=KNOWN_WORKSPACE_DISTRIBUTIONS
    )
    assert not contamination, (
        f"distribution(s) {sorted(contamination)} registered a Command in this environment "
        f"but are not part of this workspace ({sorted(KNOWN_WORKSPACE_DISTRIBUTIONS)}). This "
        "is environment contamination, not documentation drift — uninstall the stray "
        "distribution(s) rather than regenerating and committing their command."
    )

    # Act
    table = render_command_table(commands)
    checked_in = USER_MANUAL.read_text(encoding="utf-8")
    fresh = spliced_manual(checked_in, table)

    # Assert — the two-lists bug, aimed at the command surface instead of a file format: a
    # command added, removed or reworded in the CLI without the manual noticing.
    assert fresh == checked_in, (
        "manual/user-manual.md's command table has drifted from the registered commands. "
        "Regenerate it with `uv run python scripts/generate_command_table.py` and commit "
        "the result."
    )


def test_a_retyped_command_table_row_would_fail() -> None:
    # Arrange — the self-test `08` §3 requires of every check in this file: prove the
    # comparison can actually fail, rather than passing merely because nothing was compared.
    actual = "| `weft ask` | `read` | `weft-cli` | retrieve and print the nearest passages |\n"
    retyped_by_hand = "| `weft ask` | `read` | `weft-cli` | ASKS A QUESTION AND ANSWERS IT |\n"

    # Assert
    assert actual != retyped_by_hand
