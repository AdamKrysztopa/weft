"""Fitness function 11 — pipeline integrity. `01` -> *Fitness functions* item 11; `02` §3.

"Two clauses, from G2, both categorical and carrying no tuning constants." Neither clause
is a threshold or a percentage — each is a property that either holds or does not, the same
discipline fitness functions 7, 8 and 9 already carry for the identical reason: a number
nobody can defend gets re-baselined until it means nothing.

**(a) The operator set stays closed.** `02` §3: "the set stays closed until something real
needs a fifth," and a rule with no mechanism is exactly what this section exists to prevent.
The ratchet's *pinned* half — `CLOSED_OPERATOR_SET`, four names, and the waiver constant
below it — is written by hand, the same way `test_ff0_gate_in_the_gate.py`'s
`ARCHITECTURE_TASKS` is: a ratchet's anchor has to be pinned somewhere, and the test file is
where every other ratchet in this suite pins its own. What must **not** be hand-typed a
second time is the *actual* side of the comparison — "the actual operator fields on the
model" — because a second, disconnected list of the same four strings is precisely the
two-lists bug `docs/README.md` opens by describing: it is correct today and has no
mechanism keeping it correct tomorrow. `weft_kernel.pipeline.Pipeline` closes that gap
itself: `insert`, `replace`, `remove` and `set` each carry
`Field(json_schema_extra={PIPELINE_OPERATOR_MARK: True})` in the class body — the one place
in the tree that *decides* a field is an operator block — and `_marked_operator_fields`
below reads that mark off `Pipeline.model_fields`, never off a list this file maintains.
Add a fifth field carrying the mark (a `move` operator, say) and the actual side grows to
five with no edit here at all; the pinned side stays at four until someone edits
`OPERATORS_WAIVED_BEYOND_THE_CLOSED_SET` and records why in `docs/README.md`'s decision log.

**(b) Every shipped pipeline resolves.** "A pipeline file is text that rots silently while
every unit test passes" — `01`'s own words, and the reference's own worked example: a strategy
that registers, is listed, is described to an LLM in a routing prompt, and can never run
(`reference/study/02-discovery-and-config.md:226-234`). This clause finds every pipeline
document a first-party pack ships, an example pack ships, or a page under `manual/` quotes
as runnable, and resolves each one against the registry `discover()` actually builds from
the installed distributions — never a registry this file hand-assembles to make a
particular document pass. **How it fails:** rename `keybert` to `keyword-extractor` and
leave a shipped `specific.yaml` naming the old one — `_infer_contract` finds no contract
registers that name at all, and the failure is reported before `resolve()` is even called,
the same way a caller supplying `resolve()`'s `contracts:` argument today would have to
find out. An operator target that moved is `resolve()`'s own `StaleOperatorTargetError`,
caught here as a `WeftError` — `weft_kernel.errors.WeftError`'s own docstring: "the
catch-specific-exceptions rule applies to callers of this library exactly as it applies
inside it," which is why this file catches that name and nothing broader.

**Where the found set comes from, and why the check cannot pass on an empty one.** Three
sources, matching `01`'s own wording: `packages/*/pipelines/*.yaml` (a first-party pack),
`examples/*/pipelines/*.yaml` (an example pack), and every ` ```yaml id=pipeline:<name> `
fenced block under `manual/` — a tagging convention deliberately distinct from
`manual/operations-guide.md`'s own ` ```yaml path=compose.yaml `: that one claims "this text
is the real file, included, not retyped"; this one claims "this text is a pipeline document
that must resolve," which is a different property and earns a different tag rather than
overloading one that already means something else. The `examples/*/pipelines/*.yaml` glob is
still empty in this tree — no example pack ships a pipeline document yet, which is fine,
because the mechanism that would find one is what has to exist, not an instance of one.
`packages/*/pipelines/*.yaml` stopped being empty at task **2.19**: `weft-retrieve` ships
`retrieve-then-generate.yaml` (`.phase2-design.md` §4's V3 baseline — `vector-top-k` →
`single-list` → `repack` → `cited-answer`) and `no-retrieval.yaml` (ledger 2.13's own
deferred pairing, `no-retrieval` → `single-list` → `repack` →
`cited-answer(when_no_evidence=answer_from_memory)`), the pipeline both ledger 2.13 and
2.14 named and left for whichever of `single-list` (2.7), `cited-answer` (2.9) or `repack`
(2.19) closed last. `manual/user-manual.md` already carries two `id=pipeline:...` blocks
(`02` §3's own `base`/`specific` walkthrough), so the combined set was never empty even
before that. `test_at_least_one_shipped_or_quoted_pipeline_is_found`
is the floor that makes this true a fact rather than an accident of what happens to exist —
`08` §3's own rule, "a check with no floor is the reference's `test_keys_parity` with a
different subject," applied to an architecture check instead of a documentation one.
"""

from __future__ import annotations

import re
import sys
import tomllib
from collections.abc import Mapping
from importlib import import_module
from pathlib import Path
from typing import Final, cast

import pytest
import yaml
from pydantic import BaseModel, Field, ValidationError

from weft_kernel.discovery import PackRegistrar, discover
from weft_kernel.errors import WeftError
from weft_kernel.pipeline import PIPELINE_OPERATOR_MARK, Pipeline, is_pipeline_operator_field
from weft_kernel.registry import Registry, UnknownPluginError
from weft_kernel.resolution import resolve

from .conftest import REPO_ROOT

# --- (a) the operator set stays closed ----------------------------------------------------

#: `02` §3's own closed table. Pinned by hand — a ratchet's anchor has to be written
#: somewhere, and this is where every other one in this suite is.
CLOSED_OPERATOR_SET: Final[frozenset[str]] = frozenset({"insert", "replace", "remove", "set"})

#: A field beyond the closed four, permitted to carry `PIPELINE_OPERATOR_MARK` anyway.
#: **Pinned empty.** Adding a name here is a deliberate, visible act in a diff — the
#: honest options otherwise are to not add the fifth operator, or to fold it into one of
#: the existing four.
OPERATORS_WAIVED_BEYOND_THE_CLOSED_SET: Final[frozenset[str]] = frozenset()

#: Every field `Pipeline` declares that is not, and is never meant to become, an operator
#: block: the identifier, the `extends` pointer, `vars`, the base `stages` list, and
#: `slots`. Pinned by hand for the same reason `CLOSED_OPERATOR_SET` is — a ratchet's
#: anchor has to be written somewhere.
#:
#: Repair for a reviewer finding: `_marked_operator_fields` can only ever see a field
#: that carries `PIPELINE_OPERATOR_MARK`, so the two checks above enforce "a fifth
#: *marked* operator cannot land silently" — a strictly weaker statement than `02` §3's
#: "the set stays closed until something real needs a fifth." A field added to `Pipeline`
#: *without* the mark sails through both: `_marked_operator_fields` never counts it, so
#: `test_pipeline_declares_no_operator_beyond_the_closed_set` compares an unchanged
#: `actual` to an unchanged `CLOSED_OPERATOR_SET` and stays green. And it is not merely
#: invisible to this ratchet — it is dead in the kernel itself, the same mark being the
#: one thing `weft_kernel.pipeline._OPERATOR_KEYS` and `weft_kernel.resolution.
#: _apply_operators` (by way of `Pipeline.operator_order`, which filters through
#: `_OPERATOR_KEYS`) both derive from: an unmarked field a document sets validates
#: cleanly and is then never applied, the exact silent-no-op shape `02` §3's closed-set
#: rule exists to rule out. `test_pipeline_declares_no_field_outside_the_closed_
#: classification` below closes the gap by pinning the *whole* field set, not just the
#: marked half.
NON_OPERATOR_FIELDS: Final[frozenset[str]] = frozenset(
    {"name", "extends", "vars", "stages", "slots"}
)


def _marked_operator_fields(model: type[BaseModel]) -> frozenset[str]:
    """Every field `model` itself marks with `PIPELINE_OPERATOR_MARK` — never hand-typed.

    Reads `model.model_fields`, pydantic's own record of what a class declared, filtered
    through `weft_kernel.pipeline.is_pipeline_operator_field` — the same predicate
    `Pipeline`'s own `_OPERATOR_KEYS` uses, imported rather than re-derived here, so this
    file carries no second copy of the `json_schema_extra` narrowing to drift from it. See
    the module docstring for why "never a parallel list this file maintains" is the whole
    point of clause (a)'s ratchet.
    """
    return frozenset(
        name for name, field in model.model_fields.items() if is_pipeline_operator_field(field)
    )


def test_waiver_list_is_empty() -> None:
    assert not OPERATORS_WAIVED_BEYOND_THE_CLOSED_SET, (
        "A field has been waived onto the operator set beyond the closed four. `02` §3: "
        "the set stays closed until something real needs a fifth — if it genuinely does, "
        "this waiver is where that decision is recorded, alongside a dated entry in "
        "docs/README.md's decision log; it is not a place to park an experiment."
    )


def test_every_closed_operator_is_marked_on_the_model() -> None:
    # Floor — if the marking mechanism itself broke (a `Field(...)` edited back to a bare
    # default, say), `_marked_operator_fields` would come back too small, and the closed-set
    # assertion below would trivially pass by comparing an emptied actual set to itself.
    actual = _marked_operator_fields(Pipeline)
    missing = CLOSED_OPERATOR_SET - actual
    assert not missing, (
        f"Pipeline no longer marks {sorted(missing)} with PIPELINE_OPERATOR_MARK, so this "
        f"ratchet cannot see it as an operator field at all. `02` §3's closed table names "
        f"insert/replace/remove/set; restore the mark in weft_kernel.pipeline.Pipeline."
    )


def test_pipeline_declares_no_operator_beyond_the_closed_set() -> None:
    # Arrange
    actual = _marked_operator_fields(Pipeline)

    # Act
    unexpected = actual - CLOSED_OPERATOR_SET - OPERATORS_WAIVED_BEYOND_THE_CLOSED_SET

    # Assert
    assert not unexpected, (
        f"Pipeline marks {sorted(unexpected)} as an operator field, beyond `02` §3's closed "
        f"four ({sorted(CLOSED_OPERATOR_SET)}). A fifth operator is not a silent extension: "
        f"add it to OPERATORS_WAIVED_BEYOND_THE_CLOSED_SET above, with a dated entry in "
        f"docs/README.md's decision log explaining why the closed set no longer holds."
    )


def test_pipeline_declares_no_field_outside_the_closed_classification() -> None:
    """Pin the whole field set, not just the marked half — see `NON_OPERATOR_FIELDS`'s

    own docstring for the gap this closes. Every field `Pipeline` declares must be one
    of: not an operator at all (`NON_OPERATOR_FIELDS`), one of the closed four
    (`CLOSED_OPERATOR_SET`), or an explicitly waived fifth
    (`OPERATORS_WAIVED_BEYOND_THE_CLOSED_SET`) — with no fourth bucket. A new `Pipeline`
    field lands in none of the three until someone classifies it, marked or not, which is
    the point: `test_pipeline_declares_no_operator_beyond_the_closed_set` above can only
    ever see the marked half of a fifth field; this sees all of it.
    """
    # Arrange
    all_fields = frozenset(Pipeline.model_fields)

    # Act
    unclassified = (
        all_fields
        - NON_OPERATOR_FIELDS
        - CLOSED_OPERATOR_SET
        - OPERATORS_WAIVED_BEYOND_THE_CLOSED_SET
    )

    # Assert
    assert not unclassified, (
        f"Pipeline declares {sorted(unclassified)}, which this ratchet has no "
        f"classification for. If it is not an operator block, add it to "
        f"NON_OPERATOR_FIELDS. If it genuinely is a fifth operator, it needs "
        f"PIPELINE_OPERATOR_MARK, a place in OPERATORS_WAIVED_BEYOND_THE_CLOSED_SET, and a "
        f"dated entry in docs/README.md's decision log — never a field that is neither."
    )


def test_an_unmarked_field_outside_every_classification_would_be_caught() -> None:
    """Prove the whole-field-set check above can actually fail, on the exact shape the

    reviewer finding raised: a field with no `PIPELINE_OPERATOR_MARK` at all, which
    `test_a_fifth_marked_field_would_be_caught` below cannot exercise because
    `_marked_operator_fields` would never see it in the first place.
    """

    # Arrange — a throwaway model wearing no mark, the shape a fifth operator takes if
    # the mark is simply forgotten.
    class _UnmarkedFifthFieldStandIn(BaseModel):
        move: tuple[str, ...] = ()

    # Act
    all_fields = frozenset(_UnmarkedFifthFieldStandIn.model_fields)
    unclassified = (
        all_fields
        - NON_OPERATOR_FIELDS
        - CLOSED_OPERATOR_SET
        - OPERATORS_WAIVED_BEYOND_THE_CLOSED_SET
    )

    # Assert
    assert unclassified == {"move"}, (
        "an unmarked field outside every known classification must be visible as "
        "unclassified, or the whole-field-set ratchet is not proven to check anything."
    )


def test_a_fifth_marked_field_would_be_caught() -> None:
    """Prove the check above can actually fail — every ratchet in this suite carries this."""

    # Arrange — a throwaway model wearing the identical mark a real fifth operator would.
    class _FifthOperatorStandIn(BaseModel):
        move: tuple[str, ...] = Field(default=(), json_schema_extra={PIPELINE_OPERATOR_MARK: True})

    # Act
    actual = _marked_operator_fields(_FifthOperatorStandIn)
    unexpected = actual - CLOSED_OPERATOR_SET - OPERATORS_WAIVED_BEYOND_THE_CLOSED_SET

    # Assert
    assert unexpected == {"move"}, (
        "a field carrying PIPELINE_OPERATOR_MARK outside the closed set must be visible as "
        "unexpected, or the ratchet above is not proven to check anything."
    )


# --- (b) every shipped pipeline resolves --------------------------------------------------

#: `weft-store` requires a `dsn` pack setting with no default, or its `register()` never
#: runs at all (`test_ff2_no_privileged_builtins.py` carries the identical placeholder, for
#: the identical reason: the connection is opened lazily on first use, so a placeholder DSN
#: is enough to get `NodeStore:pgvector` registered without a real database).
_PLACEHOLDER_STORE_SETTINGS: Final[dict[str, dict[str, object]]] = {
    "weft-store": {"dsn": "postgresql://ff11-placeholder/placeholder"}
}

_MANUAL_ROOT: Final[Path] = REPO_ROOT / "manual"
_PACKAGE_ROOTS: Final[tuple[Path, ...]] = (REPO_ROOT / "packages", REPO_ROOT / "examples")

_MANUAL_PIPELINE_PREFIX: Final[str] = "pipeline:"
_YAML_FENCE = re.compile(
    r"^```yaml(?:\s+id=(?P<id>\S+))?\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL
)


def _entry_points_table(document: dict[str, object]) -> dict[str, object] | None:
    project = document.get("project")
    if not isinstance(project, dict):
        return None
    entry_points = cast("dict[str, object]", project).get("entry-points")
    if not isinstance(entry_points, dict):
        return None
    packs = cast("dict[str, object]", entry_points).get("weft.packs")
    return cast("dict[str, object]", packs) if isinstance(packs, dict) else None


def _first_party_distributions() -> frozenset[str]:
    """Every `packages/*/pyproject.toml` whose `project.name` declares a `weft.packs` entry
    point — the same computation `test_ff2_no_privileged_builtins.py` makes, restated here
    rather than imported across test files, on the same "one self-contained scenario"
    reasoning `tests/docs/` already gives for its own repeated small helpers.
    """
    distributions: set[str] = set()
    for package_dir in sorted(p for p in (REPO_ROOT / "packages").iterdir() if p.is_dir()):
        pyproject = package_dir / "pyproject.toml"
        if not pyproject.is_file():
            continue
        with pyproject.open("rb") as handle:
            document = tomllib.load(handle)
        if _entry_points_table(document) is None:
            continue
        project = cast("dict[str, object]", document["project"])
        name = project.get("name")
        if isinstance(name, str):
            distributions.add(name)
    return frozenset(distributions)


def _installed_registry() -> Registry:
    """The registry `ci-checks` actually has — every first-party pack, discovered for real.

    Not a registry this file hand-assembles with only the plugins one particular document
    happens to need: `01` item 11(b) says "resolves against the installed registry," and a
    registry built to already contain exactly what a test document names would make this
    check unable to notice a rename. `discover()` with `allow` pinned to every first-party
    distribution is the identical call `test_ff2_no_privileged_builtins.py` makes for the
    same reason there — `weft-canary`'s absence from that pin is `test_ff8_trust_model.py`'s
    property to hold, not this file's to disturb.
    """
    registry = Registry()
    discover(
        registry,
        allow=_first_party_distributions(),
        pack_settings=_PLACEHOLDER_STORE_SETTINGS,
    )
    _register_out_of_tree_examples(registry)
    return registry


def _register_out_of_tree_examples(registry: Registry) -> None:
    """Add every out-of-tree example pack's own registrations to `registry`.

    **Repair, 2026-08-22, from task 5.5.** `_PACKAGE_ROOTS` has always swept `examples/` as
    well as `packages/`, and the sweep found nothing there until `examples/weft-example-graph`
    shipped the first example-pack pipeline — at which point `kg.yaml` was checked against a
    registry that structurally could not contain the plugins it names, because an example pack
    is deliberately **not** a workspace member (fitness function 9(a)) and so declares no
    installed entry point for `discover()` to find. The document was correct and the check
    said it was broken.

    Two wrong repairs were available and both were refused. Dropping `examples/` from the
    sweep would leave an example pack's shipped pipeline unchecked, which is the one kind of
    pipeline most likely to rot, since no first-party test drives it. Widening `allow` would
    do nothing: the packs are not installed, so there is no entry point to allow. What is
    correct is to register them the way they would be if installed — importing each pack's
    module off its own `src/` and running its real `register()`, the identical technique
    `test_ff9_extension_from_outside.module_and_plugin_names` already uses, against a real
    `PackRegistrar` rather than a stand-in so the pipeline resources and contributions arrive
    too. A pack whose `register()` raises here fails this check loudly, which is correct: a
    pack that cannot register cannot ship a resolvable pipeline either.
    """
    for example_dir in _ALL_EXAMPLE_DIRS:
        src_dir = example_dir / "src"
        module_name = next(p.name for p in sorted(src_dir.iterdir()) if p.is_dir())
        sys.path.insert(0, str(src_dir))
        try:
            module = import_module(module_name)
            registrar = PackRegistrar(registry, distribution=_distribution_name(example_dir))
            module.register(registrar, module.Settings())
            registrar.commit()
        finally:
            sys.path.remove(str(src_dir))


def _distribution_name(example_dir: Path) -> str:
    """The `[project] name` an example pack declares — read, never derived from the directory."""
    with (example_dir / "pyproject.toml").open("rb") as handle:
        document = tomllib.load(handle)
    project = cast("dict[str, object]", document["project"])
    return cast(str, project["name"])


_ALL_EXAMPLE_DIRS: Final[tuple[Path, ...]] = tuple(
    sorted(p for p in (REPO_ROOT / "examples").iterdir() if (p / "pyproject.toml").is_file())
)


def _manual_pipeline_blocks(manual_root: Path) -> list[tuple[str, str]]:
    """Every ` ```yaml id=pipeline:<name> ` block across every `*.md` file under `manual_root`.

    `manual_root` is a parameter, not the module-level `_MANUAL_ROOT`, purely so
    `test_manual_pipeline_blocks_are_found_under_their_own_tag` can point this at a planted
    `tmp_path` instead of the real tree — the self-test discipline every finder in this file
    carries. Filters on the `id=pipeline:` prefix rather than sweeping in every fenced
    ```yaml block: `manual/operations-guide.md` already ships one (`path=compose.yaml`,
    docker compose configuration, not a pipeline), and the regex below only ever captures
    an `id=` attribute in the first place — a `path=`-only fence like that one fails to
    match `_YAML_FENCE` at all, so it is invisible here without needing a special case.
    """
    found: list[tuple[str, str]] = []
    for page in sorted(manual_root.glob("*.md")):
        markdown = page.read_text(encoding="utf-8")
        for match in _YAML_FENCE.finditer(markdown):
            block_id = match.group("id")
            if block_id is None or not block_id.startswith(_MANUAL_PIPELINE_PREFIX):
                continue
            found.append((f"{page.name}#{block_id}", match.group("body")))
    return found


def _shipped_pipeline_files(*roots: Path) -> list[tuple[str, str]]:
    """Every `*.yaml` file directly under a `pipelines/` directory one level inside `roots`,
    **or** under a `pipelines/` directory one level inside a `src/*` package directory.

    `roots` is `packages/*` for a first-party pack and `examples/*` for an example pack —
    `01` item 11(b)'s other two sources. `weft-retrieve/pipelines/` stopped being empty at
    task 2.19. **Task 2.8 adds the second location**: `weft_kernel.discovery.
    PipelineResource` reads through `importlib.resources`, which resolves a package's own
    installed directory — `packages/<name>/pipelines/` sits *outside* every pack's wheel
    and was never reachable that way, so a pack contributing a pipeline for real
    installation ships it from inside its own package, `packages/<name>/src/<import
    name>/pipelines/`. Both locations are first-party conventions this gate must find, not
    two competing ones: an old-style demonstration pipeline the CLI reads from a checked-out
    tree can still live at the top level, and a pipeline meant to be routable from an
    installed wheel lives beside the code that ships it. The self-tests just below plant one
    of each and prove the mechanism finds both regardless of what the real tree holds.
    """
    found: list[tuple[str, str]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for pack_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            for path in sorted((pack_dir / "pipelines").glob("*.yaml")):
                found.append((str(path), path.read_text(encoding="utf-8")))
            src_dir = pack_dir / "src"
            if not src_dir.is_dir():
                continue
            for package_dir in sorted(p for p in src_dir.iterdir() if p.is_dir()):
                for path in sorted((package_dir / "pipelines").glob("*.yaml")):
                    found.append((str(path), path.read_text(encoding="utf-8")))
    return found


def _every_shipped_or_quoted_pipeline() -> list[tuple[str, str]]:
    return [
        *_shipped_pipeline_files(*_PACKAGE_ROOTS),
        *_manual_pipeline_blocks(_MANUAL_ROOT),
    ]


def _parse_pipeline(source: str, yaml_text: str) -> Pipeline:
    document = yaml.safe_load(yaml_text)
    if not isinstance(document, dict):
        raise AssertionError(
            f"{source} does not parse to a YAML mapping — a pipeline document is a set of "
            f"top-level keys (name, extends, stages, ...), and this text's top-level YAML "
            f"value is a {type(document).__name__}."
        )
    try:
        return Pipeline.model_validate(document)
    except ValidationError as exc:
        raise AssertionError(f"{source} is not a valid pipeline document: {exc}") from exc


def _stage_use_pairs(pipeline: Pipeline) -> list[tuple[str, str]]:
    """Every `(stage id, plugin name)` this document introduces on its own — `_infer_contract`'s
    input. `replace`'s targets reuse `StageDeclaration` (its own `id` *is* the target, per
    `weft_kernel.pipeline`'s own docstring), so it carries a `use:` exactly like `stages:` and
    an `insert`'s own stage do; `remove` and `set` name no plugin, so neither contributes here.

    **Deliberately excludes `fallback:`.** `weft_kernel.resolution.ResolvedStage`'s own docstring
    and `02` §3's fallback callout both say why: a fallback name may legitimately name a plugin
    that is not installed *yet* — `manual/user-manual.md`'s own `id=pipeline:base` block below
    names `ocr` as `text`'s fallback with no `weft-ocr`-shaped pack anywhere in this tree — and
    this clause exists to catch a plugin that will not run *today*, which a forward-declared
    fallback is not. `test_stage_use_pairs_excludes_fallback_names` locks this in.
    """
    pairs = [(stage.id, stage.use) for stage in pipeline.stages]
    pairs += [(op.stage.id, op.stage.use) for op in pipeline.insert]
    pairs += [(stage.id, stage.use) for stage in pipeline.replace]
    return pairs


def _infer_contract(registry: Registry, name: str) -> type[object] | None:
    """Which registered contract answers for the bare plugin name `name`, if exactly one does.

    A pipeline document names a plugin, never a contract — G1 keeps the kernel from naming
    any capability, so nothing in the document itself says "this is a chunker," and
    `weft_kernel.resolution.resolve`'s own module docstring is explicit that its caller
    supplies `contracts: Mapping[str, type[object]]` because nothing else could. This check
    has no such caller in mind, so it asks the only thing that does know: the registry
    itself, for which contract(s) currently have a plugin registered under `name`. `None`
    for zero matches — the plugin does not exist anywhere, `01` item 11(b)'s own example —
    and for more than one match: genuinely ambiguous, refused rather than guessed through,
    on the same "a silent fallback is worse than a failure" rule the rest of this project
    follows. Neither case is exercised by the real tree today (`text`, `fixed-size`,
    `keybert` and `hash` each register under exactly one contract), so ambiguity is a
    defensive branch, not a scenario this file's own documents trigger.
    """
    matches = [
        contract for contract in registry.contracts() if _registers(registry, contract, name)
    ]
    return matches[0] if len(matches) == 1 else None


def _registers(registry: Registry, contract: type[object], name: str) -> bool:
    try:
        registry.entry(contract, name)
    except UnknownPluginError:
        return False
    return True


def _ancestor_chain(pipeline: Pipeline, parents: Mapping[str, Pipeline]) -> list[Pipeline]:
    """`pipeline` and every ancestor `extends` reaches, root-most first.

    A local, deliberately simpler cousin of `weft_kernel.resolution`'s own private
    `_walk_extends`: that function also merges `vars`, which this helper has no use for,
    and it is not exported for a caller like this file to reuse. Stops on a missing
    parent or a repeated name rather than raising — `resolve()` itself, called below with
    the real `parents` mapping, is the one that must raise `UnknownParentPipelineError` or
    `PipelineCycleError` for those; this walk only needs to know which documents'
    `_stage_use_pairs` belong in `pipeline`'s own contract mapping.
    """
    chain = [pipeline]
    seen = {pipeline.name}
    current = pipeline
    while current.extends is not None:
        parent = parents.get(current.extends)
        if parent is None or parent.name in seen:
            break
        chain.append(parent)
        seen.add(parent.name)
        current = parent
    chain.reverse()
    return chain


def _document_contracts(
    pipeline: Pipeline,
    parents: Mapping[str, Pipeline],
    source_by_name: Mapping[str, str],
    *,
    registry: Registry,
) -> tuple[dict[str, type[object]], list[str]]:
    """`pipeline`'s own `contracts` mapping — never the whole found set pooled into one dict.

    Repair for a reviewer finding: building one `contracts` dict for every document found
    let two documents that happen to share a stage id (`chunk`, `extract`... `02` §3's own
    example names all four) but use different plugins overwrite each other — whichever
    document's pairs were folded in last silently won, and the *other* document then got
    resolved against a contract that was never its own. `resolve()`'s own docstring is
    explicit that `contracts` "must carry an entry for every stage id `pipeline` resolves
    to, including every stage inherited through `extends`" — a per-document requirement,
    so the mapping built to satisfy it has to be too: this walks `pipeline`'s own
    `_ancestor_chain` and folds each ancestor's pairs in root to leaf, so a descendant's
    own `replace` still overrides what an ancestor declared at the same id, exactly the
    order `resolve()` itself applies operators in.
    """
    contracts: dict[str, type[object]] = {}
    unknown: list[str] = []
    for ancestor in _ancestor_chain(pipeline, parents):
        source = source_by_name.get(ancestor.name, ancestor.name)
        for stage_id, use in _stage_use_pairs(ancestor):
            contract = _infer_contract(registry, use)
            if contract is None:
                unknown.append(
                    f"{source}: stage '{stage_id}' names plugin '{use}', which no installed "
                    f"pack registers under any contract"
                )
                continue
            contracts[stage_id] = contract
    return contracts, unknown


def _resolve_every_pipeline(
    found: list[tuple[str, str]], *, registry: Registry
) -> tuple[list[str], list[str]]:
    """Parse and resolve every `(source, yaml_text)` pair. Returns `(unknown_plugins, failures)`.

    Two lists, not one, because they are different *kinds* of evidence. An unknown plugin
    is caught before `resolve()` is ever called — nothing in `contracts` could name a
    contract for it, so calling `resolve()` anyway would surface a bare `KeyError`
    (`resolve()`'s own docstring: a missing `contracts` entry "is a programming error in
    the caller"), which is a worse message than naming the stage and the plugin directly.
    A resolution failure is whatever `resolve()` itself raised once every plugin name at
    least resolved to *some* contract — `WeftError`, per the module docstring's own
    quotation of that class's rule for callers of the library.

    A pipeline name is refused loudly the moment two sources ship the same one, before any
    parsing result is used for anything else — a repair for a second reviewer finding: a
    `parents` dict pooled across every source by name let two packs that each ship a
    pipeline named `base` silently collapse into one, and which source's `base` survived
    depended on iteration order. `02` §3 already refuses a `(contract, name)` collision at
    registration rather than letting one silently win; a duplicate pipeline name is the
    identical shape of problem, refused the identical way, naming both sources.
    """
    documents: dict[str, Pipeline] = {}
    source_by_name: dict[str, str] = {}
    for source, text in found:
        pipeline = _parse_pipeline(source, text)
        if pipeline.name in source_by_name:
            raise AssertionError(
                f"pipeline name '{pipeline.name}' is shipped by both "
                f"{source_by_name[pipeline.name]!r} and {source!r} — fitness function "
                f"11(b) refuses a duplicate pipeline name the same way `02` §3 already "
                f"refuses a duplicate (contract, name) registration: loudly, naming both "
                f"sources, never silently letting whichever loaded last win."
            )
        source_by_name[pipeline.name] = source
        documents[source] = pipeline

    parents_by_name = {pipeline.name: pipeline for pipeline in documents.values()}

    unknown_plugins: list[str] = []
    failures: list[str] = []
    for source, pipeline in documents.items():
        contracts, unknown_here = _document_contracts(
            pipeline, parents_by_name, source_by_name, registry=registry
        )
        unknown_plugins.extend(unknown_here)
        if unknown_here:
            continue
        try:
            resolve(pipeline, registry=registry, contracts=contracts, parents=parents_by_name)
        except WeftError as exc:
            failures.append(f"{source} ('{pipeline.name}'): {type(exc).__name__}: {exc}")

    return unknown_plugins, failures


def test_at_least_one_shipped_or_quoted_pipeline_is_found() -> None:
    # Floor — a generator that finds nothing would look like success (module docstring).
    found = _every_shipped_or_quoted_pipeline()
    assert found, (
        "no pipeline document was found shipped by a pack, an example pack, or quoted as "
        "runnable under manual/ — fitness function 11(b) would pass vacuously."
    )


def test_every_shipped_or_quoted_pipeline_resolves() -> None:
    # Arrange
    found = _every_shipped_or_quoted_pipeline()
    assert found, "the floor test above should already have failed if this is empty"
    registry = _installed_registry()

    # Act
    unknown_plugins, failures = _resolve_every_pipeline(found, registry=registry)

    # Assert
    assert not unknown_plugins, "\n".join(unknown_plugins)
    assert not failures, "\n".join(failures)


def test_stage_use_pairs_excludes_fallback_names() -> None:
    """Repair for a reviewer finding: `fallback:` must stay invisible to this clause, by name.

    A fallback may legitimately name a plugin nothing installs yet (`02` §3's own fallback
    callout, `weft_kernel.resolution.ResolvedStage`'s docstring) — a document naming `ocr` as
    `text`'s fallback before any pack ships one is correct, not rotted. If `_stage_use_pairs`
    ever grows to include `fallback`, this is the test that would have to change on purpose,
    rather than the check silently starting to reject every pipeline that uses the field the
    manual's own worked example ships with.
    """
    # Arrange
    pipeline = _parse_pipeline(
        "planted.yaml",
        "name: has-fallback\n"
        "stages:\n"
        "  - id: extract\n"
        "    use: text\n"
        "    fallback: [nothing-registers-this]\n",
    )

    # Act
    pairs = _stage_use_pairs(pipeline)

    # Assert — only the `use:` pair is collected; the fallback name appears nowhere.
    assert pairs == [("extract", "text")]
    assert not any("nothing-registers-this" in pair for pair in pairs)


def test_manual_pipeline_with_an_unregistered_fallback_still_resolves() -> None:
    """The concrete case the finding named: `manual/user-manual.md`'s own shipped `fallback:
    [ocr]` block, against the real installed registry, where no pack registers `ocr` — this
    must pass, on purpose, because `fallback:` is excluded from what this clause checks."""
    # Arrange
    registry = _installed_registry()
    with_fallback = [
        (
            "planted.yaml",
            "name: has-fallback\n"
            "stages:\n"
            "  - id: extract\n"
            "    use: text\n"
            "    fallback: [ocr]\n"
            "  - id: chunk\n"
            "    use: fixed-size\n",
        )
    ]

    # Act
    unknown_plugins, failures = _resolve_every_pipeline(with_fallback, registry=registry)

    # Assert
    assert not unknown_plugins, "\n".join(unknown_plugins)
    assert not failures, "\n".join(failures)


def test_a_pipeline_naming_an_unknown_plugin_would_be_caught() -> None:
    """Prove the check above can actually fail — `01` item 11(b)'s own example: rename a
    plugin and leave a document naming the old one."""
    # Arrange
    registry = _installed_registry()
    rotted = [("planted.yaml", "name: rotted\nstages: [{id: chunk, use: no-longer-registered}]\n")]

    # Act
    unknown_plugins, failures = _resolve_every_pipeline(rotted, registry=registry)

    # Assert
    assert unknown_plugins, "a plugin name nothing registers must be caught, not silently passed"
    assert "no-longer-registered" in unknown_plugins[0]
    assert not failures, "resolve() must never be called once a plugin name failed to resolve"


def test_a_stale_operator_target_would_be_caught() -> None:
    """The other half of `01` item 11(b)'s example: "an operator target that moved.\""""
    # Arrange
    registry = _installed_registry()
    moved = [
        ("root.yaml", "name: base\nstages: [{id: extract, use: text}]\n"),
        (
            "child.yaml",
            "name: child\nextends: base\ninsert: [{after: chnk, stage: {id: kw, use: keybert}}]\n",
        ),
    ]

    # Act
    unknown_plugins, failures = _resolve_every_pipeline(moved, registry=registry)

    # Assert
    assert not unknown_plugins, "'keybert' and 'text' are both really registered"
    assert failures, "an insert targeting a stage id that does not exist must be caught"
    assert "StaleOperatorTargetError" in failures[0]


def test_two_unrelated_documents_sharing_a_stage_id_each_resolve_against_their_own_plugin() -> None:
    """Repair for a reviewer finding: two standalone documents naming the identical stage

    id (`chunk`, `02` §3's own example) but two different plugins from two different
    contracts must each resolve against its own plugin — never against whichever
    document's `contracts` pair happened to be folded in last. Before the fix, one of
    these two always failed with `UnknownPluginError`, and *which* one failed flipped
    with the order `found` listed them in — the shape the finding called "order-dependent,
    which makes it look like flake rather than a bug."
    """
    # Arrange
    registry = _installed_registry()
    shares_a_stage_id = [
        ("chunker.yaml", "name: chunker\nstages: [{id: chunk, use: fixed-size}]\n"),
        ("extractor.yaml", "name: extractor\nstages: [{id: chunk, use: text}]\n"),
    ]

    # Act
    unknown_plugins, failures = _resolve_every_pipeline(shares_a_stage_id, registry=registry)

    # Assert
    assert not unknown_plugins, "\n".join(unknown_plugins)
    assert not failures, "\n".join(failures)


def test_two_sources_shipping_the_same_pipeline_name_are_refused_loudly() -> None:
    """The other half of the same reviewer finding: `parents` pooled by name across every

    source let two packs each shipping a pipeline named `base` silently collapse into
    one, and which source's `base` survived depended on iteration order. Refused before
    either document is used for anything, naming both sources.
    """
    # Arrange
    registry = _installed_registry()
    duplicated = [
        ("packA/base.yaml", "name: base\nstages: [{id: extract, use: text}]\n"),
        ("packB/base.yaml", "name: base\nstages: [{id: chunk, use: fixed-size}]\n"),
    ]

    # Act / Assert
    with pytest.raises(AssertionError) as excinfo:
        _resolve_every_pipeline(duplicated, registry=registry)

    message = str(excinfo.value)
    assert "packA/base.yaml" in message
    assert "packB/base.yaml" in message


def test_shipped_pipeline_files_are_found_under_a_packs_own_pipelines_directory(
    tmp_path: Path,
) -> None:
    # Arrange — the real tree ships none of these today; this proves the mechanism that
    # would find one if it existed, per the module docstring.
    pipelines_dir = tmp_path / "weft-something" / "pipelines"
    pipelines_dir.mkdir(parents=True)
    planted = pipelines_dir / "base.yaml"
    planted.write_text("name: base\nstages: []\n", encoding="utf-8")

    # Act
    found = _shipped_pipeline_files(tmp_path)

    # Assert
    assert found == [(str(planted), "name: base\nstages: []\n")]


def test_shipped_pipeline_files_are_found_under_a_packs_own_src_layout_pipelines_directory(
    tmp_path: Path,
) -> None:
    # Arrange — task 2.8's addition: a pipeline shipped from inside the package itself,
    # reachable through `importlib.resources` once installed, not only from a checkout.
    pipelines_dir = tmp_path / "weft-something" / "src" / "weft_something" / "pipelines"
    pipelines_dir.mkdir(parents=True)
    planted = pipelines_dir / "route.yaml"
    planted.write_text("name: route\nstages: []\n", encoding="utf-8")

    # Act
    found = _shipped_pipeline_files(tmp_path)

    # Assert
    assert found == [(str(planted), "name: route\nstages: []\n")]


def test_manual_pipeline_blocks_are_found_under_their_own_tag(tmp_path: Path) -> None:
    # Arrange — an `id=pipeline:...` block is found; an ordinary, untagged ```yaml block
    # (compose.yaml's own shape) is not.
    page = tmp_path / "some-page.md"
    page.write_text(
        "```yaml path=compose.yaml\nservices: {}\n```\n\n"
        "```yaml id=pipeline:example\nname: example\nstages: []\n```\n",
        encoding="utf-8",
    )

    # Act
    found = _manual_pipeline_blocks(tmp_path)

    # Assert
    assert found == [("some-page.md#pipeline:example", "name: example\nstages: []\n")]
