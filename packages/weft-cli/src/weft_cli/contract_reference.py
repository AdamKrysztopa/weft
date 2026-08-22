"""Generates `manual/contract-reference.md` — `docs/08-manuals.md` §1, §3 clause (b).

Task **0.12**: "a contract's published reference cannot disagree with its own Protocol,
because there is no second copy of a signature." Every method signature, docstring and
version below is read directly off a real Protocol class at generation time — this module
never hand-types one. `weft_extract.contract`'s own module docstring names the source: "a
small script walks the registry... reads each registered contract's Protocol, docstring
and declared version."

**What "the registry" means here, and why `VectorSearch` is not a second list.**
`weft_kernel.registry.Registry.contracts()` gives every contract with at least one
*registered name* — `Extractor`, `Chunker`, `NodeStore`, `Embedder`. `VectorSearch` is
never registered under its own name — `weft_store.contract`'s own module docstring: "a
capability a store has, not a plugin a pipeline selects" — so a generator that only
walked named registrations would silently omit it, which is exactly the drift this task
exists to make impossible. Instead, for every named contract this module also walks the
owning pack's own public module — the same module `weft_kernel.discovery.discover`
already imports to call `register()` — for every other `@runtime_checkable` `Protocol`
that carries a `.version`: `VectorSearch` sits beside `NodeStore` in `weft_store`'s public
`__all__`, so it is found the same way, with no per-contract special case written here or
anywhere a future capability-only contract would need one. **Which distributions get
printed under a sibling is a separate question from which get printed under its anchor**,
and it is answered by `issubclass` against the registered class — see
`_distributions_satisfying`. `weft-qdrant` registers a `NodeStore` and deliberately does
not satisfy `TextSearch`; a walk that copied the anchor's distribution set across would
publish a capability the code refuses.

**Generation never touches a real database.** `weft-store`'s `register()` only
partial-binds `PgVectorStore(settings)`; nothing calls the factory here, and even if it
were called, `PgVectorStore.__init__` opens no connection — `pgvector_store.py`'s own
docstring: the connection is lazy, opened on first use. `_PLACEHOLDER_DSN` below exists
only to satisfy `weft-store`'s settings model at `register()` time, never to reach a
socket. `weft-otel` (task 5.1d) needs no equivalent placeholder: `OtelSettings.exporter`
defaults to `NONE`, so its `register()` never touches the real, process-global
`TracerProvider` unless a `weft.toml` explicitly turns it on — see that pack's own
`settings.py` for why opt-in, rather than console-by-default, is the settled shape.

**The rendered Markdown is piped through the real `ruff format`, never a second,
hand-rolled line-wrapping rule.** `poe ci-checks`'s own `fmt` step (`ruff format .`, the
first step, before `test` ever runs) reformats fenced Python inside Markdown files, not
only `.py` files — a long method signature gets wrapped onto several lines with a
trailing comma. A generator that rendered one long line would pass its own check right
up until the first `ci-checks` run silently rewrote the checked-in file out from under
it. Running the same `ruff` binary here, at generation time, means there is exactly one
formatting authority for this file, and `ci-checks`' `fmt` step is a no-op on its output.
`ruff` is invoked as `sys.executable -m ruff`, never a bare `"ruff"` argv, so this does
not depend on the interpreter's own `bin/` directory being on `PATH` — a real failure mode
of running the test suite through an explicit interpreter path (`.venv/bin/pytest`)
rather than an activated shell.

**Annotations are rendered through one formatter, never through `repr()` of whatever
typing object a signature happens to carry.** `inspect.signature`'s own `str()` is not
that formatter: a `NewType` unioned with `None` (`Cursor | None`, written exactly that way
in `weft_store.contract`) evaluates at class-body time to `typing.Optional[Cursor]`, a
pydantic-parametrised generic (`Page[Node]`) is a real class whose `__qualname__` already
bakes its argument in, and a PEP 695 type alias (`Outcome[...]`) reprs as its bare short
name regardless of module — three different runtime shapes for what a Weft author always
writes as one style. `_format_annotation` below walks all three (and `collections.abc`
generics, and plain classes) into one consistent rendering: `X | None`, never
`Optional[X]`, and every named type fully qualified by module, so the document reads the
way `docs/02-extension-model.md`'s own examples do and CLAUDE.md's own rule ("native 3.12
type hints") requires.

**A contract the generator cannot describe stops generation, rather than being described
wrongly.** A registered contract with no `.version`, or that is not a `@runtime_checkable`
Protocol with at least one method, does not degrade into an invented placeholder or an
empty `### Methods` section — see `ContractNotDescribableError` below.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
import types
import typing
from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from importlib import import_module

from weft_kernel.discovery import discover
from weft_kernel.errors import WeftError
from weft_kernel.registry import Registry, unwrap_factory
from weft_kernel.runner import Stage

#: Structurally valid, never dialled — see the module docstring's closing paragraph.
_PLACEHOLDER_DSN = "postgresql://contract-reference-generation/placeholder"

#: The one spelling of the regeneration command, referenced from `_HEADER` below and from
#: `tests/docs/test_generated_docs.py`'s failure message, so the two copies a reader
#: actually sees cannot drift from each other or from `scripts/generate_contract_reference.py`'s
#: own docstring, which gives the same command as prose a reader of that file also sees.
REGENERATE_COMMAND = "uv run python scripts/generate_contract_reference.py"

_HEADER = f"""# Contract reference

Generated — `docs/08-manuals.md` §3 clause (b). Every signature, docstring and version
below is read directly off the published `Protocol`; there is no hand-maintained copy for
it to drift from. Regenerate with `{REGENERATE_COMMAND}`, checked by
`tests/docs/test_generated_docs.py`.

## What you write, and what you get for free

Every method below is declared `async def` and returns an `Outcome[T]` —
`Produced[T] | NothingToProduce | Failed`, defined in `weft_kernel.payload.outcome` and
explained in full in `docs/02-extension-model.md` section 1, which this reference links to
rather than restates. A pack author writes exactly the method bodies below; the call is
never made directly — it always passes through the registration seam
(`weft_kernel.seam.wrap`), which attaches four things automatically, not by convention an
author has to remember:

- **A span**, named from the contract and plugin (or the resolved pipeline position, once a
  runner has one), `SpanKind.INTERNAL`, carrying `weft.pack`, `weft.contract` and
  `weft.plugin` attributes.
- **Error attribution.** A `WeftError` a plugin raises has its `pack`, `contract`, `plugin`
  and `stage` fields filled in wherever the plugin left them unset; anything else escaping
  the call is wrapped fresh with those same four fields and `__cause__` preserved, so no
  traceback is hidden. `CancelledError` is never caught here, so it is never at risk of
  being swallowed.
- **Transient stripping.** Every `Node` a plugin produces (bare, or inside a list or tuple)
  has every `__transient__` extension namespace removed before the result leaves the seam.
- **The categorical blocking-call detector**, scoped to exactly the plugin's own `await` —
  fitness function 7(b) fails the run if that call blocks the loop (file IO, a socket,
  `time.sleep`, a synchronous driver).

**`Lifetime` is declared by the plugin, not attached by the seam.** `lifetime:
ClassVar[Lifetime] = Lifetime.RUN` by default, read defensively
(`getattr(instance, "lifetime", Lifetime.RUN)`) so a plugin satisfying its contract only
structurally still gets the default. `Lifetime.RUN` is a fresh instance per pipeline run —
no thread-safety obligation on the author. `Lifetime.PROCESS` is opt-in and accepts that
obligation, in exchange for the kernel reusing the instance across runs, cached by
`(tenant_id, contract, name, config_hash)`.
"""


class ContractNotDescribableError(WeftError):
    """A registered contract this generator cannot describe.

    Raised instead of degrading silently. `docs/02-extension-model.md` §1 requires every
    published contract to declare a `.version` ("Versioned. Every contract carries a
    version, enforced by fitness function 6") and every contract published here is a
    `@runtime_checkable` `typing.Protocol` — `__protocol_attrs__` is exactly what the
    kernel itself reads to compute capability (`weft_store.contract`'s own module
    docstring: "the kernel computes which protocols a store class satisfies"). A contract
    missing either would otherwise render with an invented `unversioned` string or an
    empty `### Methods` section, and the checked-in file would be regenerated to agree —
    the published-reference-disagrees-with-its-contract defect this whole module exists to
    make impossible, reached by a different door.
    """


@dataclass(frozen=True, slots=True)
class PublishedContract:
    """One contract this generator found: the class itself and who registers under it.

    `distributions` is a set, not a single owner — `weft_kernel.registry.Registry`'s own
    `distributions_for` returns every distribution that registered at least one name
    under a contract, and a capability sibling (`VectorSearch`) inherits its anchor
    contract's distributions rather than having its own registration to read one from.

    **The rendered label is "Registered by", and that is a correction rather than a
    wording preference.** It read "Published by" while every contract happened to have
    exactly one registering distribution, which was also the one that published it.
    `weft-pdf` (task 2.27) is the first distribution to register under a contract it does
    not publish, and the old label stated something false about it. Who *publishes* a
    contract is not lost: it is the `**Module:**` line directly above, which names the
    module the Protocol is defined in and therefore the distribution that owns it.
    """

    contract: type[object]
    distributions: frozenset[str]


def discover_for_reference() -> Registry:
    """A fresh `Registry`, populated the same way `weft plugins doctor` populates one.

    Open by default — no `[packs] allow` — because a reference generator describes what
    a contract *is*, never a project's runtime policy. `weft-store` gets just enough
    settings to validate; see the module docstring for why that never opens a connection.
    """
    registry = Registry()
    discover(registry, pack_settings={"weft-store": {"dsn": _PLACEHOLDER_DSN}})
    return registry


def published_contracts(registry: Registry) -> tuple[PublishedContract, ...]:
    """Every contract this generator will render, sorted for a stable, diffable render.

    Named registrations (`registry.contracts()`) plus each one's capability siblings —
    see the module docstring's `VectorSearch` paragraph.

    **A sibling is attributed to a distribution only when that distribution's registered
    class satisfies it.** Repair for a reviewer finding against task 2.6: this used to copy
    the anchor's whole distribution set onto every sibling, so `weft-qdrant` — which
    registers a `NodeStore` and deliberately does *not* satisfy `TextSearch` — was printed
    under `TextSearch` in the shipped manual. An operator reading it would be told they can
    run `hybrid` against Qdrant and then meet `StoreCapabilityMissingError` at run
    assembly, which is a *declared* capability disagreeing with a *derived* one — the
    failure G4's "capability is derived, never declared" exists to prevent, arriving
    through the document instead of through the code.

    Asked of the registered class with `issubclass`, never of an instance, for the reason
    the module docstring gives and `weft_cli.run_services._providers_of` gives again:
    building every installed plugin to generate a document would open connections. A
    factory that is not a class, or a capability Protocol `issubclass` cannot answer, is
    left unattributed rather than assumed — this document says who *is* known to satisfy a
    contract, and silence is the honest answer to a question that cannot be asked.
    """
    named = registry.contracts()
    found: dict[type[object], set[str]] = {
        contract: set(registry.distributions_for(contract)) for contract in named
    }
    for contract in named:
        for sibling in capability_siblings(contract):
            found.setdefault(sibling, set()).update(
                _distributions_satisfying(registry, contract, sibling)
            )

    return tuple(
        PublishedContract(contract=contract, distributions=frozenset(distributions))
        for contract, distributions in sorted(found.items(), key=lambda item: item[0].__qualname__)
    )


def _distributions_satisfying(
    registry: Registry, anchor: type[object], sibling: type[object]
) -> frozenset[str]:
    """Every distribution whose class registered under `anchor` also satisfies `sibling`.

    The same question `weft_cli.run_services._providers_of` asks of a store when it names
    where a missing capability can be had, and asked the same way — off the registered
    class, through `weft_kernel.registry.unwrap_factory`, because a pack that binds its own
    settings registers a `functools.partial` and `partial` does not proxy attribute access.
    """
    satisfying: set[str] = set()
    for name in registry.names_for(anchor):
        entry = registry.entry(anchor, name)
        target = unwrap_factory(entry.factory)
        if not isinstance(target, type):
            continue
        try:
            provides = issubclass(target, sibling)
        except TypeError:
            # A Protocol with a non-method member: `issubclass` refuses to answer it, and
            # inventing an answer is how a generated document starts to differ from the
            # `isinstance` check a run actually makes.
            continue
        if provides:
            satisfying.add(entry.distribution)
    return frozenset(satisfying)


def missing_from_walked_set(
    *,
    registered: frozenset[type[object]],
    walked: AbstractSet[type[object]],
    waived: frozenset[str],
) -> frozenset[type[object]]:
    """Every contract `registered` (a real `Registry`'s own report) that `walked` lacks.

    The runtime floor `docs/08-manuals.md` §3 clause (b) names: a contract with at least
    one registered name must appear in what the generator walked, or be named in
    `waived` — never silently dropped. A pure function, kept separate from
    `published_contracts` so the check has something to call that is not the same code
    path it is checking.
    """
    return frozenset(
        contract
        for contract in registered
        if contract.__qualname__ not in waived and contract not in walked
    )


def render_contract_reference(contracts: tuple[PublishedContract, ...]) -> str:
    """`manual/contract-reference.md`'s content, built from `contracts` alone.

    Passed through `ruff format` before it is returned — see the module docstring's
    closing paragraph for why: without it, this function's own output would not survive
    `poe ci-checks`'s `fmt` step unchanged.
    """
    sections = "\n".join(_render_section(published) for published in contracts)
    return _ruff_format_markdown(f"{_HEADER}\n{sections}")


def _ruff_format_markdown(markdown: str) -> str:
    # `sys.executable -m ruff`, not a bare `"ruff"` argv — see the module docstring's note
    # on why: a bare name depends on the interpreter's own `bin/` being on `PATH`, which
    # `.venv/bin/pytest` (a normal way to run this suite) does not guarantee.
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, no user input
        [sys.executable, "-m", "ruff", "format", "--stdin-filename", "contract-reference.md", "-"],
        input=markdown,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def capability_siblings(contract: type[object]) -> tuple[type[object], ...]:
    """Every other `@runtime_checkable` `Protocol` with a `.version`, exported from
    `contract`'s own pack's public module — see the module docstring.

    Public since task 2.5, when a second caller arrived: `weft_cli.run_services` asks the
    same question of a configured store ("which capabilities does this contract's family
    contain, and which does this instance have?") to name what a store advertises in a
    refusal. Two implementations of *which Protocols are a contract's siblings* could
    disagree, and the reference would then be documenting a family the run assembler does
    not check against.

    **A `Stage[In, Out]` contract is never a candidate sibling — task 2.13's own repair.**
    `weft_retrieve.contract` publishes five pipeline positions that share the identical
    single method name `run`, distinguished from each other only by `In`/`Out` type
    parameters `runtime_checkable`'s own membership check cannot see. Left unfiltered, a
    plugin registered under any one of them — `no-retrieval` under `Retriever`, say —
    satisfies `issubclass` against every other one too, and this document would print
    `weft-retrieve` as "Registered by" for `Fuser`, `Reranker`, `ContextPacker` and
    `QueryScorer`, none of which anything registers. `weft_cli.compile`'s own rule keeps
    this from ever being true in the code: no plugin name is registered under two Phase 2
    contracts (`weft_cli.compile.AmbiguousStageContractError`, exercised by
    `tests/unit/weft_cli/test_compile.py::test_a_plugin_name_two_contracts_register_is_refused_by_name`),
    so a Stage
    contract's membership is always exactly the one name it was registered under —
    never a second one derived by structural check, the way `VectorSearch` genuinely is a
    capability `pgvector` happens to also have. Filtering by `_is_stage_protocol` is what
    keeps that store-shaped derivation from being applied to a family it was never built
    for.
    """
    top_level = contract.__module__.split(".")[0]
    module = import_module(top_level)
    return tuple(
        sorted(
            (
                obj
                for name in getattr(module, "__all__", ())
                if _is_versioned_protocol(obj := getattr(module, name))
                and obj is not contract
                and not _is_stage_protocol(obj)
            ),
            key=lambda cls: cls.__qualname__,
        )
    )


def _is_versioned_protocol(obj: object) -> bool:
    return (
        isinstance(obj, type)
        and issubclass(obj, typing.Protocol)
        and obj is not typing.Protocol
        and hasattr(obj, "version")
    )


def _is_stage_protocol(obj: type[object]) -> bool:
    """True when `obj` declares `Stage[In, Out]` as one of its own bases.

    Read the same way `weft_kernel.runner._stage_signature` reads it — off
    `__orig_bases__`, never off an instance — because this has to answer the question
    before any plugin is registered under `obj` at all. See `capability_siblings`'s own
    docstring for why a `Stage` contract must never be derived as another one's sibling.
    """
    return any(typing.get_origin(base) is Stage for base in getattr(obj, "__orig_bases__", ()))


def _render_section(published: PublishedContract) -> str:
    contract = published.contract
    distributions = ", ".join(f"`{d}`" for d in sorted(published.distributions)) or "—"
    doc = inspect.cleandoc(contract.__doc__ or "*(undocumented)*")
    version = _version_of(contract)
    callables, declared = _partition_protocol_attrs(contract)
    methods = "\n\n".join(_render_method(contract, name) for name in callables)
    attributes = (
        f"### Declared attributes\n\n"
        f"{'\n\n'.join(_render_attribute(contract, name) for name in declared)}\n\n"
        if declared
        else ""
    )

    return (
        f"## `{contract.__qualname__}`\n\n"
        f"**Module:** `{contract.__module__}`  \n"
        f"**Registered by:** {distributions}  \n"
        f"**Version:** `{version}`\n\n"
        f"{doc}\n\n"
        f"{attributes}"
        f"### Methods\n\n"
        f"{methods}\n"
    )


def _version_of(contract: type[object]) -> str:
    """`contract.version`, or a loud, specific failure — see `ContractNotDescribableError`."""
    version = getattr(contract, "version", None)
    if not isinstance(version, str):
        raise ContractNotDescribableError(
            f"{contract.__module__}.{contract.__qualname__} carries no `.version` "
            "attribute. Every published contract must declare one — "
            "docs/02-extension-model.md §1, 'Versioned' — and the reference generator "
            "refuses to invent a placeholder for one that does not."
        )
    return version


def _protocol_attrs_of(contract: type[object]) -> frozenset[str]:
    """`contract.__protocol_attrs__`, or a loud failure — see `ContractNotDescribableError`."""
    attrs = getattr(contract, "__protocol_attrs__", None)
    if not attrs:
        raise ContractNotDescribableError(
            f"{contract.__module__}.{contract.__qualname__} exposes no "
            "`__protocol_attrs__` — it is not a `@runtime_checkable` `typing.Protocol` "
            "declaring at least one method, so the generator has nothing to read a "
            "method list off. Every contract this reference documents must be one."
        )
    return frozenset(attrs)


def _partition_protocol_attrs(contract: type[object]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`contract`'s protocol members, split into what is called and what is declared.

    **Repair, in the task that first exposed it (2.7).** Until `weft_prompts.contract.Prompt`
    had a registered implementation, every contract this generator walked declared methods and
    nothing else, and `_render_method` could read each member off the class with `getattr`.
    `Prompt` declares two *data* members — `input_model` and `output_model`, the class
    attributes a prompt states its own shape with — and an annotation with no assignment is
    not an attribute of the class at all, so generation died with a bare `AttributeError`
    naming `input_model` and nothing else. A published contract that cannot be described is
    supposed to stop generation *loudly*, which is what `ContractNotDescribableError` below is
    for; crashing on a member shape the renderer never considered is the other thing.

    Data members are documented rather than skipped, because a `Prompt` implementation that
    omits `input_model` fails `isinstance` exactly as surely as one that omits `render`, and a
    reference that listed only the method would be telling a pack author half the contract.
    """
    callables: list[str] = []
    declared: list[str] = []
    for name in sorted(_protocol_attrs_of(contract)):
        (callables if callable(getattr(contract, name, None)) else declared).append(name)
    if not callables:
        raise ContractNotDescribableError(
            f"{contract.__module__}.{contract.__qualname__} declares only data members "
            f"({', '.join(declared)}) and no method. A contract with nothing to call is a "
            f"marker, and this reference documents what a pack author implements — see "
            f"`weft_store.contract.MetadataFilter`, which is a marker and is deliberately "
            f"not registered under a name."
        )
    return tuple(callables), tuple(declared)


def _render_attribute(contract: type[object], name: str) -> str:
    """One declared data member, as the annotation a pack author writes on their own class."""
    annotation = inspect.get_annotations(contract).get(name)
    rendered = _format_annotation(annotation) if annotation is not None else "object"
    return f"```python\n{name}: {rendered}\n```"


def _render_method(contract: type[object], name: str) -> str:
    member = getattr(contract, name)
    # An async generator (`async def ... yield ...`, task 2.30's `LLMProvider.stream`) is
    # `async` exactly as much as a coroutine is — `inspect.iscoroutinefunction` alone answers
    # `False` for one, which rendered `stream` as a plain `def` returning an `AsyncIterator`,
    # a signature nothing in this tree could actually call. Both checks, because a Protocol
    # method is always one or the other, never both.
    is_async = inspect.iscoroutinefunction(member) or inspect.isasyncgenfunction(member)
    keyword = "async def" if is_async else "def"
    signature = inspect.signature(member)
    params = _render_parameters(signature.parameters.values())
    return_part = (
        f" -> {_format_annotation(signature.return_annotation)}"
        if signature.return_annotation is not inspect.Signature.empty
        else ""
    )
    block = f"```python\n{keyword} {name}({params}){return_part}: ...\n```"
    doc = inspect.getdoc(member)
    return f"{block}\n\n{doc}" if doc else block


def _render_parameters(parameters: Iterable[inspect.Parameter]) -> str:
    """Every parameter, formatted through `_format_annotation`, with the right separators.

    Mirrors what `inspect.Signature.__str__` itself does for `/` and `*` — a `/` after the
    last positional-only parameter, a bare `*` before the first keyword-only one unless a
    `*args` already opened that section — kept here rather than reused because
    `Signature.__str__` formats annotations through `inspect.formatannotation`, which is
    exactly the inconsistency this module's docstring explains why it does not use.
    """
    rendered: list[str] = []
    seen_positional_only = False
    needs_bare_star = True
    for param in parameters:
        if param.kind is inspect.Parameter.POSITIONAL_ONLY:
            seen_positional_only = True
        elif seen_positional_only:
            rendered.append("/")
            seen_positional_only = False
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            needs_bare_star = False
        elif param.kind is inspect.Parameter.KEYWORD_ONLY and needs_bare_star:
            rendered.append("*")
            needs_bare_star = False
        rendered.append(_format_parameter(param))
    if seen_positional_only:
        rendered.append("/")
    return ", ".join(rendered)


def _format_parameter(param: inspect.Parameter) -> str:
    prefix = {
        inspect.Parameter.VAR_POSITIONAL: "*",
        inspect.Parameter.VAR_KEYWORD: "**",
    }.get(param.kind, "")
    text = f"{prefix}{param.name}"
    if param.annotation is not inspect.Parameter.empty:
        text += f": {_format_annotation(param.annotation)}"
    if param.default is not inspect.Parameter.empty:
        text += f" = {param.default!r}"
    return text


def _format_annotation(annotation: object) -> str:
    """One rendering for every annotation shape a Phase 0 contract carries.

    See the module docstring's paragraph on why `str(inspect.Signature(...))` is not used:
    `typing.Optional[Cursor]` (from a `NewType | None` union), `Page[Node]` (a pydantic
    concrete generic, a real `type` whose `__qualname__` already bakes its argument in) and
    `Outcome[...]` (a PEP 695 type alias, whose `repr()` is its bare short name regardless
    of module) each `repr()` differently for reasons that have nothing to do with what a
    Weft author actually wrote. This renders all of them, and `collections.abc` generics
    and plain classes besides, as one style: `X | None`, never `Optional[X]`, and every
    named type qualified by its own module.
    """
    if annotation is None or annotation is type(None):
        return "None"

    origin = typing.get_origin(annotation)
    if origin is typing.Union or isinstance(annotation, types.UnionType):
        members = typing.get_args(annotation)
        formatted = [_format_annotation(member) for member in members if member is not type(None)]
        if type(None) in members:
            formatted.append("None")
        return " | ".join(formatted)

    # A pydantic-parametrised generic (`Page[Node]`, `Scored[Node]`) is a real `type`
    # whose own `__qualname__` already bakes its argument in as literal text
    # (`"Page[Node]"`) — reading `__pydantic_generic_metadata__` recovers the origin and
    # the argument as separate objects, so they can be qualified independently.
    generic_metadata = getattr(annotation, "__pydantic_generic_metadata__", None)
    if generic_metadata and generic_metadata.get("origin") is not None:
        base = _format_annotation(generic_metadata["origin"])
        args = generic_metadata["args"]
        return f"{base}[{', '.join(_format_annotation(arg) for arg in args)}]" if args else base

    if origin is not None:
        base = _format_annotation(origin)
        args = typing.get_args(annotation)
        return f"{base}[{', '.join(_format_annotation(arg) for arg in args)}]" if args else base

    if isinstance(annotation, typing.TypeAliasType):
        return _qualify(annotation.__module__, annotation.__name__)

    if isinstance(annotation, typing.NewType):
        return _qualify(annotation.__module__, annotation.__name__)

    if isinstance(annotation, type):
        return _qualify(annotation.__module__, annotation.__qualname__)

    # Nothing left that a Phase 0 contract carries — fall back rather than guess at a
    # shape this module has not seen.
    return repr(annotation)


def _qualify(module: str | None, qualname: str) -> str:
    # `TypeAliasType.__module__` is typed `str | None` upstream (it is only ever `None`
    # for an alias built without a module context, which none of this generator's inputs
    # are) — treated the same as an unqualifiable builtin rather than asserted away.
    return qualname if module in (None, "builtins") else f"{module}.{qualname}"
