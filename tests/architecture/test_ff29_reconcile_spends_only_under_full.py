"""Fitness function **29** — a reconcile pass reaches a model only under `full`. Ledger task 11.9.

`01` → *Fitness functions* item 29 carries the argument; this file is the check.

**What it is for.** `weft_store.contract.ReconcileMode`'s own docstring states the consent boundary
this repository runs on: two members and no third, *"because the distinction being drawn is not a
degree of thoroughness but a question of consent: backfill runs model calls and writes, so an
ambient backfill would silently change what an existing pipeline does by a second route."*
`repair` is the mode the automatic post-index pass runs in, unasked, after every `weft index`, so a
participant that reached a model there would spend on every ingest with nobody having agreed to it.

**Why this is a check and not a sentence.** It was very nearly a registration seam instead — ledger
`11.9` first built one, registering `LLM`/`Prompts`/`TokenSink` onto the reconcile `Context` only
under `full`, on CLAUDE.md's own rule that cross-cutting concerns live at the registration seam and
never in a rule authors must remember. **Running the binary falsified the premise.**
`weft_cli.run_services.command_path_services` already registers those three on **every** command's
`Context`, deliberately and since task 7.4, so that a third party's `Command` can reach a model at
all — the second registration raised `DuplicateServiceError` and exited 1, and the first one was
never needed because an `LLM` was reachable from a `repair` pass before `11.9` existed. Narrowing
that seam would partly reverse 7.4; removing the service from the registry would need a kernel line
this phase's own exit forbids. So the boundary stays where the contract already puts it — inside
each participant, on the mode it was handed — and this check is what keeps it from being a rule
somebody has to remember.

**What it can see, and what it cannot, stated rather than implied.** It reads the *source* of every
first-party class that satisfies `Reconcilable` structurally, and asserts that a `ctx.require(...)`
naming a model contract inside `reconcile` sits under a branch testing `ReconcileMode.FULL`. It
therefore cannot see a pack outside this repository, and it cannot follow a model service reached
through a helper the method calls rather than through `ctx.require` in its own body. Both are real
limits; the second is why `test_the_model_seam_is_reached_directly_in_every_reconcile` exists —
it fails if a participant ever stops naming the seam in the method this check reads, which is the
point at which somebody has to come back here rather than the point at which the check goes quietly
blind. This is `docs/lessons.md` L5.15's shape turned around: a check with a blind spot says where
it is.

**Two floors, because a check that matched nothing would pass by being blind.**
`test_at_least_one_reconcilable_is_found` and `test_at_least_one_guarded_model_seam_is_found` fail
if the AST walk stops matching what the tree actually holds — the identical protection
`test_ff9_extension_from_outside.py::test_the_grep_can_actually_fail` gives its own scan.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Final, NamedTuple

import pytest

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGES: Final[Path] = REPO_ROOT / "packages"

#: The two members `weft_store.contract.Reconcilable` requires. A class defining both satisfies the
#: Protocol structurally, which is how capability is decided everywhere else in this tree — "nobody
#: writes a flag, so nobody writes a false one" (`02` §1) — so it is how participants are found
#: here rather than by importing and constructing them, which would need two live containers.
_RECONCILABLE_MEMBERS: Final[frozenset[str]] = frozenset({"reconcile", "estimate"})

#: The services whose use costs money or leaves the machine. `Embedder` is here beside the three
#: model ones because an embedding call is a paid remote call for every provider-backed embedder in
#: this tree, and `ReconcileMode`'s consent argument is about spend, not about which vendor API the
#: spend goes through.
_MODEL_CONTRACTS: Final[frozenset[str]] = frozenset({"LLM", "Prompts", "TokenSink", "Embedder"})

#: The enum member a reach for one of those must sit under. Matched on the attribute name rather
#: than the dotted path, so `ReconcileMode.FULL`, `mode is FULL` after a `from ... import` and an
#: aliased import all read the same to this check.
_FULL: Final[str] = "FULL"

#: **The ratchet, pinned empty.** A participant that genuinely must reach a model under `repair`
#: goes here, by qualified class name, in a diff somebody has to approve — never by an edit to the
#: walk above. `01` → *Fitness functions*: a waiver is a visible act.
WAIVED_RECONCILABLES: Final[frozenset[str]] = frozenset()


class _Participant(NamedTuple):
    """One first-party class satisfying `Reconcilable`, and the `reconcile` body to read."""

    qualified_name: str
    path: Path
    reconcile: ast.AsyncFunctionDef | ast.FunctionDef


def _first_party_modules() -> Iterator[Path]:
    """Every shipped `.py` under `packages/*/src`, tests and examples deliberately excluded.

    A test double satisfying `Reconcilable` is not a participant any fan-out reaches, and holding
    doubles to a shipped rule is how a check ends up waived for reasons that say nothing about the
    property (`tests/unit/weft_cli/test_reconcile.py` alone would add four).
    """
    for distribution in sorted(PACKAGES.iterdir()):
        source = distribution / "src"
        if source.is_dir():
            yield from sorted(source.rglob("*.py"))


def _participants() -> tuple[_Participant, ...]:
    found: list[_Participant] = []
    for path in _first_party_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = {
                member.name
                for member in node.body
                if isinstance(member, ast.AsyncFunctionDef | ast.FunctionDef)
            }
            if not methods >= _RECONCILABLE_MEMBERS:
                continue
            body = next(
                member
                for member in node.body
                if isinstance(member, ast.AsyncFunctionDef | ast.FunctionDef)
                and member.name == "reconcile"
            )
            module = path.relative_to(path.parents[len(path.parts) - path.parts.index("src") - 2])
            found.append(
                _Participant(
                    qualified_name=f"{module.with_suffix('').as_posix().replace('/', '.')}."
                    f"{node.name}",
                    path=path,
                    reconcile=body,
                )
            )
    return tuple(found)


def _model_seams(body: ast.AST) -> Iterator[tuple[str, ast.Call]]:
    """Every `<anything>.require(<ModelContract>)` call inside `body`, with the contract's name.

    Matched on the method name and the argument rather than on the receiver being spelled `ctx`,
    because the receiver is the caller's own local and a rename of it is not a change to what the
    call does — asserting the spelling would be asserting the arrangement (`docs/lessons.md`
    `L9.39`) rather than the behaviour.
    """
    for node in ast.walk(body):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "require":
            continue
        for argument in node.args:
            if isinstance(argument, ast.Name) and argument.id in _MODEL_CONTRACTS:
                yield argument.id, node


def _guarded_seams(reconcile: ast.AST) -> tuple[set[ast.Call], set[ast.Call]]:
    """`(guarded, all)` — the model seams under a `FULL` test, and every one found.

    "Under a `FULL` test" is decided by containment: a seam anywhere inside the body of an `if`
    whose condition names `FULL` is guarded. Containment rather than exact-shape matching, because
    `mode is ReconcileMode.FULL`, `mode == ReconcileMode.FULL` and `mode in (ReconcileMode.FULL,)`
    are one intent written three ways, and a check that admitted only the first would be a style
    rule wearing a safety rule's name.
    """
    every = {call for _, call in _model_seams(reconcile)}
    guarded: set[ast.Call] = set()
    for node in ast.walk(reconcile):
        if not isinstance(node, ast.If):
            continue
        names = {
            inner.attr for inner in ast.walk(node.test) if isinstance(inner, ast.Attribute)
        } | {inner.id for inner in ast.walk(node.test) if isinstance(inner, ast.Name)}
        if _FULL not in names:
            continue
        for statement in node.body:
            guarded |= {call for _, call in _model_seams(statement)}
    return guarded, every


def test_at_least_one_reconcilable_is_found() -> None:
    """The first floor: a walk that matched no participant would pass every check below."""
    # Act
    found = _participants()

    # Assert
    assert found, (
        "no first-party class satisfying Reconcilable was found under packages/*/src — the AST "
        "walk has stopped matching what this tree holds, and every assertion below is now vacuous"
    )


def test_at_least_one_guarded_model_seam_is_found() -> None:
    """The second floor, and the sharper one: a tree where **nothing** reaches a model inside
    `reconcile` would satisfy the rule below by having nothing to check.

    `weft_kg.store.GraphStore` is that seam today, added by ledger `11.9` — it is the first and
    so far only participant in this tree whose `full` costs a real number.
    """
    # Act
    guarded = [
        participant.qualified_name
        for participant in _participants()
        if _guarded_seams(participant.reconcile)[0]
    ]

    # Assert
    assert guarded, (
        "no reconcile() in this tree reaches a model service under a FULL branch, so the rule "
        "below is checking nothing. Either the seam moved out of the method this check reads — "
        "see the module docstring on what it cannot follow — or the expensive pass is gone"
    )


def test_the_model_seam_is_reached_directly_in_every_reconcile() -> None:
    """Every participant that spends does so through a `require` call this check can read.

    This is the blind spot named out loud rather than left to open silently: a participant that
    moved its `ctx.require(LLM)` into a helper would keep spending and stop being checkable, and
    the moment that happens somebody has to come back here and decide what the check should
    become. Asserted as a property of the current tree, so it fails at the change rather than
    after it.
    """
    # Act
    spending = {
        participant.qualified_name: _guarded_seams(participant.reconcile)
        for participant in _participants()
    }

    # Assert — a participant with a guarded seam must have every seam guarded, never a mixture.
    mixed = {
        name: sorted(str(id(call)) for call in every - guarded)
        for name, (guarded, every) in spending.items()
        if guarded and every - guarded
    }
    assert not mixed, (
        f"{sorted(mixed)} reach a model service both inside and outside a FULL branch in the same "
        f"reconcile(). One of the two is wrong, and a mixture is the shape that reads as deliberate"
    )


def test_no_reconcile_reaches_a_model_outside_full() -> None:
    """The rule itself. `ReconcileMode`'s own consent argument, made checkable.

    A participant reaching `LLM`, `Prompts`, `TokenSink` or `Embedder` in `reconcile` without a
    `FULL` branch above it spends under `repair` — the mode `weft index` runs unasked at the end
    of every ingest — so the operator pays for something they never opted into and the only
    symptom is a bill.
    """
    # Act
    offenders: dict[str, list[str]] = {}
    for participant in _participants():
        if participant.qualified_name in WAIVED_RECONCILABLES:
            continue
        guarded, every = _guarded_seams(participant.reconcile)
        unguarded = sorted(
            contract
            for contract, call in _model_seams(participant.reconcile)
            if call in every - guarded
        )
        if unguarded:
            offenders[participant.qualified_name] = unguarded

    # Assert
    assert not offenders, (
        f"{offenders} reach a model service inside reconcile() with no ReconcileMode.FULL branch "
        f"above it. ReconcileMode has two members and no third because the split is about "
        f"consent: 'repair' runs automatically after every weft index, so spending there is "
        f"spending nobody agreed to. Put the reach under a FULL branch, or add the class to "
        f"WAIVED_RECONCILABLES with the argument in the diff"
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """The planted counter-example — `test_ff9_extension_from_outside.py`'s own discipline.

    A rule with no demonstrated failure is a rule nobody has watched work, and an AST walk is
    exactly the kind of check that can silently stop matching. Both shapes are planted: one
    reaching a model with no guard at all, and one reaching it under a branch testing the *other*
    mode, which is the near-miss a reader would most likely write by hand.
    """
    # Arrange
    unguarded = ast.parse(
        "class _Spends:\n"
        "    async def reconcile(self, ctx, mode):\n"
        "        llm = ctx.require(LLM)\n"
        "        return llm\n"
        "    async def estimate(self, ctx, mode): ...\n"
    )
    wrong_mode = ast.parse(
        "class _SpendsUnderRepair:\n"
        "    async def reconcile(self, ctx, mode):\n"
        "        if mode is ReconcileMode.REPAIR:\n"
        "            return ctx.require(LLM)\n"
        "    async def estimate(self, ctx, mode): ...\n"
    )
    del tmp_path

    # Act / Assert — neither has a guarded seam, and both have an unguarded one.
    for planted in (unguarded, wrong_mode):
        body = next(
            member
            for node in ast.walk(planted)
            if isinstance(node, ast.ClassDef)
            for member in node.body
            if isinstance(member, ast.AsyncFunctionDef) and member.name == "reconcile"
        )
        guarded, every = _guarded_seams(body)
        assert every, "the planted class reaches a model and the walk did not see it"
        assert not guarded, "the planted class has no FULL branch and the walk found one"


def test_the_waiver_is_pinned_empty() -> None:
    """The ratchet — `01` → *Fitness functions*. Waiving is a visible act in a diff, never an
    edit to the walk that quietly stops looking at something.
    """
    # Assert
    assert frozenset() == WAIVED_RECONCILABLES


@pytest.mark.parametrize("contract", sorted(_MODEL_CONTRACTS))
def test_every_watched_contract_is_a_real_published_name(contract: str) -> None:
    """The set above is a claim about this tree's own contracts, not a list of plausible words.

    A typo here would silently narrow the rule to nothing for that contract, which is the
    failure mode a frozenset of strings has and a set of imported classes does not — so the
    strings are checked against the modules that publish them.
    """
    # Arrange — where each one is published, read rather than assumed.
    published = {
        "LLM": PACKAGES / "weft-rag" / "src" / "weft_llm" / "contract.py",
        "TokenSink": PACKAGES / "weft-rag" / "src" / "weft_llm" / "contract.py",
        "Prompts": PACKAGES / "weft-rag" / "src" / "weft_prompts" / "contract.py",
        "Embedder": PACKAGES / "weft-rag" / "src" / "weft_embed" / "contract.py",
    }

    # Act
    source = published[contract].read_text(encoding="utf-8")

    # Assert
    assert f"class {contract}(" in source, (
        f"{contract} is watched by this check and {published[contract]} does not define it"
    )
