"""The bridge from a pipeline *document* to the `StageSpec` list the runner consumes.

Task **2.4**. `weft_kernel.resolution.resolve` requires a `contracts: Mapping[str,
type[object]]` covering every stage id a document resolves to — inherited ones and
slot-filled ones included — and a missing entry is a bare `KeyError`, because "a missing
entry is a programming error in the caller, not a pipeline-authoring mistake" (that
function's own docstring). Nothing in this tree produced that mapping outside a test
helper: `weft_cli.ingest` names its four `StageSpec`s as constants and never reads a
document at all. This module is what a query path needs and what `weft ask` will be
rebuilt on.

**The mapping is inferred from the registry, never from a table.** A pipeline document
names a plugin and never a contract — G1 keeps the kernel from naming any capability, so
nothing in the document itself says "this is a retriever". The only thing that knows is
the registry, so that is what is asked: which contract currently has a plugin registered
under this bare `use:` name. A table here would be a closed key space in the one place
fitness function 4 exists to keep open — a third party's contract would need a line in a
file that is not theirs before their pipeline could resolve, which is `01` requirement 1's
zero-edit test failed on the first commit.

**The rule that inference imposes, stated because it is real and load-bearing:** *no
plugin name may be registered under two contracts.* `hybrid` may not be both a retriever
and a fuser. Where it is, `contracts_for` refuses by name rather than guessing — `01`
requirement 5, and the same call `tests/architecture/test_ff11_pipeline_integrity.py`'s
own `_infer_contract` already makes for the same reason.

**What that rule costs, recorded here rather than met first by an operator.** It binds two
strangers who have never heard of each other. One distribution ships `hybrid` as a `Fuser`
while another ships `hybrid` as a `Retriever`, and installing the second makes every
document naming *either* stage unresolvable — including documents that worked before the
install, and the third party's own. **The operator cannot break that tie.**
`weft_kernel.pipeline.StageDeclaration` has no `contract:` key and forbids extras, and the
`[plugins]` pin in `weft.toml` is keyed `"Contract:name"` to arbitrate a *same-key* fight,
so a pin written for a cross-contract clash arbitrates nothing and
`weft_kernel.discovery.discover` raises `InertPluginPinError` for it. The only remedy is a
rename inside a distribution that is not theirs, which is what
`AmbiguousStageContractError`'s own message has to say. Giving the operator a way out means
widening either the pin key space or the document grammar; both are G2's and ledger 2.8's
to settle rather than this module's, so the cost is written down instead of designed around
here. What is *not* in doubt is that the clash arrives loudly — `weft_kernel/resolution.py`
warns that searching every contract for a matching bare name would make it ambiguous, and
ambiguity named beats ambiguity guessed through.

**Why the extends chain is walked here rather than left to `resolve`.** `resolve` needs
the mapping *before* it can be called, and it is the thing that knows how to walk
`extends` — a circularity broken by walking the chain locally for the one question this
module needs answered (which `(id, use)` pairs exist?) and leaving every other question
about inheritance where it belongs. That is why this walk merges no `vars`, applies no
operators and raises nothing about a missing parent: `resolve`, called next by the
caller, is what must raise `UnknownParentPipelineError` and `PipelineCycleError`.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from weft_kernel.errors import UnresolvedNameError
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry, UnknownPluginError
from weft_kernel.resolution import ResolvedPipeline
from weft_kernel.runner import PipelineResolutionError, StageSpec


class AmbiguousStageContractError(PipelineResolutionError, UnresolvedNameError):
    """Two or more contracts have a plugin registered under one `use:` name.

    Not a defect in either pack: two distributions may legitimately choose the same short
    word, and neither knows about the other. What is refused is *guessing* which one a
    document meant — the message names the stage, the name and every contract that
    answers to it, because a silently chosen contract would resolve, run, and produce a
    pipeline whose middle did something nobody asked for.

    Fitness function 12's family: `valid_options` is every contract name `use` answers
    to — the candidates a caller must disambiguate between, not a name that resolved to
    nothing.
    """

    def __init__(
        self,
        message: str,
        *,
        valid_options: tuple[str, ...],
        pipeline: str | None = None,
        stages: tuple[str, ...] = (),
        distributions: tuple[str, ...] = (),
        remedy: str = "",
    ) -> None:
        PipelineResolutionError.__init__(
            self,
            message,
            pipeline=pipeline,
            stages=stages,
            distributions=distributions,
            remedy=remedy,
        )
        self.valid_options = valid_options


class UnknownStagePluginError(PipelineResolutionError, UnresolvedNameError):
    """A document's `use:` names a plugin no installed distribution registered.

    Distinct from `weft_kernel.registry.UnknownPluginError`, which answers "not under
    *this* contract" and can therefore name the valid options for it. Here there is no
    contract yet — that is the thing being inferred — so the message names every plugin
    the registry holds, whatever contract it sits under, which is the only list that can
    contain the operator's typo.

    **Not raised for a `fallback:` name.** `weft_kernel.resolution` deliberately carries
    those through unchecked so a document may name a plugin nobody has shipped yet, and
    `Runner.resolve` is where making such a document *runnable* is refused — see
    `UnknownFallbackError`. This module infers contracts for `stages:` positions only, so
    the two promises stay separate.

    Fitness function 12's family: `valid_options` is every plugin name the registry
    holds, under any contract.
    """

    def __init__(
        self,
        message: str,
        *,
        valid_options: tuple[str, ...],
        pipeline: str | None = None,
        stages: tuple[str, ...] = (),
        remedy: str = "",
    ) -> None:
        PipelineResolutionError.__init__(
            self, message, pipeline=pipeline, stages=stages, remedy=remedy
        )
        self.valid_options = valid_options


def contracts_for(
    pipeline: Pipeline, *, registry: Registry, parents: Mapping[str, Pipeline]
) -> dict[str, type[object]]:
    """The `contracts` mapping `weft_kernel.resolution.resolve` demands for `pipeline`.

    Covers every stage id the document resolves to: its own `stages:`, everything it
    inherits through `extends`, and every id its `insert:` and `replace:` operators
    introduce. `remove:` and `set:` name no plugin and contribute nothing.

    Raises `UnknownStagePluginError` for a name nothing registered and
    `AmbiguousStageContractError` for a name two contracts answer to — both by name, both
    naming the options, and neither guessed through.
    """
    contracts: dict[str, type[object]] = {}
    for document in _ancestors_first(pipeline, parents):
        for stage_id, use in _stage_use_pairs(document):
            contracts[stage_id] = _contract_for(registry, use, pipeline=pipeline, stage=stage_id)
    return contracts


def to_specs(resolved: ResolvedPipeline, *, registry: Registry) -> tuple[StageSpec, ...]:
    """Turn a resolved document into the `StageSpec` list `Runner.resolve` composes and runs.

    The contract comes from the same inference `contracts_for` performed, rather than from
    `ResolvedStage.contract` — which is a *name*, a string, and mapping a string back to a
    type would mean matching on `__name__` and quietly picking one of two contracts that
    happen to share it. Asking the registry the same question twice is cheap and cannot
    disagree with itself.

    **An empty `with:` block becomes `None`, not an empty mapping.** `_validate_stage_config`
    answers a plugin that declares no `config_model` with an empty read-only mapping, while
    the runner calls `entry.factory(spec.config)` with one positional argument that a plugin
    is documented to accept as `config: XConfig | None = None`. Handing it a mapping where
    it expects `None` would give every no-configuration plugin in the tree an argument it
    was never written to read — so the two shapes are told apart here, once, by the only
    thing that distinguishes them: a validated block is a `BaseModel`, an absent one is not.
    """
    return tuple(
        StageSpec(
            id=stage.id,
            contract=_contract_for(registry, stage.use, pipeline=None, stage=stage.id),
            name=stage.use,
            config=stage.config if isinstance(stage.config, BaseModel) else None,
            fallback=stage.fallback,
        )
        for stage in resolved.stages
    )


def _contract_for(
    registry: Registry, use: str, *, pipeline: Pipeline | None, stage: str
) -> type[object]:
    """Which registered contract answers for the bare plugin name `use` — exactly one, or refuse."""
    matches = sorted(
        (contract for contract in registry.contracts() if _registers(registry, contract, use)),
        key=lambda contract: contract.__name__,
    )
    name = pipeline.name if pipeline is not None else None
    if not matches:
        installed = tuple(
            sorted(
                {
                    plugin
                    for contract in registry.contracts()
                    for plugin in registry.names_for(contract)
                }
            )
        )
        raise UnknownStagePluginError(
            f"stage '{stage}' names plugin '{use}', which no installed distribution "
            f"registered under any contract. Installed plugin names: "
            f"{', '.join(installed) or '(none)'}.",
            valid_options=installed,
            pipeline=name,
            stages=(stage,),
            remedy=(
                f"install the distribution that ships '{use}', or correct the 'use:' field "
                f"on stage '{stage}' to one of: {', '.join(installed) or '(none installed)'}."
            ),
        )
    if len(matches) > 1:
        contract_names = tuple(contract.__name__ for contract in matches)
        offered = ", ".join(contract_names)
        raise AmbiguousStageContractError(
            f"stage '{stage}' names plugin '{use}', which is registered under more than one "
            f"contract: {offered}. A pipeline document names a plugin, never a contract, so "
            f"there is nothing here that says which was meant.",
            valid_options=contract_names,
            pipeline=name,
            stages=(stage,),
            distributions=tuple(
                sorted({registry.entry(contract, use).distribution for contract in matches})
            ),
            remedy=(
                f"have one of the distributions registering '{use}' rename it — a plugin name "
                f"must answer to exactly one of: {offered}."
            ),
        )
    return matches[0]


def _registers(registry: Registry, contract: type[object], name: str) -> bool:
    try:
        registry.entry(contract, name)
    except UnknownPluginError:
        return False
    return True


def _ancestors_first(pipeline: Pipeline, parents: Mapping[str, Pipeline]) -> list[Pipeline]:
    """`pipeline` and every ancestor `extends` reaches, root-most first.

    Stops on a missing parent or a repeated name rather than raising — see the module
    docstring: `resolve` is the one that must name a missing parent or a cycle, and two
    modules raising for the same condition would be two messages to keep in step.
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


def _stage_use_pairs(pipeline: Pipeline) -> list[tuple[str, str]]:
    """Every `(stage id, plugin name)` this one document introduces on its own.

    `replace:` reuses `StageDeclaration` — its own `id` *is* the target — so it carries a
    `use:` exactly as `stages:` and an `insert:`'s own stage do. `remove:` and `set:` name
    no plugin. `fallback:` is deliberately excluded, per `UnknownStagePluginError`.
    """
    pairs = [(stage.id, stage.use) for stage in pipeline.stages]
    pairs += [(op.stage.id, op.stage.use) for op in pipeline.insert]
    pairs += [(stage.id, stage.use) for stage in pipeline.replace]
    return pairs
