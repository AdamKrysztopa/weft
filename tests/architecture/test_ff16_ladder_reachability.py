"""Fitness function 16 — ladder reachability. `01` -> *Fitness functions* item 16; Phase 8.

**One clause, categorical, carrying no tuning constant.** A distribution that ships any
pipeline document at all must ship enough of them that every plugin it registers into a
*pipeline position* is named by one. Not a percentage, not a count of documents: a plugin
is either reachable from something a user can run today or it is not.

**Why this is a fitness function and not a preference.** Weft's promise is "naive to
advanced, quickly", and a pipeline is data — so the distance between "the engine can
express this" and "a user can run this" is one YAML file, which is exactly the distance
nobody notices growing. Measured 2026-09-05, before this check existed: the tree shipped
**four** pipeline documents naming **ten** plugins, while the default install registered
**forty-eight** plugins into pipeline positions. Thirty-eight capabilities were reachable
only by a user writing YAML from scratch against names no shipped document mentions —
including `raptor`, whose summaries `raptor-and-leaves-rrf` filters for while no shipped
path produced a single one. That is not a rung with a gap in it; it is a rung with no
floor, and it passed every one of 1,900-odd tests because each half was correct alone.

**What "a pipeline position" means, derived rather than listed.** A contract that inherits
`weft_kernel.runner.Stage` is one a document's `use:` can name — that is what `Stage` *is*,
and `weft_kernel.resolution.resolve` will build any of them from a stage declaration.
`Sufficiency`, `Prompt`, `Command`, `LLMProvider`, `RetrievalMetric` and `GenerationMetric`
declare no `Stage` base (`weft_retrieve.contract.Sufficiency`'s own docstring is explicit
about why it has "no pipeline position of its own"), so no document could name one in a
`use:` even if it wanted to, and this check does not ask it to. Nothing here enumerates
either group: `_pipeline_position_contracts` reads `Stage in contract.__mro__` off the real
registry, so a fifth query-path contract published tomorrow is covered with no edit to this
file, and a contract that stops being a `Stage` drops out of scope the moment it does.

**What this cannot check, said out loud.** A plugin reached only through *another* plugin's
`with:` block — `iterative-retrieval`'s `sufficiency:`, `corrective`'s `grader:`, every
`Prompt` a model-backed plugin resolves by name — is invisible here, because a `with:` value
is an arbitrary string whose meaning belongs to the plugin that declares the field, not to
the document. Those names are reachable in fact and unchecked in principle; the ladder puts
them on rungs anyway, and `tests/docs/test_technique_naming.py`'s property 5 is what keeps
each of them named somewhere a reader can find it. This check owns the `use:` position only.

**And it proves a plugin is *placed*, never that the placement *runs*.** Stated because the
distinction cost something on this check's own first day: `index-with-raptor` and
`index-with-questions` satisfy this check, resolve under fitness function 11(b), and both fail
at run time with *"no service is registered for Embedder on this run"* — `raptor` and
`hypothetical-questions` reach an ambient service through `ctx.require` that the query path
builds and `weft_cli.ingest.run_index` never builds at all (ledger task **8.10**). Two static
checks agreed and the binary disagreed, which is `CLAUDE.md`'s own standing rule with a fresh
instance: a green gate is not a working binary, and reachability is a weaker claim than
runnability by exactly the width of the services a run assembles.

**Why the subject is the *contributed* catalogue and not every YAML file in the tree.**
`load_contributed` is what `weft pipeline list` prints and what
`weft_retrieve.contract.RouteCatalogue` routes over — the ladder a user actually meets from
an installed wheel. A document under `manual/`, which fitness function 11(b) also resolves,
is a worked example rather than something shipped; counting one as a rung would let the
ladder be satisfied by prose. The two checks are deliberately different subjects: 11(b) asks
whether every document that claims to be runnable resolves, and this asks whether the
documents that ship cover what ships with them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from tests.discovery import discover_for_tests, installed_packs_except_the_canary
from weft_cli.pipeline_catalogue import load_contributed
from weft_kernel.discovery import PackReport, discover
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry, UnknownPluginError
from weft_kernel.runner import Stage

#: The same never-dialled DSN `tests/discovery.py` and fitness function 11 both use, for the
#: reason both state: `PgVectorStore.__init__` opens no connection, so `weft-store`'s
#: `register()` runs without a container and `NodeStore:pgvector` is a real registration here.
_PLACEHOLDER_STORE_SETTINGS: Final[Mapping[str, Mapping[str, object]]] = {
    "store": {"dsn": "postgresql://ff16-placeholder/placeholder"}
}

#: A `(contract, plugin)` pair permitted to occupy a pipeline position no shipped document
#: names. **Pinned empty, and it got there the way a waiver is supposed to** — by the entries
#: being removed rather than renewed. Phase 8's exit criterion required exactly this, so the
#: two entries this constant carried were a dated debt rather than a parking space.
#:
#: **Both were `Renderer` names, and both are gone because the contract got a driver.**
#: `weft_extract.contract.Renderer` is `Stage[Sequence[Node], Rendition]` — "an ordinary
#: `Stage` terminus", its own docstring says, whose output "leaves the pipeline for a human or
#: another system". Nothing took it *out*: no shipped command returned a `Rendition` to
#: anybody, so a document ending in `plain` or `markdown` would resolve, run, and throw away
#: its only product. The waiver said so and named ledger task **8.9** as where it would be
#: deleted. 8.9 built `weft render` and the two `preview-*` documents, and this is that
#: deletion — task 2.27's own exit demonstration, *"an operator's PDF becomes readable"*,
#: reachable from the CLI for the first time.
#:
#: **A second pair was drafted here and never landed, which is the outcome this waiver is
#: for.** Writing the ladder found that `threshold-ladder` and `always` could be placed by no
#: document anybody could ship, because `weft_cli.route_ask` held the router's name as a module
#: constant. That is a true, checked fact about what can be run — precisely the standard this
#: waiver sets — and it was still the wrong answer, because the fact was a defect rather than
#: a constraint. Ledger task **8.3** made the name `[services] route` and the entry was never
#: written. **A waiver reason must be a fact; that is necessary and not sufficient, and the
#: question to ask after establishing it is whether the fact should hold.**
#:
#: Adding a pair here is a visible act in a diff and needs a reason of the same kind: a fact
#: about what can be run, never "no rung was written for it yet" — and it needs the task that
#: will delete it again, because both entries this constant ever held named one.
POSITIONS_WAIVED_FROM_THE_LADDER: Final[frozenset[tuple[str, str]]] = frozenset()


def _reports() -> tuple[PackReport, ...]:
    """Every installed pack's discovery outcome, canary excluded — the real pass.

    A second `discover()` rather than `discover_for_tests()`'s registry alone, because this
    check needs both halves of what one pass produces: the registry (which plugin names exist,
    and which distribution registered each) and the reports (which distribution contributed
    which pipeline resource). `discover_for_tests` returns only the first.
    """
    registry = Registry()
    return discover(
        registry,
        allow=installed_packs_except_the_canary(),
        pack_settings=_PLACEHOLDER_STORE_SETTINGS,
    )


def _pipeline_position_contracts(registry: Registry) -> tuple[type[object], ...]:
    """Every registered contract a document's `use:` could name — `Stage` subclasses only.

    Read off `contract.__mro__` rather than from a list this file maintains, for the reason
    fitness function 11(a)'s own `_marked_operator_fields` gives about its operator marks: a
    second, disconnected enumeration of the same facts is correct today and has no mechanism
    keeping it correct tomorrow.
    """
    return tuple(
        contract
        for contract in sorted(registry.contracts(), key=lambda c: c.__name__)
        if Stage in getattr(contract, "__mro__", ())
    )


def _positions_shipped_by(
    registry: Registry, distributions: frozenset[str]
) -> frozenset[tuple[str, str]]:
    """`(contract name, plugin name)` for every pipeline position `distributions` registers."""
    found: set[tuple[str, str]] = set()
    for contract in _pipeline_position_contracts(registry):
        for name in registry.names_for(contract):
            try:
                entry = registry.entry(contract, name)
            except UnknownPluginError:  # pragma: no cover - names_for just yielded it
                continue
            if entry.distribution in distributions:
                found.add((contract.__name__, name))
    return frozenset(found)


def _distributions_shipping_a_pipeline(reports: Sequence[PackReport]) -> frozenset[str]:
    """Every distribution that contributes at least one pipeline document.

    **This is the whole scope rule, and it is derived rather than named.** A distribution
    that ships no document is making no claim about a ladder and is not held to one —
    `weft-pdf`, `weft-qdrant` and `weft-openai` each register a pipeline position and ship
    no document, correctly: a document naming `qdrant` could not resolve on an install that
    has no `weft-qdrant`, so the pack that owns the plugin is the only one that could ever
    place it. Ship one document and you have taken on the ladder; ship none and you have not.
    """
    return frozenset(report.distribution for report in reports if report.pipeline_resources)


def _named_in_a_use_position(pipelines: Iterable[Pipeline]) -> frozenset[str]:
    """Every plugin name any of `pipelines` places in a `use:`.

    `stages`, an `insert`'s own stage and a `replace`'s target each carry a `use:` — the same
    three sources fitness function 11(b)'s `_stage_use_pairs` reads, and for the same reason
    `remove` and `set` contribute nothing here: neither names a plugin. `fallback:` is
    excluded on 11(b)'s own stated grounds — a forward-declared fallback may legitimately
    name a plugin nothing installs yet, so counting one as coverage would let a rung be
    satisfied by a name that cannot run.
    """
    used: set[str] = set()
    for pipeline in pipelines:
        used.update(stage.use for stage in pipeline.stages)
        used.update(operator.stage.use for operator in pipeline.insert)
        used.update(stage.use for stage in pipeline.replace)
    return frozenset(used)


def _unreachable(
    positions: frozenset[tuple[str, str]], used: frozenset[str]
) -> frozenset[tuple[str, str]]:
    """The check itself, factored out so the failure self-test drives the identical code."""
    return frozenset(
        pair
        for pair in positions
        if pair[1] not in used and pair not in POSITIONS_WAIVED_FROM_THE_LADDER
    )


def test_the_waiver_names_only_what_it_documents() -> None:
    """**Pinned empty**, the shape every other ratchet in this suite holds. A pair added here
    changes this line, in a diff, on purpose."""
    assert frozenset() == POSITIONS_WAIVED_FROM_THE_LADDER, (
        "POSITIONS_WAIVED_FROM_THE_LADDER is no longer empty. A waiver here states a fact "
        "about what can be run — never 'no rung was written for it yet' — and it needs the "
        "task that will delete it again. Record both in its own docstring and in "
        "docs/README.md's decision log, or write the rung."
    )


def test_at_least_one_distribution_ships_a_pipeline() -> None:
    # Floor — with no shipping distribution the scope is empty and the check below passes
    # by asking nothing, the vacuous-pass shape `08` §3 refuses.
    shipping = _distributions_shipping_a_pipeline(_reports())
    assert shipping, (
        "no installed distribution contributes a pipeline document, so this check has no "
        "subject at all. `weft_retrieve.register` contributes the ladder through "
        "`PackRegistrar.add_pipeline_resource`; if that stopped happening, fitness function "
        "11(b) and `weft pipeline list` are both wrong too."
    )


def test_at_least_one_pipeline_position_is_checked() -> None:
    # Second floor — a `Stage` detection that broke would yield an empty `positions` set,
    # and an empty set is a subset of everything.
    registry = discover_for_tests()
    positions = _positions_shipped_by(registry, _distributions_shipping_a_pipeline(_reports()))
    assert positions, (
        "no pipeline position was found on any distribution that ships a pipeline — "
        "`_pipeline_position_contracts` reads `Stage in contract.__mro__`, so an empty "
        "result means either discovery registered nothing or `weft_kernel.runner.Stage` "
        "is no longer the base every capability contract declares."
    )


def test_every_pipeline_position_the_ladder_ships_is_reachable() -> None:
    # Arrange
    reports = _reports()
    registry = discover_for_tests()
    shipping = _distributions_shipping_a_pipeline(reports)
    positions = _positions_shipped_by(registry, shipping)
    contributed = load_contributed(reports)

    # Act
    unreachable = _unreachable(positions, _named_in_a_use_position(contributed.values()))

    # Assert
    assert not unreachable, (
        "these plugins occupy a pipeline position and no shipped pipeline document names "
        "them, so nobody can run them without writing YAML against a name they have no way "
        "to discover:\n"
        + "\n".join(f"  {contract}: {name}" for contract, name in sorted(unreachable))
        + f"\n\nShipped documents: {', '.join(sorted(contributed)) or '(none)'}.\n"
        "Add a rung — a rung exists because it is a step somebody would actually take, "
        "never to tick a plugin off — or, if the position genuinely cannot be run today, "
        "waive the pair in POSITIONS_WAIVED_FROM_THE_LADDER with the fact that makes it so."
    )


def test_the_check_can_actually_fail() -> None:
    """A position no document names must be visible, or the assertion above checks nothing."""
    # Arrange — the exact regression: a plugin registered into a position, and a document
    # set that never names it.
    positions = frozenset({("Retriever", "vector-top-k"), ("Fuser", "never-placed")})

    # Act
    unreachable = _unreachable(positions, frozenset({"vector-top-k"}))

    # Assert
    assert unreachable == {("Fuser", "never-placed")}


def test_the_waiver_is_live_rather_than_decorative() -> None:
    """The waived pairs are pairs the sweep *fires on* — not pairs it never reaches.

    `docs/lessons.md` L6.29: a waiver test that asks whether the waived thing is *present*
    passes just as happily when the check has stopped looking at all. This asks the only
    question that separates the two — drop the waiver, and does the check report these
    exact pairs? If `plain` and `markdown` ever land on a rung, this fails and the waiver
    is deleted, which is the correct outcome rather than a stale entry nobody revisits.
    """
    # Arrange
    reports = _reports()
    registry = discover_for_tests()
    positions = _positions_shipped_by(registry, _distributions_shipping_a_pipeline(reports))
    used = _named_in_a_use_position(load_contributed(reports).values())

    # Act — the identical computation with the waiver emptied.
    fires_on = frozenset(pair for pair in positions if pair[1] not in used)

    # Assert
    assert fires_on == POSITIONS_WAIVED_FROM_THE_LADDER, (
        "with the waiver emptied the check must report exactly what the waiver holds. It "
        f"reports {sorted(fires_on)} against a waiver of "
        f"{sorted(POSITIONS_WAIVED_FROM_THE_LADDER)} — either a position lost its rung "
        "(fix the ladder) or a waived name gained one (delete its waiver entry)."
    )
