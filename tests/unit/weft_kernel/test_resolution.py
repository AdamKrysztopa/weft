"""Unit tests for `weft_kernel.resolution`.

Mirrors `packages/weft-kernel/src/weft_kernel/resolution.py`. Task **1.3**: *a derived
pipeline resolves to a frozen, fully-explicit form with no inheritance left to
interpret — carrying each stage's provenance, every var's final value, unplaced
contributions and unapplied operators — and everything it can be wrong about is wrong
before it runs* (`docs/02-extension-model.md` §3 → *Derivation*, *When resolution
fails*). Extended by task **1.4**: *a derived pipeline changes its parent by operator
and never by copy, at any depth through one parent, with a cycle and every stale
operator target refused by name* (`02` §3 → the operator table and its edge rules).
Extended again by task **1.5**: *a stage's `with:` block is validated against the
plugin's own typed model at resolution, so the same plugin can run twice with
different configuration* (`02` §1, contract rules; §3 → the `with:` note). Extended
again by task **1.14**: *a var overridden by a child re-resolves every inherited
stage that references it, and no var can reach applicability* (`02` §3 → *Language,
and what a var is for*).

**Task 1.14 adds no new kernel mechanism either, the same shape task 1.8's own module
docstring states for itself.** `_walk_extends` (task 1.3) already merges `vars` across
the *whole* `extends` chain, root to leaf, once per `resolve()` call — not once per
stage and not once per level — and the main loop in `resolve()` substitutes every
stage's `config` against that one merged mapping regardless of which ancestor wrote the
stage. Nothing about that logic special-cases "how many stages reference this var" or
"how many ancestors separate the override from the reference," so both were already
true of every pipeline task 1.3 could resolve; what task 1.14 does is have a test that
would actually fail if either dimension had been special-cased. Reused rather than
duplicated: `test_a_child_that_only_retargets_a_var_resolves_the_parents_stage_with_its_
own_value` (task 1.3's own load-bearing var test) already proves the single-stage,
single-level case, and `test_operators_apply_at_any_depth_through_the_extends_chain`
(task 1.4) already proves depth is not special-cased for *operators*; task 1.14's own
`test_a_child_overriding_a_var_re_resolves_every_inherited_stage_at_any_depth` is the one
case neither of those is shaped to catch — two referencing stages, and a relay ancestor
in between that mentions the var not at all — because a bug that re-resolved only the
*first* matching stage, or that stopped merging vars past one level of `extends`, would
pass every existing test in this file while failing that one. **The negative half —
vars never reaching `applies_to` — needed no new test at all**, and is not duplicated
here: `weft_kernel.payload.applicability`'s own module docstring already states it
structurally ("there is no `${var:NAME}` token for `weft_kernel.resolution`'s
substitution to ever reach"), and `test_language_and_vars.py`'s
`test_a_var_token_written_as_an_applies_constraint_value_is_never_substituted` and
`test_a_var_sharing_the_applicability_constraint_s_value_never_retargets_it` — both task
1.8 — are already exactly "a test that would fail if someone wired them together": the
first constructs an `Applies` constraint whose value *is* the literal token text and
shows it is read as an opaque string, never substituted; the second resolves the
identical pipeline with the var set to the one value that collides with an
`applies_to` constraint and shows the routing decision does not move. A third copy of
either would test the same wiring a third time, not a different pipeline shape.

The load-bearing distinction this file exists to prove is the one `weft_kernel.runner`
already states in its own docstring: `resolve()` here produces **data** — nothing in a
`ResolvedStage` is a constructed plugin instance, and two resolutions of an
identical pipeline compare equal by `==`, which is not true of anything holding a live
object. `test_resolving_the_same_pipeline_twice_produces_equal_data` is that claim made
concrete. Task 1.4's own load-bearing pair is
`test_remove_written_above_insert_lets_a_new_stage_reuse_the_removed_id` and
`test_insert_written_above_remove_on_the_same_id_collides`: identical operators, only
their written order swapped, one succeeds and the other fails — the concrete proof that
application order is read from the document, never assumed. Task 1.5's own load-bearing
test is `test_the_same_plugin_resolves_twice_with_different_configuration_in_one_pipeline`
— the ledger's own words, made concrete: one plugin, two stage ids, two `with:` blocks,
both validated independently.

`_Extractish` / `_Chunkish` mirror `test_runner.py`'s `_TextStage` / `_CountStage`
convention: stand-in contracts declaring `Stage[In, Out]` as their own base, so the
composition check has two distinct payload shapes to tell apart. Plugin classes declare
`requires`/`provides`/`intact`/`destroys` as **class** attributes, never set in
`__init__` — resolution reads them off the registered factory directly, the same way
`weft_kernel.registry._require_destroys_if_governed` already reads `destroys` off a
class with no instance built yet, because a resolved *form* build no instance either.
`config_model` — task 1.5 — is read the same defensive way: `_Extractor` and `_Chunker`
declare `_ExtractorConfig`/`_ChunkerConfig`, both permissive stand-ins with every field
optional, because which field a given test's `with:` block writes (`lang`, `note`,
`a`, `size`, `overlap`) is exercising a different *resolution* behaviour — var
substitution, the token-must-match-exactly edge case, read-only mutation, a `set`
operator merging configuration — never a constraint `_ExtractorConfig`/`_ChunkerConfig`
themselves are meant to enforce. `_Keywords` deliberately declares no `config_model` at
all, so it also stands in for a plugin that has not opted in.
"""

import functools
from typing import TYPE_CHECKING, ClassVar, Protocol

import pytest
from pydantic import BaseModel, ConfigDict

from weft_kernel import resolution
from weft_kernel.context import Context
from weft_kernel.payload import Applies, ExtModel, Outcome, Produced, Property
from weft_kernel.pipeline import (
    InsertOperator,
    Pipeline,
    SetOperator,
    SlotDeclaration,
    StageDeclaration,
)
from weft_kernel.registry import Registry, UnknownPluginError
from weft_kernel.runner import PipelineResolutionError, Stage


class _Extractish(Stage[str, list[str]], Protocol):
    async def run(self, payload: str, ctx: Context) -> Outcome[list[str]]: ...


class _VersionedExtractish(Stage[str, list[str]], Protocol):
    """A stand-in contract that declares `version`, exactly the way a real one does.

    `version` is declared under `if TYPE_CHECKING:` and assigned after the class
    body — see `weft_chunk.contract.Chunker` — so it never joins
    `__protocol_attrs__`, the identical reasoning `_GovernedContract` in
    `test_registry.py` already documents for `publishes_property_vocabulary`.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def run(self, payload: str, ctx: Context) -> Outcome[list[str]]: ...


_VersionedExtractish.version = "3.1"


class _Chunkish(Stage[list[str], list[str]], Protocol):
    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]: ...


class _Extracted(ExtModel):
    __namespace__ = "weft-test-pack"
    __schema_version__ = "1.0.0"


class _WordBoundaries(Property):
    """`02` §3's own worked example: hyphenation repair needs it intact, chunking destroys it."""

    __namespace__ = "weft-test-pack"


class _ExtractorConfig(BaseModel):
    """`_Extractor`'s own typed `with:` model — task 1.5's mechanism, exercised generically.

    Every field optional, on purpose: which one a given test's `with:` block writes
    (`lang`, `note`, `a`) is exercising a different *resolution* behaviour — var
    substitution, the token-must-match-exactly edge case, read-only mutation — never a
    constraint this model itself is meant to enforce. See `test_an_invalid_with_block_...`
    below for a plugin whose model *does* enforce something.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    lang: str | None = None
    note: str | None = None
    a: int | None = None


class _ChunkerConfig(BaseModel):
    """`_Chunker`'s own typed `with:` model, on the same terms as `_ExtractorConfig`.

    `note` — task 1.14's own addition, mirroring `_ExtractorConfig.note` exactly — is
    what lets a second, chain-composing stage carry a `${var:NAME}` reference: `size`
    and `overlap` are `int | None`, and a var substitutes a scalar string, so proving a
    var reaches *every* inherited stage that references it needs a stray string field
    here too, on the identical footing `_ExtractorConfig.note` already has one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    size: int | None = None
    overlap: int | None = None
    note: str | None = None


class _Extractor:
    requires: tuple[type[ExtModel], ...] = ()
    provides = (_Extracted,)
    intact: tuple[type[Property], ...] = ()
    destroys: tuple[type[Property], ...] = ()
    config_model = _ExtractorConfig

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: str, ctx: Context) -> Outcome[list[str]]:
        return Produced(value=[payload])


class _Chunker:
    requires = (_Extracted,)
    provides: tuple[type[ExtModel], ...] = ()
    intact: tuple[type[Property], ...] = ()
    destroys: tuple[type[Property], ...] = ()
    config_model = _ChunkerConfig

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=payload)


class _DestroysWordBoundaries:
    """A stand-in for `weft_chunk.fixed_size.FixedSizeChunker` — task 1.2's own example."""

    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    intact: tuple[type[Property], ...] = ()
    destroys: tuple[type[Property], ...] = (_WordBoundaries,)

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=payload)


class _NeedsWordBoundariesIntact:
    """A stand-in for a hyphenation-repair stage — `02` §3's own worked example."""

    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    intact: tuple[type[Property], ...] = (_WordBoundaries,)
    destroys: tuple[type[Property], ...] = ()

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=payload)


class _Keywords:
    """A stand-in for a third-party keyword-extraction stage — task 1.4's `insert` example."""

    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    intact: tuple[type[Property], ...] = ()
    destroys: tuple[type[Property], ...] = ()

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=payload)


class _Prose(ExtModel):
    """Task 1.6's own worked example: a fact a narrowed chunker declares `applies_to` over."""

    __namespace__ = "weft-test-pack"
    __schema_version__ = "1.0.0"


class _ChunkerNarrowedToProse:
    """`_Chunker`, with an `applies_to` declared — task 1.6, `02` §3 → *Applicability*.

    Registered under its own bare name rather than replacing `_Chunker`, so
    tests exercising the plain default (no `applies_to` at all) are
    untouched by this one existing.
    """

    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    intact: tuple[type[Property], ...] = ()
    destroys: tuple[type[Property], ...] = ()
    applies_to = (Applies(_Prose),)
    config_model = _ChunkerConfig

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=payload)


def _registry() -> Registry:
    registry = Registry()
    registry.add(_Extractish, "docling", _Extractor, distribution="weft-extract")
    registry.add(_Chunkish, "sentence", _Chunker, distribution="weft-chunk")
    registry.add(_Chunkish, "sentence-narrowed", _ChunkerNarrowedToProse, distribution="weft-chunk")
    return registry


def _registry_with_operator_plugins() -> Registry:
    """`_registry()` plus the two extra plugins task 1.4's operator tests exercise.

    `sentence-v2` is a second `_Chunkish` plugin under a different bare name — what a
    `replace` swaps to, or what an `insert` reusing a just-`remove`d id names. `keybert`
    stands in for `02` §3's own driving example, `insert: {after: chunk, stage: {use:
    keybert}}`.
    """
    registry = _registry()
    registry.add(_Chunkish, "sentence-v2", _Chunker, distribution="acme-chunk")
    registry.add(_Chunkish, "keybert", _Keywords, distribution="acme-kw")
    return registry


class _Casing(Property):
    """A second `Property`, distinct from `_WordBoundaries`, for task 1.11's own conflict test.

    One shared property between two contributions only ever gives one ordering
    constraint; a genuine, unresolvable conflict needs two contributions each needing
    what the *other* destroys — `test_two_contributions_whose_ordering_constraints_...`
    below — which needs a second property to build the second half of the cycle with.
    """

    __namespace__ = "weft-test-pack"


class _ContributionConflictA:
    """Needs `_Casing` intact, destroys `_WordBoundaries` — half of a genuine cycle."""

    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    intact: tuple[type[Property], ...] = (_Casing,)
    destroys: tuple[type[Property], ...] = (_WordBoundaries,)

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=payload)


class _ContributionConflictB:
    """Needs `_WordBoundaries` intact, destroys `_Casing` — the other half of the cycle."""

    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    intact: tuple[type[Property], ...] = (_WordBoundaries,)
    destroys: tuple[type[Property], ...] = (_Casing,)

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
        return Produced(value=payload)


def _registry_with_slot_plugins() -> Registry:
    """`_registry_with_operator_plugins()` plus the plugins task 1.11's own tests exercise.

    `aaa-slot`/`zzz-slot` declare nothing at all — two contributions with genuinely no
    ordering relation between them, so a test placing them can prove the tie really is a
    tie. `hyphen-fix`/`chunker` are task 1.2's own `_NeedsWordBoundariesIntact`/
    `_DestroysWordBoundaries` pair, registered under distributions whose *names* sort the
    opposite way their *ordering constraint* requires — `zzz-needs` before `aaa-destroys`
    — so a test can tell the declared relation actually decided the order, rather than
    the tie-break happening to agree with it. `configurable` is `_ChunkerNarrowedToProse`
    — `_Chunker`'s own `config_model`, but with empty `requires` so a contributed stage
    with nothing preceding it still resolves — reused so a contributed stage has a real
    `config_model` a `set` operator can be shown merging into. `conflict-a`/`conflict-b`
    are the cycle above, registered so it is reachable through a slot at all.
    """
    registry = _registry_with_operator_plugins()
    registry.add(_Chunkish, "aaa-slot", _Keywords, distribution="aaa-pack")
    registry.add(_Chunkish, "zzz-slot", _Keywords, distribution="zzz-pack")
    registry.add(_Chunkish, "hyphen-fix", _NeedsWordBoundariesIntact, distribution="zzz-needs")
    registry.add(_Chunkish, "chunker", _DestroysWordBoundaries, distribution="aaa-destroys")
    registry.add(_Chunkish, "configurable", _ChunkerNarrowedToProse, distribution="aaa-pack")
    registry.add(_Chunkish, "conflict-a", _ContributionConflictA, distribution="acme-a")
    registry.add(_Chunkish, "conflict-b", _ContributionConflictB, distribution="acme-b")
    return registry


_CONTRACTS: dict[str, type[object]] = {"extract": _Extractish, "chunk": _Chunkish}
_CONTRACTS_WITH_KEYWORDS: dict[str, type[object]] = {**_CONTRACTS, "keywords": _Chunkish}


def test_a_standalone_pipeline_resolves_every_stage_with_provenance_and_distribution() -> None:
    # Arrange
    pipeline = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk", use="sentence", config={"size": 512}),
        ),
    )

    # Act
    resolved = resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    # Assert
    assert resolved.name == "base"
    assert [stage.id for stage in resolved.stages] == ["extract", "chunk"]
    assert resolved.stages[0].contract == "_Extractish"
    assert resolved.stages[0].contract_version is None
    assert resolved.stages[0].use == "docling"
    assert resolved.stages[0].distribution == "weft-extract"
    assert resolved.stages[0].provenance == "base"
    assert resolved.stages[0].applies_to == ()
    assert resolved.stages[1].config == _ChunkerConfig(size=512)
    assert resolved.unapplied_operators == ()
    assert resolved.unplaced_contributions == ()


def test_a_fallback_naming_no_registered_plugin_still_resolves_carried_through_verbatim() -> None:
    # Repair for a reviewer finding: `fallback:` is deliberately never looked up against
    # `registry`, unlike `use:` — `resolution.ResolvedStage`'s own docstring and `02` §3's
    # fallback callout both say a fallback may legitimately name a plugin nothing installs
    # yet. This pins that `resolve()` does not raise for one and does not silently drop or
    # rewrite the name either.
    # Arrange
    pipeline = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling", fallback=("nothing-registers-this",)),
        ),
    )

    # Act
    resolved = resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    # Assert
    assert resolved.stages[0].fallback == ("nothing-registers-this",)


def test_a_resolved_stage_prints_the_applicability_its_plugin_declared() -> None:
    # Arrange — `02` §3 → *Applicability*: "The resolved form must print each stage's
    # applicability, since a predicate is data." `_ChunkerNarrowedToProse` declares one.
    pipeline = Pipeline(
        name="base", stages=(StageDeclaration(id="chunk", use="sentence-narrowed"),)
    )

    # Act
    resolved = resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    # Assert
    assert resolved.stages[0].applies_to == (Applies(_Prose),)


def test_a_resolved_stage_carries_the_contract_s_own_declared_version() -> None:
    # Arrange — `02` §3: "every stage, plugin, version and configuration value named."
    registry = Registry()
    registry.add(_VersionedExtractish, "docling", _Extractor, distribution="weft-extract")
    pipeline = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="docling"),))

    # Act
    resolved = resolution.resolve(
        pipeline, registry=registry, contracts={"extract": _VersionedExtractish}
    )

    # Assert
    assert resolved.stages[0].contract_version == "3.1"


def test_resolve_reads_requires_through_a_partial_wrapped_factory() -> None:
    # Arrange — the only shape a plugin needing pack settings can take
    # (`functools.partial(PluginClass, settings)`, exactly what `weft_store` registers
    # `PgVectorStore` as). `resolve()` must see `_Chunker.requires` through the wrapper,
    # not silently read an empty default off the `partial` object itself.
    registry = Registry()
    registry.add(_Chunkish, "sentence", functools.partial(_Chunker, {}), distribution="weft-chunk")
    pipeline = Pipeline(name="base", stages=(StageDeclaration(id="chunk", use="sentence"),))

    # Act / Assert
    with pytest.raises(resolution.UnmetRequiresError) as excinfo:
        resolution.resolve(pipeline, registry=registry, contracts=_CONTRACTS)

    message = str(excinfo.value)
    assert "chunk" in message
    assert "_Extracted" in message


def test_resolve_reads_intact_and_destroys_through_partial_wrapped_factories() -> None:
    # Arrange — the mirrored case for `intact`/`destroys`: both stages registered as
    # `functools.partial`-bound factories, so the check only fires if the read reaches
    # the wrapped class.
    registry = Registry()
    registry.add(
        _Chunkish,
        "chunk-fixed",
        functools.partial(_DestroysWordBoundaries, {}),
        distribution="weft-chunk",
    )
    registry.add(
        _Chunkish,
        "hyphenation",
        functools.partial(_NeedsWordBoundariesIntact, {}),
        distribution="acme-clean",
    )
    pipeline = Pipeline(
        name="cleaning",
        stages=(
            StageDeclaration(id="chunk", use="chunk-fixed"),
            StageDeclaration(id="hyphenation", use="hyphenation"),
        ),
    )
    contracts = {"chunk": _Chunkish, "hyphenation": _Chunkish}

    # Act / Assert
    with pytest.raises(resolution.IntactViolationError) as excinfo:
        resolution.resolve(pipeline, registry=registry, contracts=contracts)

    message = str(excinfo.value)
    assert "hyphenation" in message
    assert "_WordBoundaries" in message


def test_resolving_the_same_pipeline_twice_produces_equal_data() -> None:
    # Arrange — the claim the module docstring makes: a resolved form is data, comparable
    # by `==`, never a live object graph. Two independent resolutions of one pipeline must
    # compare equal, which nothing holding a constructed plugin instance could promise.
    pipeline = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="docling"),))

    # Act
    first = resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)
    second = resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    # Assert
    assert first == second
    assert first is not second


def test_a_child_that_only_retargets_a_var_resolves_the_parents_stage_with_its_own_value() -> None:
    # Arrange — `02` §3 → *Derivation*: "a parent's improvement reaches its children."
    # `base` names a var in `with:`; `base-de` overrides it and nothing else.
    base = Pipeline(
        name="base",
        vars={"target_lang": "en"},
        stages=(
            StageDeclaration(id="extract", use="docling", config={"lang": "${var:target_lang}"}),
        ),
    )
    base_de = Pipeline(name="base-de", extends="base", vars={"target_lang": "de"})

    # Act
    resolved = resolution.resolve(
        base_de, registry=_registry(), contracts=_CONTRACTS, parents={"base": base}
    )

    # Assert
    assert resolved.name == "base-de"
    assert resolved.vars == {"target_lang": "de"}
    assert resolved.stages[0].config == _ExtractorConfig(lang="de")
    assert resolved.stages[0].provenance == "base"


def test_a_child_overriding_a_var_re_resolves_every_inherited_stage_at_any_depth() -> None:
    # Arrange — task 1.14, `02` §3 → *Language, and what a var is for*: "a child's
    # override re-resolves every inherited stage that references it." A single
    # referencing stage (the fixture above) cannot tell "the one stage got
    # re-resolved" apart from "every stage that references the var did," so `root`
    # carries two — `extract` and `chunk`, the two contracts this file already knows
    # compose, so the fixture proves the property without needing a third contract.
    # `mid` is a pure relay — it extends `root` and touches nothing at all, no
    # `vars`, no operators — proving depth is not special-cased: `02` §3 says
    # "depth adds no new case" of the operator chain, and `_walk_extends` merges
    # `vars` across the identical chain an operator walks. `base_de` is `02` §3's own
    # worked example, unchanged: "extends: base" plus "vars: {target_lang: de}" is
    # the entire file — retargeting a whole pipeline is those two lines even when the
    # pipeline being retargeted is two ancestors away.
    root = Pipeline(
        name="root",
        vars={"target_lang": "en"},
        stages=(
            StageDeclaration(id="extract", use="docling", config={"lang": "${var:target_lang}"}),
            StageDeclaration(id="chunk", use="sentence", config={"note": "${var:target_lang}"}),
        ),
    )
    mid = Pipeline(name="mid", extends="root")
    base_de = Pipeline(name="base-de", extends="mid", vars={"target_lang": "de"})

    # Act
    resolved = resolution.resolve(
        base_de,
        registry=_registry(),
        contracts=_CONTRACTS,
        parents={"root": root, "mid": mid},
    )

    # Assert — both inherited stages that reference the var carry the child's value,
    # two ancestors down through a relay that never mentioned it.
    assert resolved.stages[0].config == _ExtractorConfig(lang="de")
    assert resolved.stages[1].config == _ChunkerConfig(note="de")


def test_a_var_reference_only_matches_a_string_that_is_exactly_the_token() -> None:
    # Arrange — edge case, mirroring `weft_kernel.discovery.interpolate_env`: a string that
    # merely *contains* `${var:...}` is not a template engine's job here and is left as-is.
    pipeline = Pipeline(
        name="base",
        vars={"target_lang": "de"},
        stages=(
            StageDeclaration(
                id="extract", use="docling", config={"note": "target is ${var:target_lang} today"}
            ),
        ),
    )

    # Act
    resolved = resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    # Assert
    assert resolved.stages[0].config == _ExtractorConfig(note="target is ${var:target_lang} today")


def test_an_undefined_var_reference_fails_naming_the_var_and_the_pipeline() -> None:
    # Arrange
    pipeline = Pipeline(
        name="typo",
        stages=(StageDeclaration(id="extract", use="docling", config={"lang": "${var:missing}"}),),
    )

    # Act / Assert
    with pytest.raises(resolution.UndefinedVarError) as excinfo:
        resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    message = str(excinfo.value)
    assert "missing" in message
    assert "typo" in message
    # Repair for a reviewer finding against task 1.13: `stages` used to come back `()`
    # even though the stage holding the reference is known — `_substitute_vars` now
    # plumbs `stage.id` through the same way `pipeline_name` already was.
    assert excinfo.value.pipeline == "typo"
    assert excinfo.value.stages == ("extract",)
    assert "extract" in message


def test_an_undefined_var_reference_names_every_var_the_chain_does_define() -> None:
    # Arrange — the loud-failure invariant `weft_kernel.errors`' own module docstring
    # states: "what was wanted, why it is unavailable, and what the valid options are."
    # A one-character typo (`target_language` for `target_lang`) must be readable as a
    # typo from the message alone.
    pipeline = Pipeline(
        name="specific",
        vars={"target_lang": "de"},
        stages=(
            StageDeclaration(
                id="extract", use="docling", config={"lang": "${var:target_language}"}
            ),
        ),
    )

    # Act / Assert
    with pytest.raises(resolution.UndefinedVarError) as excinfo:
        resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    message = str(excinfo.value)
    assert "target_language" in message
    assert "target_lang" in message


def test_extends_naming_a_pipeline_absent_from_the_parent_lookup_fails_naming_it() -> None:
    # Arrange
    pipeline = Pipeline(name="orphan", extends="nowhere")

    # Act / Assert
    with pytest.raises(resolution.UnknownParentPipelineError) as excinfo:
        resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS, parents={})

    message = str(excinfo.value)
    assert "orphan" in message
    assert "nowhere" in message


def test_unknown_parent_names_every_pipeline_that_is_available_in_parents() -> None:
    # Arrange — the typo case: the name that would have worked is three lines away.
    base = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="docling"),))
    base_de = Pipeline(name="base-de", extends="base")
    pipeline = Pipeline(name="specific", extends="bases")

    # Act / Assert
    with pytest.raises(resolution.UnknownParentPipelineError) as excinfo:
        resolution.resolve(
            pipeline,
            registry=_registry(),
            contracts=_CONTRACTS,
            parents={"base": base, "base-de": base_de},
        )

    message = str(excinfo.value)
    assert "bases" in message
    assert "'base'" in message
    assert "'base-de'" in message


def test_a_cycle_in_extends_fails_naming_the_whole_chain() -> None:
    # Arrange
    a = Pipeline(name="a", extends="b")
    b = Pipeline(name="b", extends="a")

    # Act / Assert
    with pytest.raises(resolution.PipelineCycleError) as excinfo:
        resolution.resolve(a, registry=_registry(), contracts=_CONTRACTS, parents={"a": a, "b": b})

    message = str(excinfo.value)
    assert "a" in message
    assert "b" in message


def test_resolve_fails_loudly_for_an_unregistered_plugin_name() -> None:
    # Arrange — the plugin-exists check reuses `Registry.entry`'s own `UnknownPluginError`
    # rather than re-implementing it.
    pipeline = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="missing"),))

    # Act / Assert
    with pytest.raises(UnknownPluginError) as excinfo:
        resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    assert "missing" in str(excinfo.value)
    # Repair for a reviewer finding against `manual/user-manual.md` § 5: `UnknownPluginError`
    # is a direct `WeftError` subclass, never `PipelineResolutionError` — a `try/except
    # PipelineResolutionError` around `resolve()` does not catch this one, and the manual
    # now says so. Locked in here so a future refactor that folds it into the family cannot
    # silently make the manual's carve-out stale in the other direction either.
    assert not issubclass(UnknownPluginError, PipelineResolutionError)


def test_resolve_fails_on_an_unmet_requires_naming_the_stage_and_the_model() -> None:
    # Arrange — `chunk` requires `_Extracted`, but nothing earlier provides it.
    pipeline = Pipeline(name="base", stages=(StageDeclaration(id="chunk", use="sentence"),))

    # Act / Assert
    with pytest.raises(resolution.UnmetRequiresError) as excinfo:
        resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    message = str(excinfo.value)
    assert "chunk" in message
    assert "_Extracted" in message
    assert "(none)" in message  # nothing provided yet — the edge case for the listing
    # Repair for a reviewer finding against task 1.13: the four structured fields were
    # only ever checked via a sentinel construction, never against a real raise site —
    # so a bug swapping which stage or distribution a real call passed would have gone
    # unnoticed. `_Extracted.__namespace__` is `"weft-test-pack"`.
    assert excinfo.value.pipeline == "base"
    assert excinfo.value.stages == ("chunk",)
    assert excinfo.value.distributions == ("weft-test-pack",)
    assert excinfo.value.remedy == (
        "add an earlier stage that provides '_Extracted', or reorder 'base' so one already does."
    )


def test_an_unmet_requires_names_every_ext_model_earlier_stages_did_provide() -> None:
    # Arrange — `_Keywords` requires `_Extracted`, and an unrelated `_Marker` model is
    # provided ahead of it; the message must name what *is* available, not just what
    # was wanted, per `weft_kernel.errors`' own loud-failure invariant.
    class _Marker(ExtModel):
        __namespace__ = "weft-test-pack"
        __schema_version__ = "1.0.0"

    class _ProvidesMarker:
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = (_Marker,)
        intact: tuple[type[Property], ...] = ()
        destroys: tuple[type[Property], ...] = ()

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: str, ctx: Context) -> Outcome[list[str]]:
            return Produced(value=[payload])

    registry = Registry()
    registry.add(_Extractish, "marker-only", _ProvidesMarker, distribution="acme-marker")
    registry.add(_Chunkish, "sentence", _Chunker, distribution="weft-chunk")
    pipeline = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="marker-only"),
            StageDeclaration(id="chunk", use="sentence"),
        ),
    )

    # Act / Assert
    with pytest.raises(resolution.UnmetRequiresError) as excinfo:
        resolution.resolve(pipeline, registry=registry, contracts=_CONTRACTS)

    message = str(excinfo.value)
    assert "_Extracted" in message
    assert "_Marker" in message


def test_resolve_fails_when_consecutive_stages_do_not_compose() -> None:
    # Arrange — `chunk` (list[str] -> list[str]) before `extract` (str -> list[str]): the
    # second stage expects `str`, the first produced `list[str]`.
    pipeline = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="chunk", use="sentence"),
            StageDeclaration(id="extract", use="docling"),
        ),
    )

    # Act / Assert
    with pytest.raises(resolution.StageCompositionError) as excinfo:
        resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    message = str(excinfo.value)
    assert "chunk" in message
    assert "extract" in message
    # Repair for a reviewer finding against task 1.13 — see the identical note on
    # `test_resolve_fails_on_an_unmet_requires_naming_the_stage_and_the_model` above.
    assert excinfo.value.pipeline == "base"
    assert excinfo.value.stages == ("chunk", "extract")


def test_resolve_fails_when_an_earlier_stage_destroyed_a_property_this_stage_needs_intact() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Chunkish, "chunk-fixed", _DestroysWordBoundaries, distribution="weft-chunk")
    registry.add(_Chunkish, "hyphenation", _NeedsWordBoundariesIntact, distribution="acme-clean")
    pipeline = Pipeline(
        name="cleaning",
        stages=(
            StageDeclaration(id="chunk", use="chunk-fixed"),
            StageDeclaration(id="hyphenation", use="hyphenation"),
        ),
    )
    contracts = {"chunk": _Chunkish, "hyphenation": _Chunkish}

    # Act / Assert
    with pytest.raises(resolution.IntactViolationError) as excinfo:
        resolution.resolve(pipeline, registry=registry, contracts=contracts)

    message = str(excinfo.value)
    assert "hyphenation" in message
    assert "chunk" in message
    assert "_WordBoundaries" in message
    # Repair for a reviewer finding against task 1.13: `stages` is `(stage.id, destroyer)`
    # — the violating stage first, the one that destroyed the property second — and a
    # regression that swapped the order would pass every assertion above (both names
    # merely appear in the message) while getting the pair backwards.
    assert excinfo.value.pipeline == "cleaning"
    assert excinfo.value.stages == ("hyphenation", "chunk")
    assert excinfo.value.remedy == "move 'hyphenation' to before 'chunk', never after."


def test_resolve_succeeds_when_the_stage_needing_intact_runs_before_the_one_that_destroys_it() -> (
    None
):
    # Arrange — reordered: the position `02` §3 says would be legal.
    registry = Registry()
    registry.add(_Chunkish, "chunk-fixed", _DestroysWordBoundaries, distribution="weft-chunk")
    registry.add(_Chunkish, "hyphenation", _NeedsWordBoundariesIntact, distribution="acme-clean")
    pipeline = Pipeline(
        name="cleaning",
        stages=(
            StageDeclaration(id="hyphenation", use="hyphenation"),
            StageDeclaration(id="chunk", use="chunk-fixed"),
        ),
    )
    contracts = {"chunk": _Chunkish, "hyphenation": _Chunkish}

    # Act
    resolved = resolution.resolve(pipeline, registry=registry, contracts=contracts)

    # Assert
    assert [stage.id for stage in resolved.stages] == ["hyphenation", "chunk"]


def test_every_resolution_error_is_a_pipeline_resolution_error() -> None:
    # Arrange / Act / Assert — `02` §3 → *When resolution fails*: "each failure is its own
    # `WeftError` subclass under a `PipelineResolutionError` family base."
    assert issubclass(resolution.UnknownParentPipelineError, PipelineResolutionError)
    assert issubclass(resolution.PipelineCycleError, PipelineResolutionError)
    assert issubclass(resolution.UnmetRequiresError, PipelineResolutionError)
    assert issubclass(resolution.StageCompositionError, PipelineResolutionError)
    assert issubclass(resolution.IntactViolationError, PipelineResolutionError)
    assert issubclass(resolution.UndefinedVarError, PipelineResolutionError)
    assert issubclass(resolution.StaleOperatorTargetError, PipelineResolutionError)
    assert issubclass(resolution.OperatorIdCollisionError, PipelineResolutionError)
    assert issubclass(resolution.InvalidStageConfigError, PipelineResolutionError)
    assert issubclass(resolution.StageNotConfigurableError, PipelineResolutionError)
    assert issubclass(resolution.SlotOrderConflictError, PipelineResolutionError)
    assert issubclass(resolution.DuplicateContributionError, PipelineResolutionError)


def test_resolve_accepts_an_empty_parents_mapping_by_default() -> None:
    # Arrange — a non-extending pipeline needs no `parents` argument at all.
    pipeline = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="docling"),))

    # Act
    resolved = resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    # Assert
    assert resolved.stages[0].provenance == "base"
    assert dict(resolved.vars) == {}


def test_resolved_pipeline_vars_and_config_are_read_only() -> None:
    # Arrange
    pipeline = Pipeline(
        name="base",
        vars={"target_lang": "en"},
        stages=(StageDeclaration(id="extract", use="docling", config={"a": 1}),),
    )

    # Act
    resolved = resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    # Assert
    with pytest.raises(TypeError):
        resolved.vars["target_lang"] = "de"  # type: ignore[index]
    with pytest.raises(TypeError):
        resolved.stages[0].config["a"] = 2  # type: ignore[index]


def test_resolve_is_safe_to_call_repeatedly_with_no_parents_argument_at_all() -> None:
    # Arrange / Act / Assert — the default `parents` value is shared across every call that
    # omits it; nothing may write through it, so two such calls can never interfere with
    # each other through a mutated default the way a plain `{}` default classically could.
    pipeline = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="docling"),))

    first = resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)
    second = resolution.resolve(pipeline, registry=_registry(), contracts=_CONTRACTS)

    assert first == second


# --- task 1.4: the four operators -----------------------------------------------------


def test_an_insert_operator_adds_a_stage_after_the_named_target_with_its_own_provenance() -> None:
    # Arrange — `02` §3's own driving example: `insert: {after: chunk, stage: {use: keybert}}`.
    base = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk", use="sentence"),
        ),
    )
    specific = Pipeline(
        name="specific",
        extends="base",
        insert=(
            InsertOperator(after="chunk", stage=StageDeclaration(id="keywords", use="keybert")),
        ),
    )

    # Act
    resolved = resolution.resolve(
        specific,
        registry=_registry_with_operator_plugins(),
        contracts=_CONTRACTS_WITH_KEYWORDS,
        parents={"base": base},
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["extract", "chunk", "keywords"]
    assert resolved.stages[2].provenance == "specific"


def test_an_insert_operator_can_position_before_the_named_target() -> None:
    # Arrange — edge case: the other anchor.
    base = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk", use="sentence"),
        ),
    )
    specific = Pipeline(
        name="specific",
        extends="base",
        insert=(
            InsertOperator(before="chunk", stage=StageDeclaration(id="keywords", use="keybert")),
        ),
    )

    # Act
    resolved = resolution.resolve(
        specific,
        registry=_registry_with_operator_plugins(),
        contracts=_CONTRACTS_WITH_KEYWORDS,
        parents={"base": base},
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["extract", "keywords", "chunk"]


def test_a_replace_operator_swaps_the_plugin_and_keeps_the_stage_id_and_position() -> None:
    # Arrange
    base = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk", use="sentence"),
        ),
    )
    specific = Pipeline(
        name="specific", extends="base", replace=(StageDeclaration(id="chunk", use="sentence-v2"),)
    )

    # Act
    resolved = resolution.resolve(
        specific,
        registry=_registry_with_operator_plugins(),
        contracts=_CONTRACTS,
        parents={"base": base},
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["extract", "chunk"]
    assert resolved.stages[1].use == "sentence-v2"
    assert resolved.stages[1].provenance == "specific"


def test_a_remove_operator_drops_the_stage_by_id() -> None:
    # Arrange
    base = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk", use="sentence"),
        ),
    )
    specific = Pipeline(name="specific", extends="base", remove=("chunk",))

    # Act
    resolved = resolution.resolve(
        specific, registry=_registry(), contracts=_CONTRACTS, parents={"base": base}
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["extract"]


def test_a_set_operator_merges_new_configuration_without_changing_the_plugin_or_the_parent() -> (
    None
):
    # Arrange — also proves task 1.4's no-in-place-mutation requirement: `base` itself
    # must be unchanged after resolving a child that `set`s one of its stages.
    base = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk", use="sentence", config={"size": 512, "overlap": 50}),
        ),
    )
    specific = Pipeline(
        name="specific", extends="base", set=(SetOperator(id="chunk", config={"size": 256}),)
    )

    # Act
    resolved = resolution.resolve(
        specific, registry=_registry(), contracts=_CONTRACTS, parents={"base": base}
    )

    # Assert — provenance stays "base": `set` changes configuration, never which
    # pipeline is responsible for the stage's plugin existing at all.
    assert resolved.stages[1].use == "sentence"
    assert resolved.stages[1].config == _ChunkerConfig(size=256, overlap=50)
    assert resolved.stages[1].provenance == "base"
    assert base.stages[1].config == {"size": 512, "overlap": 50}


def test_remove_written_above_insert_lets_a_new_stage_reuse_the_removed_id() -> None:
    # Arrange — task 1.4's load-bearing claim: written order is application order.
    # `remove:` above `insert:` expresses a move — drop 'chunk', then reintroduce a stage
    # named 'chunk' running a different plugin, right where it used to sit.
    base = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk", use="sentence"),
        ),
    )
    specific = Pipeline(
        name="specific",
        extends="base",
        remove=("chunk",),
        insert=(
            InsertOperator(after="extract", stage=StageDeclaration(id="chunk", use="sentence-v2")),
        ),
    )

    # Act
    resolved = resolution.resolve(
        specific,
        registry=_registry_with_operator_plugins(),
        contracts=_CONTRACTS,
        parents={"base": base},
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["extract", "chunk"]
    assert resolved.stages[1].use == "sentence-v2"


def test_insert_written_above_remove_on_the_same_id_collides() -> None:
    # Arrange — the same two operators as the test above, written in the opposite order:
    # `insert` runs first, while the old 'chunk' still exists, so it collides.
    base = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk", use="sentence"),
        ),
    )
    specific = Pipeline(
        name="specific",
        extends="base",
        insert=(
            InsertOperator(after="extract", stage=StageDeclaration(id="chunk", use="sentence-v2")),
        ),
        remove=("chunk",),
    )

    # Act / Assert
    with pytest.raises(resolution.OperatorIdCollisionError) as excinfo:
        resolution.resolve(
            specific,
            registry=_registry_with_operator_plugins(),
            contracts=_CONTRACTS,
            parents={"base": base},
        )

    message = str(excinfo.value)
    assert "chunk" in message
    assert "specific" in message


def test_an_insert_operator_refuses_a_new_id_that_already_exists() -> None:
    # Arrange — `02` §3: "insert fails equally when its new id collides with an existing
    # one" — no `remove` involved this time, the simplest form of the collision.
    base = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk", use="sentence"),
        ),
    )
    specific = Pipeline(
        name="specific",
        extends="base",
        insert=(
            InsertOperator(after="extract", stage=StageDeclaration(id="chunk", use="sentence-v2")),
        ),
    )

    # Act / Assert
    with pytest.raises(resolution.OperatorIdCollisionError):
        resolution.resolve(
            specific,
            registry=_registry_with_operator_plugins(),
            contracts=_CONTRACTS,
            parents={"base": base},
        )


def test_insert_after_an_unknown_target_names_the_pipeline_the_parent_and_the_existing_ids() -> (
    None
):
    # Arrange
    base = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="docling"),))
    specific = Pipeline(
        name="specific",
        extends="base",
        insert=(
            InsertOperator(after="missing", stage=StageDeclaration(id="keywords", use="keybert")),
        ),
    )

    # Act / Assert
    with pytest.raises(resolution.StaleOperatorTargetError) as excinfo:
        resolution.resolve(
            specific,
            registry=_registry_with_operator_plugins(),
            contracts=_CONTRACTS_WITH_KEYWORDS,
            parents={"base": base},
        )

    message = str(excinfo.value)
    assert "missing" in message
    assert "specific" in message
    assert "base" in message
    assert "extract" in message


def test_replace_of_an_unknown_id_fails_the_same_stale_target_check() -> None:
    # Arrange
    base = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="docling"),))
    specific = Pipeline(
        name="specific", extends="base", replace=(StageDeclaration(id="missing", use="docling"),)
    )

    # Act / Assert
    with pytest.raises(resolution.StaleOperatorTargetError) as excinfo:
        resolution.resolve(
            specific, registry=_registry(), contracts=_CONTRACTS, parents={"base": base}
        )

    assert "missing" in str(excinfo.value)


def test_set_of_an_unknown_id_fails_the_same_stale_target_check() -> None:
    # Arrange
    base = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="docling"),))
    specific = Pipeline(
        name="specific", extends="base", set=(SetOperator(id="missing", config={"a": 1}),)
    )

    # Act / Assert
    with pytest.raises(resolution.StaleOperatorTargetError) as excinfo:
        resolution.resolve(
            specific, registry=_registry(), contracts=_CONTRACTS, parents={"base": base}
        )

    assert "missing" in str(excinfo.value)


def test_remove_of_an_unknown_id_gets_no_exemption_from_the_strict_check() -> None:
    # Arrange — `02` §3: "remove gets no exemption... a remove line matching nothing is
    # evidence the parent moved under you."
    base = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="docling"),))
    specific = Pipeline(name="specific", extends="base", remove=("missing",))

    # Act / Assert
    with pytest.raises(resolution.StaleOperatorTargetError) as excinfo:
        resolution.resolve(
            specific, registry=_registry(), contracts=_CONTRACTS, parents={"base": base}
        )

    assert "missing" in str(excinfo.value)


def test_operators_apply_at_any_depth_through_the_extends_chain() -> None:
    # Arrange — `02` §3: "`extends` takes one parent, at any depth... depth adds no new
    # case." Grandparent carries the stages; parent removes one; child inserts one.
    grandparent = Pipeline(
        name="grandparent",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk", use="sentence"),
        ),
    )
    parent = Pipeline(name="parent", extends="grandparent", remove=("chunk",))
    child = Pipeline(
        name="child",
        extends="parent",
        insert=(
            InsertOperator(after="extract", stage=StageDeclaration(id="keywords", use="keybert")),
        ),
    )

    # Act
    resolved = resolution.resolve(
        child,
        registry=_registry_with_operator_plugins(),
        contracts=_CONTRACTS_WITH_KEYWORDS,
        parents={"grandparent": grandparent, "parent": parent},
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["extract", "keywords"]
    assert resolved.stages[0].provenance == "grandparent"
    assert resolved.stages[1].provenance == "child"


def test_a_cycle_is_refused_even_when_the_pipelines_in_it_carry_operators() -> None:
    # Arrange — 1.3's `PipelineCycleError` already exists; this is the same check exercised
    # with operators present, per task 1.4's own remit.
    a = Pipeline(name="a", extends="b", remove=("x",))
    b = Pipeline(name="b", extends="a")

    # Act / Assert
    with pytest.raises(resolution.PipelineCycleError) as excinfo:
        resolution.resolve(a, registry=_registry(), contracts=_CONTRACTS, parents={"a": a, "b": b})

    message = str(excinfo.value)
    assert "a" in message
    assert "b" in message


def test_a_parent_change_flows_through_the_next_resolve_of_an_operator_bearing_child() -> None:
    # Arrange — `02` §3: "the parent is referenced, never copied: resolution reads live
    # parents." `child`'s own operator never changes; only what `base` names does.
    base_v1 = Pipeline(name="base", stages=(StageDeclaration(id="extract", use="docling"),))
    child = Pipeline(
        name="child",
        extends="base",
        insert=(
            InsertOperator(after="extract", stage=StageDeclaration(id="chunk", use="sentence")),
        ),
    )

    # Act — first resolution, against the parent as it stood then.
    resolved_v1 = resolution.resolve(
        child, registry=_registry(), contracts=_CONTRACTS, parents={"base": base_v1}
    )

    # Assert
    assert [stage.id for stage in resolved_v1.stages] == ["extract", "chunk"]
    assert resolved_v1.stages[0].config == _ExtractorConfig()

    # Act — the parent changes; nothing about `child` is touched.
    base_v2 = Pipeline(
        name="base", stages=(StageDeclaration(id="extract", use="docling", config={"lang": "en"}),)
    )
    resolved_v2 = resolution.resolve(
        child, registry=_registry(), contracts=_CONTRACTS, parents={"base": base_v2}
    )

    # Assert — the very next resolution of the same child sees the parent's edit.
    assert resolved_v2.stages[0].config == _ExtractorConfig(lang="en")


# --- task 1.5: with: validated against the plugin's own typed model ------------------


def test_the_same_plugin_resolves_twice_with_different_configuration_in_one_pipeline() -> None:
    # Arrange — the ledger's own property: one plugin (`sentence`), two stage ids, two
    # `with:` blocks. `extract` first, so `_Chunker.requires = (_Extracted,)` is met for
    # both chunk stages.
    pipeline = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling"),
            StageDeclaration(id="chunk-a", use="sentence", config={"size": 256}),
            StageDeclaration(id="chunk-b", use="sentence", config={"size": 1024, "overlap": 100}),
        ),
    )
    contracts: dict[str, type[object]] = {
        "extract": _Extractish,
        "chunk-a": _Chunkish,
        "chunk-b": _Chunkish,
    }

    # Act
    resolved = resolution.resolve(pipeline, registry=_registry(), contracts=contracts)

    # Assert — same plugin, independently validated, different results.
    assert resolved.stages[1].use == resolved.stages[2].use == "sentence"
    assert resolved.stages[1].config == _ChunkerConfig(size=256)
    assert resolved.stages[2].config == _ChunkerConfig(size=1024, overlap=100)
    assert resolved.stages[1].config != resolved.stages[2].config


def test_an_invalid_with_block_fails_naming_the_stage_the_plugin_the_field_and_what_the_model_accepts() -> (  # noqa: E501
    None
):
    # Arrange — a plugin whose model actually constrains something, unlike the permissive
    # `_ExtractorConfig`/`_ChunkerConfig` every other test in this file reuses.
    class _StrictConfig(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        top_n: int

    class _Strict:
        requires: tuple[type[ExtModel], ...] = ()
        provides: tuple[type[ExtModel], ...] = ()
        intact: tuple[type[Property], ...] = ()
        destroys: tuple[type[Property], ...] = ()
        config_model = _StrictConfig

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: list[str], ctx: Context) -> Outcome[list[str]]:
            return Produced(value=payload)

    registry = Registry()
    registry.add(_Chunkish, "strict", _Strict, distribution="acme-strict")
    pipeline = Pipeline(
        name="base",
        stages=(StageDeclaration(id="chunk", use="strict", config={"top_n": "eight"}),),
    )

    # Act / Assert
    with pytest.raises(resolution.InvalidStageConfigError) as excinfo:
        resolution.resolve(pipeline, registry=registry, contracts={"chunk": _Chunkish})

    message = str(excinfo.value)
    assert "chunk" in message
    assert "_Chunkish:strict" in message
    assert "top_n" in message
    assert "_StrictConfig" in message


def test_a_plugin_publishing_no_config_model_still_resolves_with_an_empty_with_block() -> None:
    # Arrange — `_Keywords` declares no `config_model` at all: an absent model means the
    # `with:` block must be empty, and it is here.
    pipeline = Pipeline(name="base", stages=(StageDeclaration(id="keywords", use="keybert"),))

    # Act
    resolved = resolution.resolve(
        pipeline, registry=_registry_with_operator_plugins(), contracts={"keywords": _Chunkish}
    )

    # Assert
    assert resolved.stages[0].config == {}


def test_a_non_empty_with_block_for_a_plugin_with_no_config_model_is_refused() -> None:
    # Arrange — `02` §3's own driving example writes `with: {top_n: 8}` for `keybert`; here
    # `_Keywords` is a plugin nobody gave a `config_model`, reproducing on purpose the
    # mistake of a `with:` block for a plugin that cannot accept one — the block must not
    # be silently accepted and dropped.
    pipeline = Pipeline(
        name="base", stages=(StageDeclaration(id="keywords", use="keybert", config={"top_n": 8}),)
    )

    # Act / Assert
    with pytest.raises(resolution.StageNotConfigurableError) as excinfo:
        resolution.resolve(
            pipeline, registry=_registry_with_operator_plugins(), contracts={"keywords": _Chunkish}
        )

    message = str(excinfo.value)
    assert "keywords" in message
    assert "_Chunkish:keybert" in message


# --- Task 1.11: slots — a contribution targets a slot, never a stage id ----------------


def _base_with_slot() -> Pipeline:
    # `sentence-narrowed` (`_ChunkerNarrowedToProse`), not `sentence` (`_Chunker`):
    # `_Chunker.requires = (_Extracted,)`, and these fixtures are about slot placement,
    # not requires/provides — the narrowed twin declares no `requires` at all, so a bare
    # `chunk` stage resolves standalone.
    return Pipeline(
        name="base",
        stages=(StageDeclaration(id="chunk", use="sentence-narrowed"),),
        slots=(SlotDeclaration(id="enrich", after="chunk"),),
    )


def test_a_single_contribution_fills_its_slot_with_a_qualified_id_and_its_own_provenance() -> None:
    # Arrange — `02` §3 → *Slots*, and `ResolvedStage.provenance`'s own docstring: "Task
    # 1.11 is what first lets a pack be the answer here instead of a pipeline."
    contribution = resolution.Contribution(
        slot="enrich", distribution="aaa-pack", stage=StageDeclaration(id="extra", use="aaa-slot")
    )
    contracts = {**_CONTRACTS, "aaa-pack:extra": _Chunkish}

    # Act
    resolved = resolution.resolve(
        _base_with_slot(),
        registry=_registry_with_slot_plugins(),
        contracts=contracts,
        contributions=(contribution,),
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["chunk", "aaa-pack:extra"]
    assert resolved.stages[1].provenance == "aaa-pack"
    assert resolved.stages[1].distribution == "aaa-pack"
    assert resolved.unplaced_contributions == ()


def test_two_contributions_order_by_their_declared_relation_not_by_distribution_name() -> None:
    # Arrange — `zzz-needs` needs `_WordBoundaries` intact, `aaa-destroys` destroys it; the
    # distribution names sort the *opposite* way the declared relation requires, so this is
    # the proof the relation decided the order, not an accidental agreement with the name.
    contributions = (
        resolution.Contribution(
            slot="enrich",
            distribution="zzz-needs",
            stage=StageDeclaration(id="hyphenation", use="hyphen-fix"),
        ),
        resolution.Contribution(
            slot="enrich",
            distribution="aaa-destroys",
            stage=StageDeclaration(id="clean", use="chunker"),
        ),
    )
    contracts = {
        **_CONTRACTS,
        "zzz-needs:hyphenation": _Chunkish,
        "aaa-destroys:clean": _Chunkish,
    }

    # Act
    resolved = resolution.resolve(
        _base_with_slot(),
        registry=_registry_with_slot_plugins(),
        contracts=contracts,
        contributions=contributions,
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == [
        "chunk",
        "zzz-needs:hyphenation",
        "aaa-destroys:clean",
    ]


def test_two_contributions_with_no_ordering_relation_break_the_tie_by_distribution_name() -> None:
    # Arrange — `02` §3: "genuine ties break by distribution name, so two machines with the
    # same installs resolve identically." Passed in reverse (`zzz-pack` before `aaa-pack`)
    # to prove the output order is not merely echoing the input order.
    contributions = (
        resolution.Contribution(
            slot="enrich",
            distribution="zzz-pack",
            stage=StageDeclaration(id="extra", use="zzz-slot"),
        ),
        resolution.Contribution(
            slot="enrich",
            distribution="aaa-pack",
            stage=StageDeclaration(id="extra", use="aaa-slot"),
        ),
    )
    contracts = {**_CONTRACTS, "zzz-pack:extra": _Chunkish, "aaa-pack:extra": _Chunkish}

    # Act
    resolved = resolution.resolve(
        _base_with_slot(),
        registry=_registry_with_slot_plugins(),
        contracts=contracts,
        contributions=contributions,
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["chunk", "aaa-pack:extra", "zzz-pack:extra"]


def test_two_contributions_naming_the_same_qualified_id_are_refused_not_silently_collapsed() -> (
    None
):
    # Arrange — repair for a reviewer finding against the task 1.11 commit: two
    # `Contribution`s from the same distribution offering the same local stage id used to
    # collapse to whichever `_order_contributions` built last, with the first silently gone
    # — not placed, not refused, not in `unplaced_contributions` either. Both target `enrich`
    # here (same slot), which is the shape the finding reproduced; `_refuse_duplicate_
    # contributions` checks across slots too, but one slot is enough to prove the refusal.
    contributions = (
        resolution.Contribution(
            slot="enrich", distribution="aaa-pack", stage=StageDeclaration(id="e", use="aaa-slot")
        ),
        resolution.Contribution(
            slot="enrich", distribution="aaa-pack", stage=StageDeclaration(id="e", use="zzz-slot")
        ),
    )
    contracts = {**_CONTRACTS, "aaa-pack:e": _Chunkish}

    # Act / Assert
    with pytest.raises(resolution.DuplicateContributionError) as excinfo:
        resolution.resolve(
            _base_with_slot(),
            registry=_registry_with_slot_plugins(),
            contracts=contracts,
            contributions=contributions,
        )

    message = str(excinfo.value)
    assert "aaa-pack" in message
    assert "aaa-pack:e" in message


def test_two_slots_sharing_one_anchor_fill_in_the_order_the_document_declared_them() -> None:
    # Arrange — repair for a reviewer finding: `_fill_slots` computes each slot's anchor
    # from the original `stages` list and inserts highest-anchor-first so an earlier
    # insertion never shifts a later slot's already-computed index — but with no
    # declaration-position tie-break, two slots sharing one anchor came out *reversed*
    # from the order the document wrote them in. Both `enrich` and `annotate` anchor on
    # `chunk` here, `enrich` declared first — `02` §3: "the written order is the pipeline."
    pipeline = Pipeline(
        name="base",
        stages=(StageDeclaration(id="chunk", use="sentence-narrowed"),),
        slots=(
            SlotDeclaration(id="enrich", after="chunk"),
            SlotDeclaration(id="annotate", after="chunk"),
        ),
    )
    contributions = (
        resolution.Contribution(
            slot="enrich", distribution="aaa-pack", stage=StageDeclaration(id="e", use="aaa-slot")
        ),
        resolution.Contribution(
            slot="annotate", distribution="zzz-pack", stage=StageDeclaration(id="n", use="zzz-slot")
        ),
    )
    contracts = {**_CONTRACTS, "aaa-pack:e": _Chunkish, "zzz-pack:n": _Chunkish}

    # Act
    resolved = resolution.resolve(
        pipeline,
        registry=_registry_with_slot_plugins(),
        contracts=contracts,
        contributions=contributions,
    )

    # Assert — declared order preserved: `enrich`'s contribution before `annotate`'s, both
    # still after `chunk`. Flipping `_fill_slots`'s sort back to a bare `reverse=True` on
    # anchor index alone (no declaration-position tie-break) reverses this pair.
    assert [stage.id for stage in resolved.stages] == ["chunk", "aaa-pack:e", "zzz-pack:n"]


def test_a_contribution_with_no_matching_slot_is_recorded_as_unplaced_rather_than_failing() -> None:
    # Arrange — `02` §3: "a contribution with no matching slot is a recorded no-op"; the
    # pipeline below declares no slot at all, so nothing breaks and nothing is silent.
    pipeline = Pipeline(
        name="base", stages=(StageDeclaration(id="chunk", use="sentence-narrowed"),)
    )
    contribution = resolution.Contribution(
        slot="enrich", distribution="aaa-pack", stage=StageDeclaration(id="extra", use="aaa-slot")
    )
    contracts = {**_CONTRACTS, "aaa-pack:extra": _Chunkish}

    # Act
    resolved = resolution.resolve(
        pipeline,
        registry=_registry_with_slot_plugins(),
        contracts=contracts,
        contributions=(contribution,),
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["chunk"]
    assert len(resolved.unplaced_contributions) == 1
    assert "aaa-pack:extra" in resolved.unplaced_contributions[0]
    assert "enrich" in resolved.unplaced_contributions[0]


def test_removing_a_slot_refuses_every_contribution_to_it_without_naming_a_pack() -> None:
    # Arrange — `02` §3: "`remove: enrich` drops the slot itself, which is how a pipeline
    # refuses contributions without naming any pack."
    specific = Pipeline(name="specific", extends="base", remove=("enrich",))
    contribution = resolution.Contribution(
        slot="enrich", distribution="aaa-pack", stage=StageDeclaration(id="extra", use="aaa-slot")
    )
    contracts = {**_CONTRACTS, "aaa-pack:extra": _Chunkish}

    # Act
    resolved = resolution.resolve(
        specific,
        registry=_registry_with_slot_plugins(),
        contracts=contracts,
        parents={"base": _base_with_slot()},
        contributions=(contribution,),
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["chunk"]
    assert len(resolved.unplaced_contributions) == 1


def test_set_targeting_a_contributed_id_overrides_its_config_once_the_pack_is_installed() -> None:
    # Arrange — `02` §3: a contributed stage "may be `set` but never `replaced` or
    # `removed`". `configurable` carries `_ChunkerConfig` as its `config_model`, so the
    # merge is checked against a real model, not just presence of a key.
    specific = Pipeline(
        name="specific",
        extends="base",
        set=(SetOperator(id="aaa-pack:extra", config={"overlap": 5}),),
    )
    contribution = resolution.Contribution(
        slot="enrich",
        distribution="aaa-pack",
        stage=StageDeclaration(id="extra", use="configurable", config={"size": 100}),
    )
    contracts = {**_CONTRACTS, "aaa-pack:extra": _Chunkish}

    # Act
    resolved = resolution.resolve(
        specific,
        registry=_registry_with_slot_plugins(),
        contracts=contracts,
        parents={"base": _base_with_slot()},
        contributions=(contribution,),
    )

    # Assert
    assert resolved.stages[1].id == "aaa-pack:extra"
    assert resolved.stages[1].config == _ChunkerConfig(size=100, overlap=5)
    assert resolved.unapplied_operators == ()


def test_set_targeting_a_contributed_id_is_recorded_unapplied_when_the_pack_is_not_installed() -> (
    None
):
    # Arrange — `02` §3: "Installation-dependent targets are recorded, never fatal... `set:
    # weft-graph:entities` where that pack is absent is an unapplied operator in the
    # resolved form, not a resolution failure." No contribution at all is supplied here.
    specific = Pipeline(
        name="specific",
        extends="base",
        set=(SetOperator(id="acme-graph:entities", config={"a": 1}),),
    )

    # Act
    resolved = resolution.resolve(
        specific,
        registry=_registry_with_slot_plugins(),
        contracts=_CONTRACTS,
        parents={"base": _base_with_slot()},
    )

    # Assert
    assert [stage.id for stage in resolved.stages] == ["chunk"]
    assert len(resolved.unapplied_operators) == 1
    assert "acme-graph:entities" in resolved.unapplied_operators[0]


def test_two_contributions_whose_ordering_constraints_contradict_each_other_are_refused() -> None:
    # Arrange — `_ContributionConflictA` needs `_Casing` intact and destroys
    # `_WordBoundaries`; `_ContributionConflictB` needs `_WordBoundaries` intact and
    # destroys `_Casing` — each must legally precede the other, so no order satisfies both.
    contributions = (
        resolution.Contribution(
            slot="enrich", distribution="acme-a", stage=StageDeclaration(id="a", use="conflict-a")
        ),
        resolution.Contribution(
            slot="enrich", distribution="acme-b", stage=StageDeclaration(id="b", use="conflict-b")
        ),
    )
    contracts = {**_CONTRACTS, "acme-a:a": _Chunkish, "acme-b:b": _Chunkish}

    # Act / Assert
    with pytest.raises(resolution.SlotOrderConflictError) as excinfo:
        resolution.resolve(
            _base_with_slot(),
            registry=_registry_with_slot_plugins(),
            contracts=contracts,
            contributions=contributions,
        )

    message = str(excinfo.value)
    assert "acme-a" in message
    assert "acme-b" in message


def test_a_slots_anchor_removed_by_a_descendant_fails_naming_what_does_still_exist() -> None:
    # Arrange — `02` §3's own strictness for the four operators applies here too: an
    # ancestor's own `remove` can move the ground out from under a slot it never touched.
    specific = Pipeline(name="specific", extends="base", remove=("chunk",))

    # Act / Assert
    with pytest.raises(resolution.StaleOperatorTargetError) as excinfo:
        resolution.resolve(
            specific,
            registry=_registry_with_slot_plugins(),
            contracts=_CONTRACTS,
            parents={"base": _base_with_slot()},
        )

    message = str(excinfo.value)
    assert "enrich" in message
    assert "chunk" in message
