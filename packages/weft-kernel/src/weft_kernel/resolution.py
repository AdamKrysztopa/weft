"""`resolve()` — a pipeline document reduced to a frozen, fully-explicit form. Task 1.3.

Specified in `docs/02-extension-model.md` §3 → *Derivation* and *When resolution
fails*. `weft_kernel.pipeline.Pipeline` is what an author wrote: `extends` unfollowed,
`vars` unsubstituted, no plugin looked up. `weft_kernel.runner.RunnablePipeline` is
what a `Runner` executes: constructed plugin instances, cached per `Lifetime`, scoped
to a tenant. Neither is what `02` §3 means by "the resolved form" — a **data** value in
between the two, produced here: "Resolution produces a frozen, fully-explicit
pipeline: every stage, plugin, version and configuration value named, with no
inheritance left to interpret. That resolved form is what runs, what gets logged, and
what evaluation compares." `ResolvedPipeline` is a `BaseModel`, not a `dataclass`
wrapping live objects the way `RunnablePipeline` does — printable, diffable, loggable,
comparable by `==` across two separate calls to `resolve()`, which is exactly what a
constructed plugin instance can never promise. Building a `RunnablePipeline` from a
`ResolvedPipeline` — instantiating every `StageSpec` this module names — is a later
step's job, not this one's; nothing here calls a factory.

**Everything a resolved pipeline can be wrong about is wrong before it runs.** `02` §3
lists five checks; `weft_kernel.registry.Registry.entry` already does the first
(`UnknownPluginError`, reused unchanged, never re-implemented) and the other four are
this module's own: `requires` produced by an earlier stage, consecutive stages compose
by `Stage[In, Out]`, `intact` not already destroyed (task 1.2's ordering constraints),
and every `${var:NAME}` reference defined somewhere in the `extends` chain. Two more
belong to `extends` itself and have no equivalent in `weft_kernel.runner.Runner.resolve`,
because `Runner` was never handed a document with a parent to follow: an `extends`
target absent from the caller's `parents` lookup, and a cycle, named as the whole
chain rather than the one link that happened to close it. **Task 1.5 adds one more,
against the last thing a stage carries once vars are substituted:** a stage's `with:`
block is validated against its plugin's own declared `config_model`, and the *validated
object* — never the raw mapping — is what a `ResolvedStage.config` actually holds.

**Why this check exists — `02` §1's contract rule, and the reference's most-repeated
mistake.** `02` §1: "a contract's registration API carries a typed configuration model,
or the extension point is decorative." `02` §3's own extended note names the evidence
that rule is written against: the identical failure occurred *independently* in two
reference subsystems that never talked to each other — `evaluation/config.py`'s `params`
field was commented out, so no metric could ever be parameterised, and
`evaluation/datasets/settings_loader.py` carried a `TODO: Enhance registry to support
enhancer-specific configuration` because `create_enhancer(name, llm, language, **kwargs)`
had nowhere typed to put one. Both defects are the same shape: a `with:`-style block
with nowhere checked to land, so it was either silently dropped or never offered at
all. This module is where that shape stops being possible for a pipeline document —
`InvalidStageConfigError` and `StageNotConfigurableError` below are its two ways of
refusing rather than repeating it.

**`requires`/`provides`/`intact`/`destroys`/`config_model` are read off the registered
factory *class*, never an instance this module builds.** `weft_kernel.registry`'s own
`_require_destroys_if_governed` already establishes the precedent — "reads the class,
not an instance... no config exists yet to build an instance from at registration
time" — and the same is true here for the identical reason: a resolved *form* is data,
so nothing here ever calls a factory. `config_model` follows the same defensive-`getattr`
grain those four already do, on purpose: G1 keeps the kernel from naming any capability,
so there is no `Chunker`-shaped or `Extractor`-shaped hook to hang a config check on —
the only thing every contract's plugin has in common is that it is *a class a factory
constructs*, and that is exactly what `requires`/`provides`/`intact`/`destroys` already
read off generically, with no ClassVar declared on `Stage` itself for `typing.Protocol`
reasons the runner's own module docstring explains. `config_model` costs a plugin one
optional class attribute — `getattr(declared, "config_model", None)` supplies `None`
for a plugin that never declares one, exactly as `Lifetime.RUN` / `()` / `()` are
supplied for the others — never a required base class or a name the kernel has to know
in advance. Every stand-in plugin class this module's own tests declare states these as
class attributes, exactly as `weft_chunk.fixed_size.FixedSizeChunker` does for real
(`destroys = (WordBoundaries,)` at its own class body). Every read goes through
`weft_kernel.registry.unwrap_factory` first, for the same reason
`_require_destroys_if_governed` does: `entry.factory` is sometimes a
`functools.partial` binding pack settings — `weft_store`'s own registration —
and reading `getattr` straight off a `partial` silently sees `()` (or `None`) regardless
of what the wrapped class actually declares. Skipping the unwrap here would be worse
than in `registry`, because there is no refusal to catch it: a governed contract's
`intact` or `destroys` would just vanish, and `weft_kernel.runner.Runner.resolve` —
which reads a *constructed instance*, immune to this — would disagree about the same
pipeline with nothing loud to say why.

**A stage's contract is supplied by the caller, not guessed from a bare `use:` name.**
A `StageDeclaration` carries no `contract:` key — G1 keeps the kernel from naming any
capability, so nothing here could recognise "Extractor" or "Chunker" if it saw one, and
searching every registered contract for a name that happens to match would make two
unrelated packs registering the same bare name under two different contracts
(`Registry`'s own docstring: "two names collide only if they share both the contract
*and* the string name... unrelated registrations") silently ambiguous rather than
loudly refused, which is precisely the guessing `weft_kernel.pipeline`'s own docstring
says a pre-resolution converter would have had to do. `resolve()` instead takes
`contracts: Mapping[str, type[object]]`, keyed by **stage id** — the same externally
supplied dependency shape `parents` already is: `02` §3 says "the kernel opens no
file... resolution takes its parent lookup as an argument", and a contract lookup is
the same kind of thing, supplied the same way. Once a stage's contract is known,
`registry.entry(contract, stage.use)` is the real, checked lookup `02` §3 means by "the
lookup resolution does against a registry" — a check, not a guess, run against
information resolution was actually given.

**Only the pipeline with no `extends` may carry stages — every other pipeline in the
chain carries only operators.**
`weft_kernel.pipeline.Pipeline._extends_and_stages_are_mutually_exclusive_with_operators`
refuses `stages:` alongside `extends`, and refuses an operator with no `extends`, both in
the authored form, before a registry or a parent lookup exists to resolve against — so
every stage this module ever *starts* from belongs to the *root* of an `extends` chain.
Task 1.4 is what a non-root pipeline in that chain is *for*: "resolve the parent
completely, then apply this pipeline's own operators to that result" (`02` §3 →
*Derivation*), root to leaf, one ancestor at a time — `_apply_ancestry_operators` below.
A stage's `provenance` is therefore no longer always the root: it is the root's name for
every stage the root wrote, and the name of whichever descendant's `insert` or `replace`
most recently put a *different* stage — or a different plugin at an existing id — there,
which is what `02` §3 means by "every stage in the resolved form records which pipeline
or pack put it there, so depth stays forensically readable." `set` never moves
provenance: it changes configuration, never which plugin answers for the id, so the
question `provenance` answers — who is responsible for *this stage existing, running
this plugin* — has the same answer before and after a `set`. Depth still matters for
`vars` exactly as it did before 1.4: each ancestor's `vars:` block is merged root-to-leaf,
so a leaf's override reaches a var referenced in a `with:` block the root itself wrote —
`02` §3: "a child's override re-resolves every inherited stage that references it."

**Operators apply against the *running* stage list, never against the original root.**
`02` §3: "Operators apply in written order, each validated against the running result."
That is what makes `remove` followed by `insert` on one id a move rather than a
collision — task 1.4 settles the question `docs/build-ledger.md` left open after 1.1:
"the order in which those keys appear in the document is the order they apply."
`weft_kernel.pipeline.Pipeline.operator_order` is read off the document (or the call)
that built the pipeline, never assumed from field order, and `_apply_operators` below
walks it literally, one block at a time. **Every operator is strict** — a target id
absent from the running result is `StaleOperatorTargetError`, naming the id, the
pipeline that wrote the operator, the parent it extends, and the ids that do exist;
`remove` gets no exemption, because a `remove` matching nothing is evidence the parent
moved under the child, not something to shrug past. `insert` additionally refuses a new
id that already exists — `OperatorIdCollisionError` — because inserting it would
silently shadow a stage the parent chain already has one of.

**`${var:NAME}` mirrors `weft_kernel.discovery.interpolate_env`'s `${env:VAR}` on
purpose**, not by coincidence: `02` §3 gives `vars:` scalar values substituted into
`with:`, the same shape `${env:VAR}` already substitutes environment values into pack
settings, and neither document specifies a template *language* — `interpolate_env`'s
own docstring is explicit that partial substitution inside a longer string "is a
template engine this project does not have and does not need". A value must be
*exactly* `${var:NAME}` to substitute; a string that merely contains the token passes
through untouched, and an undefined reference is `UndefinedVarError`, naming the var,
the pipeline and the stage whose `with:` block held the reference, exactly as `02` §3
requires: "An undefined var is a resolution error naming the var and the pipeline." The
stage id is not `02` §3's own wording, but it is task 1.13's own rule for the family
this class belongs to: `stages` is populated "wherever a failure genuinely has none to
name" is the only excuse for leaving it empty, and the stage holding the bad reference
is right there in scope at the call site below — there is nothing genuine about leaving
it out.

**Config validation runs last, per stage, after vars have already been substituted** —
task 1.5. A stage's `with:` block is a document fragment until this point: raw values,
possibly still carrying `${var:NAME}` tokens. `_substitute_vars` resolves those first,
so a bad var reference is still `UndefinedVarError` rather than a confusing validation
failure against a token pydantic was never going to accept as, say, an `int`. Only once
the block is fully literal does `_validate_stage_config` check it against
`declared.config_model` (read the same defensive way as `requires`/`intact`/`destroys`
above): `InvalidStageConfigError` if a model is declared and the block fails it —
naming the stage, the plugin, every field pydantic rejected and what the model accepts
— or `StageNotConfigurableError` if no model is declared and the block is non-empty
anyway. A plugin that declares no `config_model` at all still resolves, exactly as
before this task, provided its `with:` block is empty; the two are the same rule seen
from either side; see `02` §1: "a contract's registration API carries a typed
configuration model, or the extension point is decorative." The **object**
`config_model.model_validate(...)` returns — never the raw mapping it validated — is
what `ResolvedStage.config` holds from here on, which is the whole point: nothing that
reads a `ResolvedStage` downstream ever sees an untyped `dict`.

**`unapplied_operators` stays empty even now; `unplaced_contributions` still has nothing
to describe.** Task 1.4 gives every operator no exemption from failing loudly — a stale
target is `StaleOperatorTargetError`, not a recorded no-op — so there is no such thing as
an *unapplied* `insert`/`replace`/`remove`/`set` yet. `02` §3 → *Slots* is what first
gives an operator a legitimate reason to land nowhere: "Installation-dependent targets
are recorded, never fatal" for a contribution targeting a slot the running pack does not
provide — a distinction task 1.11 draws, not this one. `tuple[str, ...]` holds a short
description per entry until that task gives the concept its own shape; what matters for
this task is that the *field* already exists, so widening its element type in 1.11 is a
smaller, more contained change than discovering the field absent altogether after
evaluation has started comparing resolved forms by equality.

**Task 1.13 — the audit `02` §3 → *When resolution fails* asks for.** Two things changed
here, neither a reversal. First, `UnmetRequiresError`, `StageCompositionError` and
`IntactViolationError` are no longer declared in this module — they moved to
`weft_kernel.runner`, re-exported here (`from weft_kernel.runner import X as X`, the
explicit form a type checker accepts as a real export rather than an unused import) so
every existing `resolution.UnmetRequiresError` reference keeps working unchanged. The
reason is the defect the sweep found: `weft_kernel.runner.Runner.resolve` performed the
identical three checks against a `StageSpec` list and raised the bare
`PipelineResolutionError` family base directly for all three, told apart only by reading
the message — exactly the fat-class shape `02` §3 rules out, one module over from where
this module had already solved it correctly for a pipeline *document*. Reusing these three
names is not a new decision; it is applying the one this module already made to the other
mechanism that needed it, which is also why `manual/troubleshooting.md`'s own entry for
each already said "this is the same check `weft_kernel.runner.PipelineResolutionError`
performs for an explicit `StageSpec` list" before this task made it the same *class*.

Second, every subclass below now passes real, structured values for the four fields `02`
§3 requires on the family base — `pipeline`, `stages`, `distributions`, `remedy` — not only
a formatted sentence containing the same facts. `pipeline` and `distributions` are `None`
or `()` wherever this module genuinely has none to name (a `PipelineCycleError` has no
distribution in conflict; `_stage_signature`'s "contract does not declare `Stage[In,
Out]`" case has no pipeline in scope at all), the identical honest-absence reasoning `02`
§3 already gives `UnknownParentPipelineError`'s "no stage ids and no distribution to
name" — never a fabricated placeholder a caller could mistake for real data.
"""

from __future__ import annotations

import re
import typing
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, cast

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, ValidationError, field_validator

from weft_kernel.errors import UnresolvedNameError
from weft_kernel.payload import Applies, ExtModel
from weft_kernel.pipeline import (
    Pipeline,
    Scalar,
    SetOperator,
    SlotDeclaration,
    StageDeclaration,
    VarBlock,
)
from weft_kernel.registry import Registry, unwrap_factory
from weft_kernel.runner import IntactViolationError as IntactViolationError
from weft_kernel.runner import (
    PipelineResolutionError,
    Stage,
    UnresolvedNameInPipelineResolutionError,
)
from weft_kernel.runner import StageCompositionError as StageCompositionError
from weft_kernel.runner import UnmetRequiresError as UnmetRequiresError

_VAR_TOKEN: Final[re.Pattern[str]] = re.compile(r"^\$\{var:([^}]+)\}$")
"""On the same footing as `weft_kernel.discovery._ENV_TOKEN` — see the module docstring."""

_QUALIFIER: Final[str] = ":"
"""A deliberate duplicate of `weft_kernel.pipeline._QUALIFIER`, private to that module —
see `weft_kernel.pipeline._read_only`'s own docstring for why this module duplicates
rather than reaches across a private name: `_stage_signature` below does the identical
thing for the identical reason. This is what `_qualify` below stitches a contribution's
`distribution` and its own local `stage.id` together with, and what the deferred-`set`
split in `_apply_sets` reads to tell a plain stage id from a pack's contributed one.
"""

_NO_PARENTS: Final[Mapping[str, Pipeline]] = MappingProxyType({})
"""The default `parents` lookup for a pipeline that does not `extends` anything.

A `MappingProxyType`, not a plain `{}`, on the same reasoning
`weft_kernel.pipeline._NO_CONFIG` already documents: it is shared rather than
rebuilt per call, safe only because nothing can write through it, so a mutable-default
hazard never gets the chance to exist.
"""


class Contribution(BaseModel):
    """One pack's stage, offered into a named slot rather than claimed by a stage id.

    `02` §3 → *Slots*: "A contribution targets a named slot, never a stage id." `stage`
    reuses `StageDeclaration` for exactly that reason — the plugin name and its own
    `with:` block are the same shape a pipeline's own stages already have — but
    `stage.id` here is the pack's own **local**, unqualified name (`entities`, not
    `weft-graph:entities`): `StageDeclaration.id`'s own reserved-qualifier check already
    refuses a colon there, and there is no reason to give the same thing a second name.
    `_qualify` below is what prefixes it with `distribution` once — and only once — a
    contribution actually gets placed: an id only needs to be globally unique from the
    moment it exists in a resolved stage list, and an unplaced contribution never reaches
    one.

    Never authored: a pipeline document has no syntax that builds one of these, and
    resolution never builds one either. A caller supplies a tuple of these to
    `resolve()`, on the identical footing `contracts` and `parents` already are — an
    externally supplied dependency the kernel neither opens nor discovers, per `02` §3's
    own G1 reasoning for `parents`. In practice that caller is whatever assembled the
    `Registry` from every installed pack's own registration, since a contribution is
    only ever real once a pack that offers one is actually on the machine.

    **Task 5.3a (`S8`) is where that caller stopped being hypothetical.** A pack offers one
    through its own `register()`, via `weft_kernel.discovery.PackRegistrar.add_contribution`
    — `distribution` filled in there, never stated by the pack — and `weft_cli.
    registry_bootstrap.build_dependencies` is the "whatever assembled the `Registry`" this
    docstring already named: it concatenates every `weft_kernel.discovery.PackReport.
    contributions` tuple `discover()` returned into the one `contributions=` argument every
    `weft_kernel.resolution.resolve` call site in `weft-cli` now passes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str = Field(min_length=1)
    distribution: str = Field(min_length=1)
    stage: StageDeclaration


def _qualify(contribution: Contribution) -> str:
    """The id a placed contribution wears in the resolved stage list — `02` §3 → *Slots*:
    "Contributed stage ids are qualified by distribution (`weft-graph:entities`)."
    """
    return f"{contribution.distribution}{_QUALIFIER}{contribution.stage.id}"


def _qualified_stage(
    *, id: str, use: str, config: Mapping[str, object], fallback: tuple[str, ...]
) -> StageDeclaration:
    """Build a `StageDeclaration` bypassing validation — for an id this module computed itself.

    `model_construct`, not the ordinary constructor, deliberately: `StageDeclaration.id`'s
    own field validator (`_id_is_not_a_pack_s_to_give`) exists to refuse a `:`-qualified
    id everywhere an *author* could type one — exactly the spelling `id` carries every
    time this function is called, since both of this module's two call sites
    (`_placed_stage`, placing a fresh contribution; `_apply_deferred_sets`, merging a
    `set` into one already placed) only ever pass a *pack's* id, never an author's.
    Re-validating it would refuse the one shape `02` §3 reserves the qualifier to
    produce. `config` is trusted to already be the read-only view ordinary construction
    gives it — a fresh dict merge (`{**current.config, **op.config}`) or a contribution's
    own already-validated `stage.config` — so nothing here re-wraps it.
    """
    return StageDeclaration.model_construct(id=id, use=use, config=config, fallback=fallback)


def _placed_stage(qualified_id: str, stage: StageDeclaration) -> StageDeclaration:
    """A contribution's own `StageDeclaration`, wearing its placed, qualified id."""
    return _qualified_stage(
        id=qualified_id, use=stage.use, config=stage.config, fallback=stage.fallback
    )


_NO_CONTRIBUTIONS: Final[tuple[Contribution, ...]] = ()
"""The default `contributions` a `resolve()` call is given — a pipeline with slots that
no installed pack contributes into resolves exactly as it would with none declared at
all, which is what task 1.11 means by "installed and doing nothing must be visible
without breaking every pipeline lacking that slot" in the other direction: a pipeline
with a slot and *no* contributions must not need a caller to supply anything special
either.
"""


class UnknownParentPipelineError(
    UnresolvedNameInPipelineResolutionError, PipelineResolutionError, UnresolvedNameError
):
    """`extends` names a pipeline the caller's `parents` mapping does not contain.

    `02` §3 → *When resolution fails*: every failure names "the pipeline, the stage
    ids, the distributions in conflict and the remedy" where those apply — a missing
    parent has no stage ids and no distribution to name, so the message states the
    child, the parent name it wrote, and the remedy: supply that pipeline in `parents`,
    or fix the typo. It also names every pipeline `parents` *does* contain, the same
    "what was wanted, why it is unavailable, and what the valid options are" shape
    `weft_kernel.errors`' own module docstring requires of every kernel-raised error —
    without it a one-character typo is unfixable from the message alone, when the name
    that would have worked was in the caller's own argument the whole time.
    `weft_kernel.runner`'s own `PipelineResolutionError` has no equivalent, because
    `Runner.resolve` is never handed a document with a parent to follow at all.

    Fitness function 12's family: `valid_options` is every pipeline name `parents`
    *does* contain.

    No `__init__` of its own — task 2.36's repair collapsed this class's own 19-line
    forwarding body into `weft_kernel.runner.UnresolvedNameInPipelineResolutionError`, which
    it now inherits unmodified; see that class's own docstring for why the shared body
    lives in `runner` rather than here, and why `valid_options` staying required and
    keyword-only, with no default, is unaffected by the collapse.
    """


class PipelineCycleError(PipelineResolutionError):
    """`extends` walks back to a pipeline already in the chain being resolved.

    Named as the **whole chain**, not the one link that happened to close it — `02` §3:
    "A cycle is a resolution error naming the whole chain." Reporting only the
    repeated name would tell an author *that* something loops without telling them
    *which* edit to undo; the full chain, in the order it was walked, does.
    """


class InvalidStageConfigError(PipelineResolutionError):
    """A stage's `with:` block does not validate against its plugin's own `config_model`.

    Task 1.5, `02` §1: "a contract's registration API carries a typed configuration
    model, or the extension point is decorative." Raised once `${var:NAME}` substitution
    has already happened (see the module docstring, *"Config validation runs last..."*),
    so this is always a genuine mismatch between the literal `with:` block and what the
    plugin's model accepts — never a var reference read as a stray string. Names the
    stage id, the plugin (`contract:name`), every field pydantic's own `ValidationError`
    rejected with its reason, and what the model accepts, so a typo'd field reads as a
    typo and a wrong type reads as a wrong type, from the message alone.
    """


class StageNotConfigurableError(PipelineResolutionError):
    """A stage sets a non-empty `with:` block for a plugin that publishes no `config_model`.

    Task 1.5, the other half of `02` §1's rule: an extension point with no typed model
    is decorative, and a `with:` block written against a decorative extension point
    cannot be silently accepted and dropped — that is exactly the reference's own defect
    (see the module docstring's reference-study paragraph): a `params` field commented out,
    an enhancer's per-instance configuration with nowhere typed to go, both swallowed
    with no error at all. An absent `config_model` is not a refusal to be configured
    forever, only *today*; the remedy this names is either dropping the `with:` block,
    or having the plugin declare a `config_model` so it has somewhere to land.
    """


class UndefinedVarError(
    UnresolvedNameInPipelineResolutionError, PipelineResolutionError, UnresolvedNameError
):
    """A `with:` value references `${var:NAME}` and no pipeline in the chain defines it.

    `02` §3 → *Language, and what a var is for*: "An undefined var is a resolution
    error naming the var and the pipeline." Checked against every ancestor's `vars:`
    merged root to leaf, so a var the root never set but a child later supplies is
    still found — the reference is resolved against the *final* chain, not the level
    that wrote it. Also names every var `merged_vars` *does* define at that point —
    the chain's own final answer, already in scope where this raises — so a reader can
    tell a misspelling from a var genuinely missing from every ancestor, rather than
    grepping the whole chain by hand to find out. `stages` names the one stage whose
    `with:` block held the reference — task 1.13's own field, populated here because
    the stage is never absent from scope, unlike a cycle's missing distribution.

    Fitness function 12's family: `valid_options` is every var `merged_vars` defines.

    No `__init__` of its own — task 2.36's repair collapsed this class's own 19-line
    forwarding body into `weft_kernel.runner.UnresolvedNameInPipelineResolutionError`, which
    it now inherits unmodified; see that class's own docstring for why the shared body
    lives in `runner` rather than here, and why `valid_options` staying required and
    keyword-only, with no default, is unaffected by the collapse.
    """


class StaleOperatorTargetError(
    UnresolvedNameInPipelineResolutionError, PipelineResolutionError, UnresolvedNameError
):
    """Task 1.4: an operator names a stage id the running result does not have.

    `02` §3 → the operator table's edge rules: "Every operator is strict. A target id
    absent from the resolved parent fails resolution, naming the id, the pipeline that
    wrote the operator, the parent it resolved against and the ids that do exist." One
    class for `insert`'s `after:`/`before:`, `replace`'s id, `remove`'s id and `set`'s id
    alike — all four are the same failure *kind*, a reference into a parent that turned
    out not to have what it named, which is why they share one name rather than four.
    `remove` gets no exemption: "a `remove` line matching nothing is evidence the parent
    moved under you," the same words `02` §3 uses, not a softer case of this error.

    Task 1.11 widens `remove`'s own half two ways, without adding a fifth name: its
    target may now be a *slot* id as well as a stage id (`_apply_removes` below), and a
    slot's own `after:`/`before:` anchor going missing — because a descendant's `remove`
    took the stage it pointed at, never because the slot itself moved — is the identical
    *kind* of reference-that-turned-out-missing `_slot_anchor_index` raises this for, not
    a sixth error class.

    Fitness function 12's family: `valid_options` is every id that does exist at this
    point in the chain — stage ids and slot ids alike, since either may be a legal
    target depending on the operator.

    No `__init__` of its own — task 2.36's repair collapsed this class's own 19-line
    forwarding body into `weft_kernel.runner.UnresolvedNameInPipelineResolutionError`, which
    it now inherits unmodified; see that class's own docstring for why the shared body
    lives in `runner` rather than here, and why `valid_options` staying required and
    keyword-only, with no default, is unaffected by the collapse.
    """


class OperatorIdCollisionError(PipelineResolutionError):
    """Task 1.4: an `insert` operator's new stage id already exists in the running result.

    `02` §3 → the operator table's edge rules: "`insert` fails equally when its *new* id
    collides with an existing one, or a child would silently shadow a parent's stage." A
    distinct failure *kind* from `StaleOperatorTargetError` above — that one is a
    reference to something missing, this one is a name that is not free to take — so it
    gets its own class rather than a shared one with a reason field, per `02` §3 → *When
    resolution fails*'s "one class per kind rather than one class with a `kind` field."
    """


class DuplicateContributionError(PipelineResolutionError):
    """Task 1.11: two contributions resolve to the identical qualified id.

    `_qualify` stitches a contribution's `distribution` and its own local `stage.id`
    together into the id it wears once placed (`02` §3 → *Slots*: "Contributed stage
    ids are qualified by distribution... so they cannot collide with the author's").
    That guarantee is about a contribution colliding with something the *document*
    wrote; it says nothing about two contributions colliding with *each other* — nothing
    forces a distribution's own `register()` to keep the local ids of the contributions
    it offers unique among themselves. Without this check, `_order_contributions`'s own
    `remaining = {_qualify(c): c for c in contributions}` would silently collapse two
    such contributions to one dict entry — the second one built wins, the first is gone:
    not placed, not refused, and never counted in `unplaced_contributions` either, since
    it never survives long enough to be checked against a declared slot. That is the
    reference's four silently-overwriting registration decorators one seam further in, and
    `02` §3's *Slots* section rules out exactly this shape of collision for an
    author's own stages; this is the same rule applied where two packs, not a pack and
    an author, are the ones that can collide.
    """


class SlotOrderConflictError(PipelineResolutionError):
    """Task 1.11: two or more contributions to one slot cannot be ordered at all.

    `02` §3 → *Slots*: "two contributions in one slot are ordered by the declared
    [`intact`/`destroys`] relations... genuine ties break by distribution name." That
    tie-break only ever runs among contributions with *no* relation between them —
    `_order_contributions` below still has to know what to do when the relations
    themselves cannot be satisfied by any order at all, the same way a cycle in `extends`
    cannot be resolved by trying harder. A distinct failure *kind* from
    `IntactViolationError`: that one checks a single, already-fixed order against a
    constraint; this one is what happens when *no* order would satisfy every declared
    constraint among a slot's contributions, which needs its own name rather than
    borrowing one that presumes an order already exists to be wrong about.
    """


_EMPTY_CONFIG: Final[Mapping[str, object]] = MappingProxyType({})
"""What `ResolvedStage.config` holds for a plugin that declares no `config_model` at all.

Shared rather than rebuilt per stage, on the same reasoning `weft_kernel.pipeline.
_NO_CONFIG` already documents: safe only because nothing can write through a
`MappingProxyType`, so there is nothing a stage's stored default could do to another
stage's if they happened to be the exact same (empty) object.
"""


def _dump_stage_config(value: object) -> object:
    """Serialise `ResolvedStage.config`'s two possible shapes back into something JSON holds.

    A `config_model` instance dumps through its own `model_dump(mode="json")` — pydantic
    already knows how to turn any nested field of its own into JSON-safe data, which a
    third-party plugin's `config_model` gets for free by being a `BaseModel` subclass at
    all. The no-model case is a plain (read-only) mapping already, so `dict(...)` is the
    whole job — the same unwrap `weft_kernel.pipeline._read_only`'s own `PlainSerializer`
    performs for exactly the same reason: pydantic knows how to write a `dict` back to a
    document and refuses a `MappingProxyType` outright.
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(cast("Mapping[str, object]", value))
    return value


type StageConfig = typing.Annotated[
    object, PlainSerializer(_dump_stage_config, return_type=object, when_used="always")
]
"""What `ResolvedStage.config` actually holds — task 1.5.

Either a `config_model` instance the plugin declared and this module validated the
stage's `with:` block against, or an empty read-only mapping for a plugin that declares
none. `object`, not `ConfigBlock` (`weft_kernel.pipeline`'s own `Mapping[str, object]`
alias): the two shapes this field can hold share no common `Mapping` base once one of
them is an arbitrary `BaseModel` subclass a third-party plugin defines, and pydantic
validates an `object`-typed field by accepting whatever `_validate_stage_config` below
already decided to build, rather than trying to coerce it into some narrower shape.
`_dump_stage_config`, defined just above so it exists before this alias's value is ever
evaluated, is the corresponding write side: `model_dump()` needs to know how to turn
either shape back into something JSON can hold.
"""


def _validate_stage_config(
    config: Mapping[str, object],
    *,
    declared: object,
    stage_id: str,
    contract: type[object],
    use: str,
    pipeline_name: str,
) -> object:
    """Validate a stage's (already var-substituted) `with:` block against its plugin's model.

    See the module docstring, *"Config validation runs last, per stage..."*, for why this
    runs after `_substitute_vars` rather than before, and `02` §1's rule this exists to
    make real: "a contract's registration API carries a typed configuration model, or the
    extension point is decorative." `config_model` is read the same defensive way
    `requires`/`intact`/`destroys` already are, off `declared` — the caller's
    `unwrap_factory(entry.factory)` — so a plugin that never declares one answers `None`,
    not an `AttributeError`.

    No model declared and an empty block: nothing to check, returns `_EMPTY_CONFIG`. No
    model declared and a non-empty block: `StageNotConfigurableError`, naming the stage
    and the plugin — a `with:` block with nowhere checked to land must never be silently
    accepted and dropped, which is the reference's own defect this task exists to close. A
    model declared: `config_model.model_validate(config)`, and any `pydantic.
    ValidationError` it raises becomes `InvalidStageConfigError`, naming the stage, the
    plugin, every field pydantic rejected with its own reason, and — read off `config_model.
    model_fields` rather than hand-maintained — what the model actually accepts.
    """
    config_model = cast("type[BaseModel] | None", getattr(declared, "config_model", None))
    if config_model is None:
        if config:
            raise StageNotConfigurableError(
                f"stage '{stage_id}' ({contract.__name__}:{use}) in pipeline '{pipeline_name}' "
                f"sets a 'with:' block ({dict(config)!r}), but {contract.__name__}:{use} "
                f"publishes no configuration model — it cannot be parameterised at all. Drop "
                f"'with:', or have the plugin declare `config_model`.",
                pipeline=pipeline_name,
                stages=(stage_id,),
                remedy=(
                    f"drop the 'with:' block on '{stage_id}', or have {contract.__name__}:"
                    f"{use} declare a `config_model`."
                ),
            )
        return _EMPTY_CONFIG
    try:
        return config_model.model_validate(config)
    except ValidationError as exc:
        problems = "; ".join(
            f"field '{'.'.join(str(part) for part in error['loc']) or '(with block itself)'}': "
            f"{error['msg']}"
            for error in exc.errors()
        )
        accepted = ", ".join(sorted(config_model.model_fields)) or "(no fields)"
        raise InvalidStageConfigError(
            f"stage '{stage_id}' ({contract.__name__}:{use}) in pipeline '{pipeline_name}' has "
            f"an invalid 'with:' block for {config_model.__name__}: {problems}. "
            f"{config_model.__name__} accepts: {accepted}.",
            pipeline=pipeline_name,
            stages=(stage_id,),
            remedy=(
                f"fix the 'with:' fields the message rejected. "
                f"{config_model.__name__} accepts: {accepted}."
            ),
        ) from exc


class ResolvedStage(BaseModel):
    """One stage, checked and fully explicit — no plugin instance, only what building one needs.

    Not `weft_kernel.runner.StageSpec`: that one is handed *by a caller* to
    `Runner.resolve`, already carrying a concrete contract type and a config object a
    caller assembled by hand. This one is what `resolve()` *produces* from a
    `StageDeclaration` — `contract` is document-shaped, printable form (a name) rather
    than a caller-assembled Python type, and `config` — task 1.5 — is the plugin's own
    `config_model` already validated against the stage's `with:` block, or an empty
    mapping for a plugin that declares none. Either way it is data built fresh by this
    call, from what `resolve()` was given, never a caller-assembled object handed in —
    which is what makes two `ResolvedStage`s from two separate `resolve()` calls
    comparable by `==`.

    `provenance` is which pipeline is responsible for this stage existing and running the
    plugin it runs — `02` §3: "every stage in the resolved form records which pipeline or
    pack put it there, so depth stays forensically readable." The root's name for every
    stage the root wrote and no descendant's `insert`/`replace` has touched since; the
    name of whichever descendant's `insert` introduced the stage, or whose `replace` most
    recently swapped its plugin, otherwise. `set` never changes it — overriding
    configuration answers a different question than "who put this stage's plugin here."
    Task 1.11 is what first lets a *pack* be the answer here instead of a pipeline.

    `contract_version` is the *contract's* declared version — `getattr(contract,
    "version", None)`, the same `ClassVar` `weft_extract.contract.Extractor.version`
    and `weft_chunk.contract.Chunker.version` both carry — never defaulted to a
    plausible-looking string when a caller hands `resolve()` a contract that
    declares none: `None` recorded is visible in a diff, a fabricated version is
    not. `02` §3 names "every stage, plugin, version and configuration value" as
    what a resolved pipeline makes explicit; this is that version. It is not the
    *distribution's* version (what a pack upgrade actually bumps, and what
    evaluation would need to diff a retrieval regression across one) — the kernel
    reads no package metadata to know that, and nothing here pretends otherwise
    by inventing a field it cannot fill honestly.

    `applies_to` — task 1.6, `02` §3 → *Applicability* — is the one exception to this
    module's general rule that a check's inputs (`requires`/`provides`/`intact`/
    `destroys`) are read off `declared` and then discarded once they have done their
    job: applicability is not a load-time *check* at all, nothing here evaluates it, so
    there is nothing for it to be discarded after. It is read off `declared` the
    identical defensive way and simply carried onto the record, because `02` §3 states
    it as its own requirement: "The resolved form must print each stage's applicability,
    since a predicate is data." A reader of a `ResolvedPipeline` — a person running
    `weft pipeline show`, eventually, or a test comparing two resolutions — has no other
    way to see what a stage will route around once `weft_kernel.runner` actually runs it.

    **`fallback` is the other field this module deliberately never looks up, and that is
    a second, different exception from `applies_to`'s.** `use` is checked against
    `registry` by `Registry.entry` below, and refuses an unregistered name loudly, by
    design — `01`'s own rule against a silent fallback. `fallback` is not: a document's
    `fallback:` list round-trips from `StageDeclaration` onto this field unchecked,
    exactly as authored, string for string. This is not an oversight this module carries
    quietly — `manual/user-manual.md` §1 and `02` §3's own worked example say so where a
    reader meets the field. Looking a fallback name up *here* would force every fallback
    entry to name a plugin already installed alongside the stage that names it, which
    forecloses exactly the case `fallback:` exists for: a document naming `ocr` as the
    fallback for `text` before any pack ships one, so the document is already correct the
    day a pack providing it is installed, with no edit. `fallback:` is intentionally out
    of `tests/architecture/test_ff11_pipeline_integrity.py`'s check for the identical
    reason: that check exists to catch a stage whose plugin will not run *today*, and a
    fallback naming a plugin nobody has written yet is not that mistake.

    **Phase 2 task 2.28 answered the question this docstring used to leave open**, and the
    answer preserves everything above. `weft_kernel.fallback.try_in_order` now walks the
    list, and `weft_kernel.runner.Runner.resolve` — a *later* step than this one — refuses
    an unregistered fallback name with `UnknownFallbackError`. Not at try time, which
    would make the failure depend on encountering a document the primary cannot read, and
    never by skipping, which is `01` rule 5's silent fallback with extra steps. So the
    promise this module protects is intact and is now visibly a *document*-level one: a
    pipeline may be authored, stored, diffed and derived while naming a plugin nobody has
    shipped; what is refused is making that pipeline runnable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    contract: str
    contract_version: str | None = None
    use: str
    config: StageConfig = Field(default_factory=lambda: _EMPTY_CONFIG)
    fallback: tuple[str, ...] = ()
    applies_to: tuple[Applies, ...] = ()
    distribution: str
    provenance: str


class ResolvedPipeline(BaseModel):
    """A pipeline document reduced to its frozen, fully-explicit form. See the module docstring.

    `vars` holds the **final** merged value of every var in the chain, substituted into
    every stage's `config` already — nothing about a `ResolvedPipeline` requires
    walking `extends` again to understand what it means. `stages` is the root's own list
    with every descendant's operators already folded in, in the order they applied, not
    the order the root originally wrote them. `unapplied_operators` and
    `unplaced_contributions` are carried empty until task 1.11 gives them something to
    hold — task 1.4's operators are strict, never recorded-and-skipped; see the module
    docstring for why the fields exist before their content can.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    vars: VarBlock = Field(default_factory=dict)
    stages: tuple[ResolvedStage, ...] = ()
    unapplied_operators: tuple[str, ...] = ()
    unplaced_contributions: tuple[str, ...] = ()

    @field_validator("vars", mode="after")
    @classmethod
    def _vars_are_read_only(cls, value: Mapping[str, Scalar]) -> Mapping[str, Scalar]:
        return _read_only(value)


def _read_only[K, V](value: Mapping[K, V]) -> Mapping[K, V]:
    """Make a resolved mapping field as frozen as the model that carries it.

    A deliberate duplicate of `weft_kernel.pipeline._read_only`, private to that
    module, for the identical reason `_stage_signature` above is duplicated rather
    than imported — see that function's own docstring. Same shape, same reasoning:
    `frozen=True` blocks rebinding a field, never mutating what it holds, and
    `ResolvedStage.config`/`ResolvedPipeline.vars` are shared, never copied, across
    every stage that came from the same ancestor — see the module docstring's note on
    `extends` reading live parents.
    """
    return MappingProxyType(dict(value))


def resolve(
    pipeline: Pipeline,
    *,
    registry: Registry,
    contracts: Mapping[str, type[object]],
    parents: Mapping[str, Pipeline] = _NO_PARENTS,
    contributions: tuple[Contribution, ...] = _NO_CONTRIBUTIONS,
) -> ResolvedPipeline:
    """Reduce `pipeline` to a frozen, fully-explicit `ResolvedPipeline`. See the module docstring.

    `contracts` must carry an entry for every stage id `pipeline` resolves to,
    including every stage inherited through `extends` **and every contribution that
    might be placed** — task 1.11 widens the same requirement the module docstring
    already states for `extends`, since a contributed id is unknown to the caller's
    `parents` chain the same way an inherited one already was. A missing entry is a
    programming error in the caller, not a pipeline-authoring mistake, so it surfaces
    as a plain `KeyError` naming the stage rather than a `WeftError`: no pipeline
    author can fix a caller's own omission by editing a document.

    Raises `UnknownParentPipelineError` or `PipelineCycleError` while walking
    `extends`; then `StaleOperatorTargetError` or `OperatorIdCollisionError` while
    folding operators onto the root's stage list (task 1.4); then, task 1.11,
    `StaleOperatorTargetError` again for a slot whose own anchor went missing, or
    `SlotOrderConflictError` if two contributions to one slot cannot be ordered at all;
    then, once the merged stage list and the merged `vars` are known, per stage in
    order: `UnknownPluginError` (`Registry.entry`, reused), `StageCompositionError`,
    `UnmetRequiresError`, `IntactViolationError`, `UndefinedVarError` — the five checks
    `02` §3 names for a stage list — and finally, task 1.5, `InvalidStageConfigError` or
    `StageNotConfigurableError` once that stage's `with:` block is fully literal. Run
    once against the list operators and slot-fill have already finished changing, so a
    pipeline with more than one problem always reports the cheapest one first.
    """
    ancestry, merged_vars = _walk_extends(pipeline, parents)
    working_stages, working_slots, provenance, deferred_sets = _apply_ancestry_operators(ancestry)
    unplaced = _fill_slots(
        working_stages,
        working_slots,
        provenance,
        contributions,
        registry=registry,
        contracts=contracts,
        pipeline_name=pipeline.name,
    )
    unapplied = _apply_deferred_sets(working_stages, deferred_sets)
    _check_composition(tuple(working_stages), contracts, pipeline_name=pipeline.name)

    resolved_stages: list[ResolvedStage] = []
    provided: set[type[object]] = set()
    destroyed_by: dict[type[object], str] = {}
    for stage in working_stages:
        contract = contracts[stage.id]
        entry = registry.entry(contract, stage.use)
        declared = unwrap_factory(entry.factory)

        for required in cast("tuple[type[ExtModel], ...]", getattr(declared, "requires", ())):
            if required not in provided:
                available = ", ".join(sorted(model.__name__ for model in provided)) or "(none)"
                raise UnmetRequiresError(
                    f"stage '{stage.id}' ({contract.__name__}:{stage.use}) requires "
                    f"'{required.__name__}' but no earlier stage in pipeline "
                    f"'{pipeline.name}' provides it. Provided so far: {available}.",
                    pipeline=pipeline.name,
                    stages=(stage.id,),
                    distributions=(required.__namespace__,),
                    remedy=(
                        f"add an earlier stage that provides '{required.__name__}', or "
                        f"reorder '{pipeline.name}' so one already does."
                    ),
                )
        for needed_intact in cast("tuple[type[object], ...]", getattr(declared, "intact", ())):
            destroyer = destroyed_by.get(needed_intact)
            if destroyer is not None:
                raise IntactViolationError(
                    f"stage '{stage.id}' ({contract.__name__}:{stage.use}) needs "
                    f"'{needed_intact.__name__}' intact, but stage '{destroyer}' earlier in "
                    f"pipeline '{pipeline.name}' already destroys it. The only legal "
                    f"positions for '{stage.id}' are before '{destroyer}', never after.",
                    pipeline=pipeline.name,
                    stages=(stage.id, destroyer),
                    remedy=f"move '{stage.id}' to before '{destroyer}', never after.",
                )
        provided.update(cast("tuple[type[object], ...]", getattr(declared, "provides", ())))
        for destroyed in cast("tuple[type[object], ...]", getattr(declared, "destroys", ())):
            destroyed_by.setdefault(destroyed, stage.id)

        substituted_config = _substitute_vars(
            stage.config, merged_vars, pipeline_name=pipeline.name, stage_id=stage.id
        )
        validated_config = _validate_stage_config(
            substituted_config,
            declared=declared,
            stage_id=stage.id,
            contract=contract,
            use=stage.use,
            pipeline_name=pipeline.name,
        )

        resolved_stages.append(
            ResolvedStage(
                id=stage.id,
                contract=contract.__name__,
                contract_version=getattr(contract, "version", None),
                use=stage.use,
                config=validated_config,
                fallback=stage.fallback,
                applies_to=cast("tuple[Applies, ...]", getattr(declared, "applies_to", ())),
                distribution=entry.distribution,
                provenance=provenance[stage.id],
            )
        )

    return ResolvedPipeline(
        name=pipeline.name,
        vars=merged_vars,
        stages=tuple(resolved_stages),
        unapplied_operators=tuple(unapplied),
        unplaced_contributions=tuple(unplaced),
    )


def _walk_extends(
    pipeline: Pipeline, parents: Mapping[str, Pipeline]
) -> tuple[tuple[Pipeline, ...], dict[str, Scalar]]:
    """Follow `extends` to its root, returning the whole chain root-first, and merged vars.

    `chain` records every pipeline name visited, in order, purely to make
    `PipelineCycleError` name the whole loop rather than the one repeated name. Vars
    merge root to leaf — each ancestor visited updates the accumulator in the order it
    was walked away from the root, so a leaf's own `vars:` wins last, which is what
    lets `test_a_child_that_only_retargets_a_var_...` see the child's override rather
    than the root's original value. `parents` is read fresh on every call and never
    copied — `02` §3 → *Derivation*: "the parent is referenced, never copied: resolution
    reads live parents" — so editing the `Pipeline` a caller's `parents` mapping points
    at, or handing `resolve()` a different mapping entirely, changes what the very next
    call sees with no cache anywhere in between to go stale.
    """
    chain: list[str] = []
    ancestry: list[Pipeline] = []
    current = pipeline
    while True:
        if current.name in chain:
            raise PipelineCycleError(
                f"pipeline '{pipeline.name}' has a cycle in its 'extends' chain: "
                f"{' -> '.join([*chain, current.name])}. A pipeline cannot extend itself, "
                f"directly or through any number of intermediate parents.",
                pipeline=pipeline.name,
                remedy=(
                    f"break the cycle: {' -> '.join([*chain, current.name])} — remove or "
                    f"retarget one 'extends' link in that chain."
                ),
            )
        chain.append(current.name)
        ancestry.append(current)
        if current.extends is None:
            break
        parent = parents.get(current.extends)
        if parent is None:
            options = tuple(sorted(parents))
            available = ", ".join(repr(candidate) for candidate in options) or "(none)"
            raise UnknownParentPipelineError(
                f"pipeline '{current.name}' extends '{current.extends}', but the parent "
                f"lookup this resolve() call was given has no pipeline named that. Supply it "
                f"in 'parents', or fix the name if it was mistyped. Pipelines available in "
                f"'parents': {available}.",
                valid_options=options,
                pipeline=current.name,
                remedy=(
                    f"add '{current.extends}' to 'parents', or fix '{current.name}'s "
                    f"'extends:' if it was mistyped."
                ),
            )
        current = parent

    ancestry.reverse()  # root first
    merged_vars: dict[str, Scalar] = {}
    for ancestor in ancestry:
        merged_vars.update(ancestor.vars)

    return tuple(ancestry), merged_vars


def _apply_ancestry_operators(
    ancestry: tuple[Pipeline, ...],
) -> tuple[
    list[StageDeclaration], list[SlotDeclaration], dict[str, str], list[tuple[SetOperator, str]]
]:
    """Fold every descendant's operators onto the root's stage list, root to leaf.

    `02` §3 → *Derivation*: "resolve the parent completely, then apply this pipeline's
    operators to that result" — "the same operation at depth one and depth five". The
    root (`ancestry[0]`) is the only pipeline that may carry `stages:` or `slots:`
    (`Pipeline._extends_and_stages_are_mutually_exclusive_with_operators`); every
    pipeline after it in the chain contributes only operators, applied by
    `_apply_operators` against the result the ancestor *before* it left — never against
    the original root — which is what lets a grandchild's `remove` see an id its own
    parent inserted, and what makes depth "the same operation" rather than a special
    case.

    Task 1.11 gives this two more things to carry through, alongside `stages` and
    `provenance`: `slots`, so a descendant's `remove: <slot-id>` can drop one before slot
    fill ever runs (`02` §3: "operators address the author's own stages and slots"); and
    `deferred_sets`, every `set` operator whose target already carries a pack's qualifier
    (`_apply_sets` below) — those cannot apply here, because a contributed id does not
    exist until slot fill runs *after* every ancestor's operators have, so `resolve()`
    applies them separately, once slot fill is done (`_apply_deferred_sets`).
    """
    root = ancestry[0]
    stages: list[StageDeclaration] = list(root.stages)
    slots: list[SlotDeclaration] = list(root.slots)
    provenance: dict[str, str] = {stage.id: root.name for stage in stages}
    deferred_sets: list[tuple[SetOperator, str]] = []
    for descendant in ancestry[1:]:
        _apply_operators(stages, slots, provenance, deferred_sets, descendant)
    return stages, slots, provenance, deferred_sets


def _apply_operators(
    stages: list[StageDeclaration],
    slots: list[SlotDeclaration],
    provenance: dict[str, str],
    deferred_sets: list[tuple[SetOperator, str]],
    pipeline: Pipeline,
) -> None:
    """Apply one pipeline's own operator blocks, in the order its document wrote them.

    `02` §3, settled by task 1.4: "the order in which those keys appear in the document
    is the order they apply." `pipeline.operator_order` is read off the mapping or the
    keyword arguments that built `pipeline`, never assumed from field declaration order
    — see `weft_kernel.pipeline`'s own module docstring for why assuming it would make
    one of *remove-then-insert* and *insert-then-remove* permanently unwritable. `stages`,
    `slots` and `provenance` are mutated in place: they *are* "the running result" `02`
    §3 means by "each validated against the running result", carried from block to block
    within one pipeline and then on to the next descendant in `_apply_ancestry_operators`.
    """
    for key in pipeline.operator_order:
        if key == "insert":
            _apply_inserts(stages, provenance, pipeline)
        elif key == "replace":
            _apply_replaces(stages, provenance, pipeline)
        elif key == "remove":
            _apply_removes(stages, slots, provenance, pipeline)
        elif key == "set":
            _apply_sets(stages, provenance, deferred_sets, pipeline)


def _apply_inserts(
    stages: list[StageDeclaration], provenance: dict[str, str], pipeline: Pipeline
) -> None:
    """`insert`: add `op.stage`, positioned `after:`/`before:` an id already in `stages`.

    Refuses a colliding new id before it refuses a missing target, so two problems in one
    `insert` entry always report the collision — the cheaper, purely-local check.
    """
    for op in pipeline.insert:
        _refuse_id_collision(stages, op.stage.id, pipeline=pipeline)
        target = op.after if op.after is not None else op.before
        index = _index_of(stages, cast("str", target), pipeline=pipeline, operator="insert")
        position = index + 1 if op.after is not None else index
        stages.insert(position, op.stage)
        provenance[op.stage.id] = pipeline.name


def _apply_replaces(
    stages: list[StageDeclaration], provenance: dict[str, str], pipeline: Pipeline
) -> None:
    """`replace`: swap the `StageDeclaration` at an existing id, keeping its position.

    `pipeline.replace` reuses `StageDeclaration` itself rather than a bespoke operator
    model — its own `id` field *is* the target, so "keeping its position" is not a rule
    this function enforces so much as a consequence of `id` staying fixed: `list.
    __setitem__` overwrites the slot `_index_of` found without moving anything else.
    """
    for replacement in pipeline.replace:
        index = _index_of(stages, replacement.id, pipeline=pipeline, operator="replace")
        stages[index] = replacement
        provenance[replacement.id] = pipeline.name


def _apply_removes(
    stages: list[StageDeclaration],
    slots: list[SlotDeclaration],
    provenance: dict[str, str],
    pipeline: Pipeline,
) -> None:
    """`remove`: drop a stage **or a slot** by id. No exemption from strictness — `02` §3.

    Task 1.11, `02` §3 → *Slots*: "`remove: enrich` drops the slot itself, which is how a
    pipeline refuses contributions without naming any pack." A slot id is checked first —
    `Pipeline._slot_ids_are_unique_and_free` already keeps the two vocabularies disjoint,
    so this is never an ambiguous choice, only an ordering of which lookup to try. Neither
    lookup finding `target` gets no softer treatment than task 1.4's own `remove` did:
    still `StaleOperatorTargetError`, now naming both the stage ids and the slot ids that
    do exist, since a typo could plausibly have meant either.
    """
    for target in pipeline.remove:
        slot_index = next((i for i, slot in enumerate(slots) if slot.id == target), None)
        if slot_index is not None:
            del slots[slot_index]
            continue
        stage_index = next((i for i, stage in enumerate(stages) if stage.id == target), None)
        if stage_index is None:
            stage_ids = tuple(stage.id for stage in stages)
            slot_ids = tuple(slot.id for slot in slots)
            existing_stages = ", ".join(repr(stage_id) for stage_id in stage_ids) or "(none)"
            existing_slots = ", ".join(repr(slot_id) for slot_id in slot_ids) or "(none)"
            raise StaleOperatorTargetError(
                f"pipeline '{pipeline.name}' extends '{pipeline.extends}' and its 'remove' "
                f"operator targets id '{target}', but no stage or slot with that id exists "
                f"in the parent it resolved against at this point in the chain. Stage ids "
                f"that do exist: {existing_stages}. Slot ids that do exist: {existing_slots}.",
                valid_options=stage_ids + slot_ids,
                pipeline=pipeline.name,
                stages=(target,),
                remedy=(
                    f"fix the 'remove' target — stage ids that do exist: {existing_stages}; "
                    f"slot ids that do exist: {existing_slots}."
                ),
            )
        del stages[stage_index]
        del provenance[target]


def _apply_sets(
    stages: list[StageDeclaration],
    provenance: dict[str, str],
    deferred_sets: list[tuple[SetOperator, str]],
    pipeline: Pipeline,
) -> None:
    """`set`: override configuration at an id, plugin/position/provenance untouched.

    `{**current.config, **op.config}` builds a **new** plain `dict` rather than writing
    through `current.config` — `weft_kernel.pipeline._read_only` wraps every `with:`
    block in a `MappingProxyType` precisely so an in-place update raises `TypeError`
    instead of silently mutating a mapping the parent, and every *other* child of that
    parent, still shares. `provenance` is deliberately left alone: `02` §3's phrase is
    "who put this stage's plugin here", and `set` never touches which plugin that is —
    see `ResolvedStage.provenance`'s own docstring for the definition this obeys. An
    earlier version of this function moved `provenance` on every `set`, on the reasoning
    that "current behaviour" was the more forensically useful thing to name; that read
    contradicted the definition this module and `ResolvedStage` both state, so it was the
    function that was wrong, not the two docstrings.

    Task 1.11 splits this operator in two. A target carrying no pack qualifier is an
    ordinary stage id, unchanged from task 1.4, applied here and now — `_index_of`
    strict as ever. A target carrying one (`_QUALIFIER in op.id`) names a stage that,
    at this point in resolution, cannot possibly exist yet: slot fill runs only *after*
    every ancestor's operators have (`02` §3: "slots fill after the extends chain
    resolves"), so applying it here would always be `StaleOperatorTargetError`,
    whether or not the pack it names is actually installed. `Pipeline.
    _remove_targets_are_not_a_packs_to_name` already refuses this shape for `remove`; a
    `set` is different precisely because `02` §3 grants it the one exception — "may be
    `set` but never `replaced` or `removed`" — so instead of applying or refusing it
    now, it is appended to `deferred_sets` and settled by `_apply_deferred_sets`, once
    slot fill has had its chance to make the target real.
    """
    for op in pipeline.set:
        if _QUALIFIER in op.id:
            deferred_sets.append((op, pipeline.name))
            continue
        index = _index_of(stages, op.id, pipeline=pipeline, operator="set")
        current = stages[index]
        merged_config = {**current.config, **op.config}
        stages[index] = StageDeclaration(
            id=current.id, use=current.use, config=merged_config, fallback=current.fallback
        )


def _fill_slots(
    stages: list[StageDeclaration],
    slots: list[SlotDeclaration],
    provenance: dict[str, str],
    contributions: tuple[Contribution, ...],
    *,
    registry: Registry,
    contracts: Mapping[str, type[object]],
    pipeline_name: str,
) -> list[str]:
    """Fill every declared slot with its ordered contributions, in place. Task 1.11.

    `02` §3 → *Slots*: "slots fill after the extends chain resolves" — every ancestor's
    operators have already run by the time `resolve()` calls this, so `stages`/`slots`
    are the same "running result" they were the whole way through, just with nothing
    left to change it but this. Every declared slot's own anchor is checked here, via
    `_slot_anchor_index`, **whether or not anything contributes to it** — a slot whose
    `after:`/`before:` target a descendant's own `remove` quietly took out from under it
    is a genuine document defect independent of any pack, and `weft pipeline validate`
    with no packs installed at all must still be able to see it (`StaleOperatorTargetError`,
    see its own docstring's task 1.11 addendum) — never only once someone happens to try
    filling it.

    Refuses a duplicate qualified id across every contribution before any of it is
    grouped or ordered — see `_refuse_duplicate_contributions`.

    Returns every contribution that named a slot this pipeline does not have — `02` §3:
    "a contribution with no matching slot is a recorded no-op". Multiple slots fill from
    a snapshot of every anchor position taken before any insertion, applied highest
    position first so an earlier slot's insertion never shifts a later slot's already-
    computed index — the identical reasoning `_apply_inserts` already relies on for a
    single stage, just batched — **and, among slots sharing one anchor, latest-declared
    first**: `sorted(..., reverse=True)` is stable, so without a declaration-position
    tie-break two same-anchor slots would keep list order going *in*, and inserting both
    at one position then reverses them coming *out* (`stages[index:index] = placed`
    pushes each new batch in front of the one already there). Carrying each slot's own
    `enumerate` position as the tie-break and reversing it too means the *later*-declared
    slot is inserted first and gets pushed in front by the *earlier*-declared one's
    insertion right after it — restoring the declared order rather than reversing it.
    `02` §3's own rule for the document itself, "the written order is the pipeline,"
    applies here without an exception for two slots naming the same anchor.
    """
    _refuse_duplicate_contributions(contributions, pipeline_name=pipeline_name)

    by_slot: dict[str, list[Contribution]] = {}
    for contribution in contributions:
        by_slot.setdefault(contribution.slot, []).append(contribution)

    declared_ids = {slot.id for slot in slots}
    unplaced = [
        f"{_qualify(contribution)} -> slot '{contribution.slot}' (pipeline '{pipeline_name}' "
        f"declares no such slot)"
        for contribution in contributions
        if contribution.slot not in declared_ids
    ]

    fills: list[tuple[int, int, list[StageDeclaration]]] = []
    for declaration_position, slot in enumerate(slots):
        index = _slot_anchor_index(stages, slot, pipeline_name=pipeline_name)
        entries = by_slot.get(slot.id, [])
        if not entries:
            continue
        ordered = _order_contributions(
            entries, registry=registry, contracts=contracts, pipeline_name=pipeline_name
        )
        placed: list[StageDeclaration] = []
        for contribution in ordered:
            qualified_id = _qualify(contribution)
            placed.append(_placed_stage(qualified_id, contribution.stage))
            provenance[qualified_id] = contribution.distribution
        fills.append((index, declaration_position, placed))

    for index, _, placed in sorted(fills, key=lambda item: (item[0], item[1]), reverse=True):
        stages[index:index] = placed

    return unplaced


def _slot_anchor_index(
    stages: list[StageDeclaration], slot: SlotDeclaration, *, pipeline_name: str
) -> int:
    """Where `slot` inserts into `stages` — `after:`/`before:`, on `_apply_inserts`'s own terms."""
    target = slot.after if slot.after is not None else slot.before
    for position, stage in enumerate(stages):
        if stage.id == target:
            return position + 1 if slot.after is not None else position
    options = tuple(stage.id for stage in stages)
    existing = ", ".join(repr(stage_id) for stage_id in options) or "(none)"
    raise StaleOperatorTargetError(
        f"pipeline '{pipeline_name}' declares slot '{slot.id}' positioned against stage id "
        f"'{target}', but no stage with that id exists in the fully resolved chain — an "
        f"ancestor's own operator likely removed or renamed it. The ids that do exist: "
        f"{existing}.",
        valid_options=options,
        pipeline=pipeline_name,
        stages=(cast("str", target),),
        remedy=(
            f"restore stage '{target}', or move slot '{slot.id}'s after:/before: to one "
            f"of the ids that still exist: {existing}."
        ),
    )


def _refuse_duplicate_contributions(
    contributions: tuple[Contribution, ...], *, pipeline_name: str
) -> None:
    """Every contribution's qualified id must be unique before slot-fill groups or orders any.

    Checked globally, across every slot at once, rather than one slot's own entries at a
    time: two contributions naming the same qualified id are exactly as dangerous whether
    they target the same slot or two different ones, since either way both would try to
    wear the identical id once placed into the merged stage list. See
    `DuplicateContributionError` for why this cannot be left to `_order_contributions`'s
    own dict-building to catch — by the time that runs, one of the two is already gone.
    """
    seen: dict[str, Contribution] = {}
    for contribution in contributions:
        qualified = _qualify(contribution)
        earlier = seen.get(qualified)
        if earlier is not None:
            raise DuplicateContributionError(
                f"pipeline '{pipeline_name}': distribution '{contribution.distribution}' "
                f"offers stage id '{contribution.stage.id}' more than once — once for slot "
                f"'{earlier.slot}' and again for slot '{contribution.slot}' — and both "
                f"would resolve to the identical qualified id '{qualified}'. Give each "
                f"contribution its own local stage id.",
                pipeline=pipeline_name,
                stages=(qualified,),
                distributions=(contribution.distribution,),
                remedy=(
                    f"give the contribution offered for slot '{contribution.slot}' its own "
                    f"local stage id, distinct from the one already offered for slot "
                    f"'{earlier.slot}'."
                ),
            )
        seen[qualified] = contribution


def _order_contributions(
    contributions: list[Contribution],
    *,
    registry: Registry,
    contracts: Mapping[str, type[object]],
    pipeline_name: str,
) -> list[Contribution]:
    """One slot's contributions, ordered by declared `intact`/`destroys`, ties by name.

    `02` §3 → *Slots*: "two contributions in one slot are ordered by the declared
    [ordering] relations... genuine ties break by distribution name, so two machines
    with the same installs resolve identically." Mirrors the deterministic-topological-
    sort shape `resolve()`'s own main loop already uses for a whole pipeline — a
    contribution that needs a property intact can never be placed while one that
    destroys it is still unplaced — except tie-broken explicitly rather than falling out
    of list order, because there is no author-written order among contributions to sort
    by: they arrive from however many packs happen to be installed, in no order anyone
    chose.

    A single contribution needs no registry lookup at all — the common case, and the one
    every existing test *without* task 1.11's own ordering fixtures exercises.
    `pipeline_name` — task 1.13 — exists solely so `SlotOrderConflictError` can name the
    pipeline on its own `pipeline` field; nothing here reads the value otherwise.
    """
    if len(contributions) <= 1:
        return list(contributions)

    declared: dict[str, object] = {}
    for contribution in contributions:
        qualified = _qualify(contribution)
        contract = contracts[qualified]
        entry = registry.entry(contract, contribution.stage.use)
        declared[qualified] = unwrap_factory(entry.factory)

    remaining = {_qualify(c): c for c in contributions}
    destroys_of = {
        qid: set(cast("tuple[type[object], ...]", getattr(declared[qid], "destroys", ())))
        for qid in remaining
    }
    intact_of = {
        qid: set(cast("tuple[type[object], ...]", getattr(declared[qid], "intact", ())))
        for qid in remaining
    }

    ordered: list[Contribution] = []
    while remaining:
        ready = [
            qid
            for qid in remaining
            if not any(intact_of[other] & destroys_of[qid] for other in remaining if other != qid)
        ]
        if not ready:
            names = ", ".join(sorted(remaining))
            distributions = tuple(sorted({remaining[qid].distribution for qid in remaining}))
            raise SlotOrderConflictError(
                f"contributions to slot '{contributions[0].slot}' cannot be ordered: "
                f"{names} each need a property intact that another destroys, with no legal "
                f"order between them. Fix the ordering declarations on the plugins involved.",
                pipeline=pipeline_name,
                stages=tuple(sorted(remaining)),
                distributions=distributions,
                remedy=(
                    f"fix the intact/destroys declarations on the plugins behind {names} so "
                    f"some order satisfies every constraint."
                ),
            )
        chosen = min(ready, key=lambda qid: remaining[qid].distribution)
        ordered.append(remaining.pop(chosen))
    return ordered


def _apply_deferred_sets(
    stages: list[StageDeclaration], deferred: list[tuple[SetOperator, str]]
) -> list[str]:
    """Apply every `set` operator that targeted a pack's qualified id, once slots are filled.

    `02` §3 → *Slots*: "Installation-dependent targets are recorded, never fatal... `set:
    weft-graph:entities` where that pack is absent is an unapplied operator in the
    resolved form, not a resolution failure." `_apply_sets` deferred these rather than
    applying or refusing them, because a qualified id cannot exist until `_fill_slots`
    has had its chance to place it — checked here, against the *filled* `stages`, so a
    target that genuinely does not exist (its pack is not installed) is never confused
    with one that merely had not been placed yet.
    """
    unapplied: list[str] = []
    for op, pipeline_name in deferred:
        index = next((i for i, stage in enumerate(stages) if stage.id == op.id), None)
        if index is None:
            unapplied.append(
                f"pipeline '{pipeline_name}' sets configuration for '{op.id}', but no pack "
                f"contributed that stage — the pack providing it is not installed. The set "
                f"is recorded, not applied."
            )
            continue
        current = stages[index]
        merged_config = {**current.config, **op.config}
        stages[index] = _qualified_stage(
            id=current.id, use=current.use, config=merged_config, fallback=current.fallback
        )
    return unapplied


def _index_of(
    stages: list[StageDeclaration], target: str, *, pipeline: Pipeline, operator: str
) -> int:
    """The position of `target` in `stages`, or `StaleOperatorTargetError` naming everything."""
    for position, stage in enumerate(stages):
        if stage.id == target:
            return position
    options = tuple(stage.id for stage in stages)
    existing = ", ".join(repr(stage_id) for stage_id in options) or "(none)"
    raise StaleOperatorTargetError(
        f"pipeline '{pipeline.name}' extends '{pipeline.extends}' and its '{operator}' "
        f"operator targets stage id '{target}', but no stage with that id exists in the "
        f"parent it resolved against at this point in the chain. The ids that do exist: "
        f"{existing}.",
        valid_options=options,
        pipeline=pipeline.name,
        stages=(target,),
        remedy=f"fix the '{operator}' target — ids that do exist: {existing}.",
    )


def _refuse_id_collision(
    stages: list[StageDeclaration], new_id: str, *, pipeline: Pipeline
) -> None:
    """`insert`'s new id must be free — `02` §3: it "would silently shadow a parent's stage"."""
    if any(stage.id == new_id for stage in stages):
        raise OperatorIdCollisionError(
            f"pipeline '{pipeline.name}' extends '{pipeline.extends}' and its 'insert' "
            f"operator adds stage id '{new_id}', but a stage with that id already exists "
            f"in the parent it resolved against — inserting it would silently shadow the "
            f"existing stage. Pick a different id, or use 'replace'/'set' if the intent "
            f"is to change the existing stage.",
            pipeline=pipeline.name,
            stages=(new_id,),
            remedy=f"pick a stage id other than '{new_id}', or use 'replace'/'set' instead.",
        )


def _stage_signature(contract: type[object]) -> tuple[object, object]:
    """The `(In, Out)` `contract` declared via `Stage[In, Out]` as one of its own bases.

    A deliberate duplicate of `weft_kernel.runner._stage_signature`, not an import of
    it: that name is private to `runner`, and this module's own composition check runs
    over `StageDeclaration`s and a caller-supplied `contracts` mapping rather than
    `runner.StageSpec`s, so the two call sites read `__orig_bases__` off the same kind
    of object for two genuinely different resolution mechanisms. Ten lines duplicated
    on purpose reads better a year from now than a private cross-module import would.
    """
    for base in getattr(contract, "__orig_bases__", ()):
        if typing.get_origin(base) is Stage:
            args = typing.get_args(base)
            if len(args) == 2:  # noqa: PLR2004 - Stage is fixed at two type parameters
                return args[0], args[1]
    raise StageCompositionError(
        f"'{contract.__name__}' does not declare Stage[In, Out] as a base — every contract "
        f"used in a pipeline states what it consumes and produces, e.g. "
        f"class YourContract(Stage[list[In], list[Out]], Protocol).",
        remedy=(
            f"declare `class {contract.__name__}(Stage[In, Out], Protocol)` on the contract itself."
        ),
    )


def _check_composition(
    stages: tuple[StageDeclaration, ...],
    contracts: Mapping[str, type[object]],
    *,
    pipeline_name: str,
) -> None:
    """Every consecutive pair of `stages` composes, checked purely against `contracts`.

    Mirrors `weft_kernel.runner._check_composition` exactly, one payload type pair per
    contract read off `Stage[In, Out]`'s own `__orig_bases__` — the same reading `02`
    §3's own narrowing note describes. Run before any registry lookup, so a
    mis-ordered pipeline fails on the cheapest check first. `pipeline_name` — task
    1.13 — exists solely so `StageCompositionError` can name the pipeline.
    """
    previous: tuple[str, object] | None = None
    for stage in stages:
        contract = contracts[stage.id]
        payload_type, produced_type = _stage_signature(contract)
        if previous is not None:
            previous_id, previous_produced = previous
            if previous_produced != payload_type:
                raise StageCompositionError(
                    f"stage '{stage.id}' ({contract.__name__}:{stage.use}) expects "
                    f"{payload_type!r}, but the previous stage '{previous_id}' produces "
                    f"{previous_produced!r}. Consecutive stages must compose by type.",
                    pipeline=pipeline_name,
                    stages=(previous_id, stage.id),
                    remedy=(
                        f"reorder pipeline '{pipeline_name}' so '{previous_id}' precedes a "
                        f"stage expecting {previous_produced!r}, or so '{stage.id}' follows "
                        f"one producing {payload_type!r}."
                    ),
                )
        previous = (stage.id, produced_type)


def _substitute_vars(
    config: Mapping[str, object],
    merged_vars: Mapping[str, Scalar],
    *,
    pipeline_name: str,
    stage_id: str,
) -> Mapping[str, object]:
    """Recursively resolve every `${var:NAME}` string in `config` against `merged_vars`.

    Mirrors `weft_kernel.discovery.interpolate_env` exactly — see the module docstring
    for why. A string that is *exactly* `${var:NAME}` becomes that var's value; a
    string merely containing the token passes through untouched; `dict` and `list`
    recurse so a whole `with:` block substitutes in one call. `stage_id` is plumbed
    through for the identical reason `pipeline_name` already was — task 1.13's repair:
    an `UndefinedVarError` raised deep inside a nested `with:` block still needs to name
    which stage's block it came from, and the caller below is the only frame that knows.
    """
    return cast(
        "Mapping[str, object]",
        _substitute(config, merged_vars, pipeline_name=pipeline_name, stage_id=stage_id),
    )


def _substitute(
    value: object, merged_vars: Mapping[str, Scalar], *, pipeline_name: str, stage_id: str
) -> object:
    if isinstance(value, str):
        match = _VAR_TOKEN.match(value)
        if match is None:
            return value
        name = match.group(1)
        if name not in merged_vars:
            options = tuple(sorted(merged_vars))
            defined = ", ".join(repr(key) for key in options) or "(none)"
            raise UndefinedVarError(
                f"'{value}' references var '{name}' in stage '{stage_id}', but pipeline "
                f"'{pipeline_name}' defines no such var — not directly, and none of its "
                f"ancestors do either. Add it to a 'vars:' block somewhere in the chain, or "
                f"fix the reference. Vars defined in this chain: {defined}.",
                valid_options=options,
                pipeline=pipeline_name,
                stages=(stage_id,),
                remedy=f"add 'vars: {{{name}: ...}}' somewhere in the chain, or fix the reference.",
            )
        return merged_vars[name]
    if isinstance(value, Mapping):
        items = cast("Mapping[str, object]", value)
        return {
            key: _substitute(item, merged_vars, pipeline_name=pipeline_name, stage_id=stage_id)
            for key, item in items.items()
        }
    if isinstance(value, list):
        entries = cast("list[object]", value)
        return [
            _substitute(item, merged_vars, pipeline_name=pipeline_name, stage_id=stage_id)
            for item in entries
        ]
    return value
