"""Fitness function **23** — a stage that splits declares what it splits. Ledger task 9.2.

`01` → *Fitness functions this phase turns on* carries the argument; this file is the check, and
filing it is what mints the number: FF22 was taken the same day by task 9.0's
`test_ff22_every_run_path_reaches_a_declared_role.py`, so `23` is the first free one.

**The property.** Every plugin discovery registers under `Chunker` carries a non-empty
`applies_to`. `02` §3's default — *a stage that declares no `applies_to` applies to everything*
(`docs/02-extension-model.md` §3 → *Applicability*; cited by section rather than by line, because
the line moved within the same phase when task 9.3 inserted a block earlier in that file — `L9.50`)
— stays for every other contract; for a stage whose whole job is to split, "everything" is the
defect.

**Why a fitness function and not a review note.** Ledger `1.6` is ticked — *an atomic node passes
the chunker unsplit without the chunker knowing what atomic means* — and on 2026-09-06 that property
was measured against the product and did not hold: `FixedSizeChunker` declared no `applies_to` and
split a `MediaType.TABLE` node into two chunks. The mechanism had shipped, its worked example had
shipped, its test fixture declared the thing, and the one chunker this project actually ships did
not (`docs/internal/lessons.md` `L9.6`). Nothing in a green gate said so, because a declaration
nobody makes is indistinguishable from a declaration nobody needs.

**Read off the registered plugin, never off source text.** `applies_to` is read here the way
`weft_kernel.runner._applies_to_of` reads it — `getattr(instance, "applies_to", ())` on the object
the registered factory builds
(`packages/weft-kernel/src/weft_kernel/runner.py:1257-1266 'def _app'`) — so a
chunker that inherits its declaration, or that a factory rather than a class supplies, answers this
check exactly as it would answer the runner. A grep for the string would answer for neither.

**The population is `packages/` and `examples/`, and `testing/` is structurally empty.**
`testing/weft-canary` registers nothing at all: its `register()` deletes both arguments and never
runs, because every test session refuses it by allow-list and fitness function 8(a) fails if it
ever executes (`testing/weft-canary/src/weft_canary/__init__.py:47-56 'def register('`). Sweeping it
would add a
directory to the prose and no subject to the check.

**What this cannot check, stated rather than implied.** `Chunker` already forces one declaration at
registration — `publishes_property_vocabulary = True` makes `destroys` mandatory, and
`weft_kernel.registry` refuses a plugin without it naming what is missing
(`packages/weft-rag/src/weft_chunk/contract.py:81 'Chunker.publish'`). `applies_to` is *not* on that
footing, so a
third party's chunker that declares none registers fine and is refused by nothing: this check's
subject is the chunkers *this tree* ships. Putting `applies_to` beside `destroys` in
`required_declarations` is the stronger answer and is deliberately not taken here — `02` §3 settles
that a stage declaring nothing applies to everything, and narrowing that at the registration seam is
an amendment to a settled rule rather than a repair, owed the argument `09` §6.2 asks of a widening.
It is recorded in `docs/internal/lessons.md` rather than decided in a test file.

**The waiver is pinned empty.** A chunker that genuinely splits everything is not a case this
project has, and an entry here is a visible act in a diff, never a silent edit.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, cast

from tests.discovery import discover_for_tests, register_out_of_tree_examples
from weft_chunk.contract import Chunker
from weft_kernel.registry import Registry, unwrap_factory

#: Plugin names permitted to split every node they are handed. **Pinned empty.** Widening this is an
#: argument recorded in `docs/internal/README.md`'s decision log and named here — never a name
#: parked to make a red check green.
CHUNKERS_APPLYING_TO_EVERYTHING: Final[frozenset[str]] = frozenset()


def _chunkers_declaring_nothing(registry: Registry) -> tuple[str, ...]:
    """Every `Chunker` plugin in `registry` whose `applies_to` is empty, by registered name.

    The instance rather than the class, because the instance is what the runner asks: a factory
    that returns a configured object, or a class that computes its declaration in `__init__`,
    would answer a class-level read differently from the way the pipeline actually behaves.
    `factory(None)` is exactly what `weft_kernel.runner._build` calls for a stage naming no
    `with:` block, so a chunker this cannot construct is a chunker no default pipeline could
    place either — and it fails here rather than being skipped.
    """
    found: list[str] = []
    for name in registry.names_for(Chunker):
        if name in CHUNKERS_APPLYING_TO_EVERYTHING:
            continue
        built = cast(
            "Callable[[object], object]", unwrap_factory(registry.entry(Chunker, name).factory)
        )
        instance = built(None)
        if not getattr(instance, "applies_to", ()):
            found.append(name)
    return tuple(sorted(found))


def _every_registered_chunker() -> Registry:
    """The registry every shipped and every out-of-tree example pack contributes to.

    An example pack is deliberately not a workspace member (fitness function 9(a)), so nothing
    installs an entry point for it — `register_out_of_tree_examples` runs its real `register()`
    off its own `src/`, which is how `test_ff11_pipeline_integrity.py` already reaches the same
    population.
    """
    registry = discover_for_tests()
    register_out_of_tree_examples(registry)
    return registry


def test_every_registered_chunker_declares_what_it_splits() -> None:
    # Arrange
    registry = _every_registered_chunker()

    # Act
    silent = _chunkers_declaring_nothing(registry)

    # Assert
    assert not silent, (
        f"these chunkers declare no `applies_to`, so the runner hands them every node in a "
        f"batch — an atomic table or figure included, which they will split: "
        f"{', '.join(silent)}. Declare what the chunker's own splitting logic actually needs "
        f"(`02` §3 → Applicability); the nodes that cannot satisfy it are routed past."
    )


def test_the_waiver_is_empty() -> None:
    # Arrange / Act / Assert — a ratchet, so that widening it shows up in a diff.
    assert frozenset() == CHUNKERS_APPLYING_TO_EVERYTHING


def test_the_sweep_reaches_both_a_shipped_pack_and_an_out_of_tree_one() -> None:
    """Non-vacuity: a population of zero would satisfy the check above and mean nothing.

    Both halves are named because they arrive by different mechanisms — one through an installed
    entry point, one by importing an example pack's `src/` — and either could break alone.
    """
    # Arrange
    registry = _every_registered_chunker()

    # Act
    registered = set(registry.names_for(Chunker))

    # Assert
    assert {"fixed-size", "example-chunker"} <= registered, (
        f"the sweep found {sorted(registered)}; a chunker this check cannot see is a chunker it "
        f"cannot hold to anything."
    )


def test_a_planted_chunker_declaring_nothing_would_be_caught() -> None:
    """The disagreement the check exists to find, planted deliberately.

    Membership rather than equality: what is being exercised is the finder, and pinning the whole
    tuple would make this a second copy of the check above that fails for its reasons too.
    """

    # Arrange
    class _SplitsEverything:
        destroys: tuple[type[object], ...] = ()

        def __init__(self, config: object = None) -> None:
            del config

    registry = _every_registered_chunker()
    registry.add(Chunker, "splits-everything", _SplitsEverything, distribution="weft-test-pack")

    # Act
    silent = _chunkers_declaring_nothing(registry)

    # Assert
    assert "splits-everything" in silent
