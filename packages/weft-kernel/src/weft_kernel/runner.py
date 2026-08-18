"""The linear runner — an explicit, ordered `StageSpec` list, resolved once and run batch by batch.

Specified in `docs/06-phase-0-build.md` step 6 and `docs/02-extension-model.md`
section 1 ("What a plugin receives", "Composition is typed and checked at
load"). This is the second of `06`'s three places Phase 0 could accidentally
settle **G2** (pipeline derivation semantics, open): a pipeline here is a
`Sequence[StageSpec]` a caller writes out in full. No `extends`, `insert`,
`replace`, `remove` or `set`, and no derivation of any kind — that machinery
is Phase 1's, after G2 closes. `06`: *"a plan with no derivation operators
cannot silently place a stage between two cleaning stages, which is exactly
why the choice is shaped this way."*

**`Lifetime` and `Stage[In, Out]` are built here**, not in an earlier step,
because nothing before this one needed them: step 3 (the seam) wraps a bare
async callable with no opinion on what it is a method of; step 4 (the
passport) hands `Context` to whatever calls it; discovery (step 5) registers
factories, never instances. The runner is the first thing that has to
*resolve and run a chain of them*, which is what forces the shape a plugin
class must have.

**Five checks happen before a single batch runs — "at resolution", never
discovered later as a runtime `KeyError`** (`06` step 6; the fourth is G2's,
task 1.2, and the fifth is Phase 2's, task 2.28):

1. **The plugin exists.** `Registry.entry` already raises `UnknownPluginError`
   naming the contract, the name that was wanted, and every name that *is*
   registered — reused here unchanged, not re-implemented.
2. **`requires` is produced by an earlier stage.** Checked model by model
   against the `provides` every earlier stage in the same list declared,
   accumulated as resolution walks the list in order. A miss raises
   `UnmetRequiresError` naming the stage, the missing `ExtModel` and its
   `__namespace__` — which doubles as the pack that owns it, the same
   convention `docs/02-extension-model.md` section 1 uses throughout.
3. **Consecutive stages compose by type.** `Stage[In, Out]` — see below for
   where `In`/`Out` actually come from.
4. **`intact` was not destroyed by an earlier stage.** `docs/02-extension-model.md`
   §3 → *Ordering constraints*: G5's `requires`/`provides` solve ordering by
   data dependency, and "it cannot solve the cleaning chain, because
   `WhitespaceNormalizer` must run last for being *destructive*, not because
   anyone reads its output." `intact` and `destroys` are the mirror,
   accumulated the same way `provides` is — a running set of every
   `weft_kernel.payload.Property` an earlier stage's `destroys` named, with
   which stage named it — so a later stage needing one `intact` fails,
   naming the stage, the property, the stage that destroyed it, and that the
   only legal positions for the needing stage are *before* the one that
   destroys it. Unlike `requires`/`provides`, `destroys` is **mandatory** on
   every plugin registered for a contract that opts into this — see
   `weft_kernel.registry`'s own docstring for that half, which happens at
   registration, before this module ever sees the plugin; `intact` stays an
   optional convention read defensively here exactly as `requires` already
   is.

5. **Every `fallback:` name exists, and stands in for the primary**, task
   2.28. A stage may name other plugins to try when its own refuses the
   position, and the chain that walks them is
   `weft_kernel.fallback.try_in_order` — a combinator over any contract,
   which is why it lives in its own module and not in this one. What
   happens *here* is the lookup: each name is resolved against the
   registry at resolution and refused as `UnknownFallbackError` if
   nothing registered it, so a chain that cannot run fails before a batch
   does rather than on the first document the primary could not read.
   Each is then compared with the primary it would replace — checks 2 and
   4 above were answered by the primary's declarations alone, so a
   fallback demanding more or promising less is refused as
   `FallbackNotSubstitutableError` rather than corrupting a run on
   exactly the documents nobody tested. Both are class-level reads, so
   the candidates themselves are still **built lazily, at try time** and
   an uninstantiable fallback costs nothing while the primary is working
   — see `_chain`, `_attempt` and `_built_of`, the last of which is why a
   fallback the run actually reached is still flushed.

**Where a pipeline's types actually come from — a narrowing worth stating
plainly.** `docs/02-extension-model.md` → *Composition is typed and checked
at load* writes `Stage[In, Out]` once per *contract*, not once per plugin —
see that section for the per-capability examples the kernel itself does not
restate. That reading is what this module implements: a `StageSpec.contract`
is expected to declare `Stage[In, Out]` as one of its own bases, and the
composition check reads `In`/`Out` off the *contract* via `__orig_bases__` —
never off the plugin, which may satisfy a contract structurally with no
declared base at all. This is a deliberate, documented choice, not an
oversight: contracts are few and already generic, one plugin implementing
several contracts would otherwise have to restate the same pair of types
redundantly, and Phase 0 has no contract yet to prove the alternative against
— step 7 is expected to follow this convention, and `docs/02-extension-model.md`
§1 carries the same note.

**`requires`, `provides` and `lifetime` are read off the constructed
instance, defensively, and `Stage` declares none of them.** `run` is the
only member `Stage`'s body carries. `typing.Protocol` computes
`__protocol_attrs__` — the set `isinstance` checks against on a
`@runtime_checkable` Protocol — by walking every base class's `__dict__`,
`Stage` included; a `ClassVar` declared on `Stage` would therefore become a
required `isinstance` member of every contract built on `Stage[In, Out]`
(`Chunker`, `Extractor`, `NodeStore`, …), not merely an inheritable
convenience. `getattr(instance, name, default)` already supplies
`Lifetime.RUN` / `()` / `()` when a plugin never sets them — whether or not
that plugin inherits `Stage` at all — so nothing about correctness depends
on `Stage` declaring these, only on the runner reading them defensively.
See `docs/02-extension-model.md`'s Phase 0 step 7 narrowing note.

**The instance cache honours `Lifetime`.** Keyed `(tenant_id, contract, name,
config_hash)`, per `docs/02-extension-model.md` section 1 — `config_hash` is
a content hash rather than the config object itself, so a config holding an
unhashable field (a plain `dict`, say) does not make caching impossible.
`Lifetime.RUN` — the default — is never written to the cache: a fresh
instance is built every time `resolve()` runs, reused only for the stages of
*that* `RunnablePipeline`, exactly as "a fresh instance per pipeline run, no
thread-safety obligation on the author" describes. `Lifetime.PROCESS` is
written once and read back by every later `resolve()` call sharing the same
key, on the same `Runner` — which is therefore expected to live for the
process, not be rebuilt per run, or the cache buys nothing.

**`flush()` is the runner's, never a stage's.** `docs/02-extension-model.md`:
"there is no `persist()`... `add()` may buffer; **the kernel runner calls
`flush`** at the end of a run and on cancellation, so no plugin can forget
it." The kernel names no capability, so it cannot know which stages own
persistence — instead every resolved instance that happens to expose an
async, callable `flush()` is flushed, once, whether or not it needs one.
`flush` is documented as idempotent, so calling it on something that has
nothing to flush is a legitimate no-op, never a hazard. Every stage gets its
chance regardless of an earlier one's failure — see `_flush_all` — and each
call carries the same span and attribution `weft_kernel.seam.wrap` gives
`run()`, via `weft_kernel.seam.wrap_flush`.

**`run` returns a `RunSummary`, sized by outcome count, never by payload.**
`docs/02-extension-model.md` → *Composition is typed and checked at load*:
"the kernel runner owns batching, so memory is bounded by batch size rather
than corpus size." Retaining every batch's whole `Outcome` — in particular a
`Produced` batch's produced value — for the life of a run would make that
false for the one component that owns the promise: peak memory would grow
with the corpus, not the batch. `RunSummary` carries only counts of
`Produced` / `NothingToProduce` / `Failed`, plus the reasons the latter two
gave, so a batch's payload is free to be collected the moment it has been
counted.

**Applicability is routed here, task 1.6 — `docs/02-extension-model.md` §3 →
*Applicability*.** `weft_kernel.payload.applicability.Applies` is what a
stage's `applies_to` declares; this module is "the seam" that section keeps
promising will do the evaluating, on the identical `getattr(instance,
"applies_to", ())` footing `_requires_of`/`_intact_of` already read. An
empty tuple — no plugin written before this task declares one — means every
node satisfies it vacuously, so `_run_one_batch` below skips straight to
the single whole-batch call it always made; nothing about a stage that never
opts in changes. A non-empty tuple, against a payload that is a `Sequence`
of `Node` (never a bare `str`/`bytes`, which are sequences of the wrong
thing entirely), splits the batch into its **maximal contiguous runs** of
"every `Applies` matches" and "at least one does not" — `_segment_by_
applicability` — runs the stage once per matching run, and threads every
non-matching run through unchanged, in the position it already held.
Contiguous *runs*, not a single filtered call over every matching node,
because a chunker's `Sequence[Node] -> Sequence[Node]` is not shape-
preserving: calling it once over the whole matching subset would return one
undifferentiated sequence with no record of where an untouched node
originally separated two matching ones, and there would be nothing left to
recombine correctly. This is `docs/11-multimodal.md` §2's own claim made
literal: "An atomic node passes the chunker unsplit, and the chunker does
not have to know that" — the chunker's `run` carries no branch on any
node's content; the branch lives here, once, for every stage that ever
declares `applies_to`. A payload that is not a routable `Sequence[Node]` at
all — a `Query`, say, for a stage at the query-path end of `Stage[In, Out]`
— runs exactly as an empty `applies_to` would: applicability is a node-
level mechanism, and nothing about the kernel could recognise "this payload
is nodes" without naming the capability that produces them.

**One batch in flight**, per `01` → *Colour*: `run` walks its batches with a
plain `async for`, awaiting one batch's whole chain of stages before the next
batch's `__anext__` is even requested. No `asyncio.gather`, no per-batch task
— parallelism, if a stage wants it, is the stage's own concern over the one
batch it was handed.

**`CancelledError` propagates untouched — including when its own cleanup
fails.** `run` catches `BaseException`, not `Exception`, around the batch
loop, so a `CancelledError` raised mid-run still reaches `_flush_all` before
`raise` sends it on. Every stage still gets its chance to flush. The
narrower hazard is what `_flush_all` normally does on a flush failure:
it raises `FlushError`, and raising anything from inside an `except` block
handling `exc` replaces `exc` on the way out — a `CancelledError` would
surface only as `FlushError.__context__`, silently converting a cancelled
task into one that merely raised. So `_flush_all` takes the exception
already in flight and, when one is present, never raises on top of it: a
flush failure is attached to it as a note instead. The result is `01` →
*Colour*'s requirement exactly: never caught, never rewritten, whether or
not cleanup itself succeeds.
"""

from __future__ import annotations

import hashlib
import typing
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.fallback import Attempt, try_in_order
from weft_kernel.payload import (
    Applies,
    ExtModel,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    Property,
)
from weft_kernel.registry import Registry, RegistryEntry, UnknownPluginError, unwrap_factory
from weft_kernel.seam import wrap, wrap_flush


class Lifetime(StrEnum):
    """How long one resolved stage instance may be reused. `02` §1 → *What a plugin receives*."""

    RUN = "run"
    PROCESS = "process"


class Stage[In, Out](Protocol):
    """The shape every registered plugin class satisfies. `02` §1 → *What a plugin receives*.

    A contract publishes this specialised — see `docs/02-extension-model.md`
    → *Composition is typed and checked at load* for the per-capability
    examples — which is what the composition check in this module reads back
    via `__orig_bases__`. A plugin implementing that contract does not need
    to name `Stage` itself.

    **`run` is the only member declared here, deliberately.** `Lifetime`,
    `requires` and `provides` are conventions a plugin *may* set — read
    defensively off the constructed instance by `_lifetime_of`,
    `_requires_of` and `_provides_of` below — never declared as `ClassVar`s
    on this Protocol. See the module docstring, *"`requires`, `provides` and
    `lifetime` are read off the constructed instance, defensively, and
    `Stage` declares none of them."*
    """

    async def run(self, payload: In, ctx: Context) -> Outcome[Out]: ...


class PipelineResolutionError(WeftError):
    """The family base for every way a pipeline can fail to resolve. `02` §3 → *When
    resolution fails*: "each failure is its own `WeftError` subclass under a
    `PipelineResolutionError` family base, all carrying the same required fields — the
    pipeline, the stage ids, the distributions in conflict, and the remedy."

    **Never raised directly, task 1.13.** It used to be — this class alone covered three
    unrelated checks (an unmet `requires`, two stages that do not compose, an `intact`
    property already destroyed), told apart only by reading the message. `02` §3 names
    exactly the failure this is: "a fat class would present one already-documented name
    and let a dozen new failure modes ship undocumented" to the 0.14 coverage ratchet,
    which derives its required set from subclass *names* — and it is not hypothetical
    here, it is what `weft_kernel.resolution.resolve()` already proved wrong for the
    identical three checks, giving each its own name (`UnmetRequiresError`,
    `StageCompositionError`, `IntactViolationError`, below) for a pipeline *document*.
    Since a `StageSpec` list and a resolved document fail these three checks for the
    literal same reason — `weft_kernel.resolution`'s own docstring already says as much,
    "the same check `weft_kernel.runner.PipelineResolutionError` performs for an explicit
    `StageSpec` list" — the fix is not three *new* names, it is reusing these three,
    defined here because `Runner.resolve` was the first to need them and `weft_kernel.
    resolution` already imports this module's base.

    **The four fields are real attributes, not prose.** Before task 1.13 the pipeline, the
    failing stage ids, the distributions in conflict and the remedy lived only inside each
    subclass's own formatted message — readable by a person, unreachable by a caller (the
    CLI's exit-code mapping, a future report) without parsing English. `pipeline` is
    `None`, never a placeholder, where there genuinely is none to name — an anonymous
    `StageSpec` list has no name at all, the identical honesty `02` §3 already asks of
    `UnknownParentPipelineError`'s "no stage ids and no distribution to name" for a
    missing parent. `stages` and `distributions` default to `()`, `remedy` to `""`, for
    the same reason: an empty tuple is a fact ("nothing here"), never a lie about data
    that was never computed.
    """

    def __init__(
        self,
        message: str,
        *,
        pipeline: str | None = None,
        stages: tuple[str, ...] = (),
        distributions: tuple[str, ...] = (),
        remedy: str = "",
    ) -> None:
        super().__init__(message)
        self.pipeline = pipeline
        self.stages = stages
        self.distributions = distributions
        self.remedy = remedy


class UnresolvedNameInPipelineResolutionError:
    """The shared `__init__` for every `PipelineResolutionError` subclass that is *also*
    `UnresolvedNameError` — task 2.36's own repair.

    Task 2.36 gave `UnknownParentPipelineError`, `UndefinedVarError` and
    `StaleOperatorTargetError` (`weft_kernel.resolution`) and `UnknownFallbackError`
    (below) an identical 19-line `__init__`: forward the family base's four fields, then
    set `self.valid_options`. Four copies of the same body is exactly the shape `01`'s own
    rule against a fat class exists to prevent one level down — not four failure *kinds*
    sharing a name, but one failure kind (a name that did not resolve against an
    enumerable set of alternatives, inside pipeline resolution specifically) written out
    four times. This class is that body, written once; each of the four now declares it
    as their *first* base — so it is the one Python's MRO finds `__init__` on — and
    declares no `__init__` of its own.

    **The guarantee this exists to serve is unchanged, not merely preserved by accident.**
    `valid_options` stays a required, keyword-only parameter with no default — the same
    signature the four used to each declare by hand — so a raise site that forgets it
    still fails to construct the exception at all, `TypeError` before a `WeftError` even
    exists to catch. Nothing about collapsing four bodies into one changes what the one
    body requires.

    **Not itself a `WeftError`, on the identical footing `weft_kernel.errors.
    UnresolvedNameError`'s own docstring already states for the marker it is mixed in
    alongside.** Three separate reasons converge on this one shape:

    - *A `PipelineResolutionError` base would make it a `WeftError` subclass, and
      `tests/docs/test_troubleshooting_coverage.py`'s own coverage ratchet — task 0.14,
      `08` §3 clause (d) — requires a `manual/troubleshooting.md` entry for every
      `WeftError` subclass the first-party tree defines, pinned-empty waiver only by a
      dated decision-log entry.* This class is never raised on its own — only its four
      concrete subclasses ever are — so it names no failure mode a user ever meets in a
      traceback; writing a troubleshooting entry for a class nobody encounters would be
      documentation invented to satisfy a check rather than to help a reader, exactly
      what `08`'s own rule exists to prevent in the other direction. Not inheriting
      `WeftError` at all is the honest way to keep it out of that requirement, mirroring
      the precedent already sitting one class over: `UnresolvedNameError` itself is "not
      itself a `WeftError`, and defines no `__init__` of its own" for the same reason —
      it is a marker/mixin, not a failure mode with its own identity.
    - *Calling `PipelineResolutionError.__init__(self, ...)` explicitly, never via
      `super()`, is what makes the base unnecessary.* Every concrete subclass below still
      lists `PipelineResolutionError` as an actual base (so `isinstance` and
      `PipelineResolutionError.__subclasses__()` see it exactly as before) — this class
      only has to supply the four raise sites' shared `__init__` *body*, not sit in the
      inheritance chain itself. Listed first among a subclass's bases, so Python's MRO
      finds `__init__` here before it reaches `PipelineResolutionError`'s own. The `cast`
      below is what that split costs statically: this class alone has no way to promise
      pyright that whatever mixes it in also mixes in `PipelineResolutionError`, so the
      call is annotated true rather than left for strict mode to refuse. Every real
      subclass keeps the promise the cast makes.
    - *Not `_`-prefixed, because pyright's strict mode makes that choice unavailable for a
      class actually reused across modules.* A leading underscore was tried first, on
      `weft_kernel.pipeline._QUALIFIER`'s own precedent — but that precedent is for a
      private *constant*, duplicated on purpose rather than imported, exactly because
      duplicating one character is cheaper than coupling two modules over it. A shared
      `__init__` is not that: the entire point of writing it once is that both this
      module (`UnknownFallbackError`) and `weft_kernel.resolution` (the other three)
      construct the *same* class, so duplicating it would silently reproduce the very
      duplication task 2.36's review found. `reportPrivateUsage` under
      `[tool.pyright] typeCheckingMode = "strict"` refuses a leading-underscore name
      imported into another module's source regardless of package boundary, which makes
      the `_QUALIFIER` shape structurally unavailable here — the concrete fact that
      decided the question, not merely a style preference. It stays out of
      `weft_kernel/__init__.py`'s own export list all the same: no contract in `02` gives
      a pack a reason to raise `PipelineResolutionError`'s specific four-field shape —
      that family is raised only by `weft_kernel.resolution.resolve` and `Runner.resolve`
      themselves — so a pack wanting `01` requirement 5's guarantee for its own error
      hierarchy mixes in `UnresolvedNameError` directly instead, exactly as
      `weft_llm.models.UnknownModelError` and every other non-`PipelineResolutionError`
      family member already do.

    **Deliberately does not mix in `UnresolvedNameError` itself.** If it did, it would be
    a direct subclass of the marker, and fitness function 12's own family walk
    (`test_ff12_unresolvable_name_carries_options.py`'s `_all_unresolved_name_subclasses`,
    which starts from `UnresolvedNameError.__subclasses__()`) would discover it as a 21st
    member alongside the 20 pinned in `NAME_RESOLUTION_FAMILY` — an accounting artifact of
    this refactor, not a new failure kind, and exactly the kind of thing that check exists
    to catch rather than silently absorb. Each of the four concrete subclasses below still
    writes `UnresolvedNameError` as its own base, so `issubclass(cls, UnresolvedNameError)`
    is unchanged for every one of them and the family the fitness function counts stays at
    20. Neither that walk nor `weft_kernel.errors.UnresolvedNameError.__subclasses__()`
    needed to become more recursive for this to hold — both already are, and a class that
    is this one's *user* rather than its subclass is never reached walking downward from
    either the marker or `WeftError`, since this class is a subclass of neither.
    """

    valid_options: tuple[str, ...]

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
            cast("PipelineResolutionError", self),
            message,
            pipeline=pipeline,
            stages=stages,
            distributions=distributions,
            remedy=remedy,
        )
        self.valid_options = valid_options


class UnmetRequiresError(PipelineResolutionError):
    """A stage's `requires` names an `ExtModel` no earlier stage in this list provides.

    Moved here at task 1.13 from being one of three checks `PipelineResolutionError`
    itself used to raise bare — see that class's own docstring. `weft_kernel.resolution`
    imports this rather than declaring a second class of the same name for the identical
    check against a pipeline *document*: two classes for one kind is exactly what `02` §3
    → *When resolution fails* rules out ("one class per kind rather than one class with a
    kind field"), and `Runner.resolve` and `weft_kernel.resolution.resolve` disagreeing
    about what to call the same failure would be that rule broken across two modules
    instead of inside one.
    """


class StageCompositionError(PipelineResolutionError):
    """Two consecutive stages do not compose: one's `Out` is not the next one's `In` — or a
    contract in the list does not declare `Stage[In, Out]` as a base at all, so there is no
    type pair to compare in the first place. See `UnmetRequiresError`'s own docstring for
    why this is imported by `weft_kernel.resolution` rather than redefined there.
    """


class IntactViolationError(PipelineResolutionError):
    """A stage needs a `Property` `intact` that an earlier stage's `destroys` already named.

    Task 1.2, `02` §3 → *Ordering constraints*. See `UnmetRequiresError`'s own docstring
    for why this is imported by `weft_kernel.resolution` rather than redefined there.
    """


class UnknownFallbackError(
    UnresolvedNameInPipelineResolutionError, PipelineResolutionError, UnresolvedNameError
):
    """A stage's `fallback:` list names a plugin no distribution registered — task 2.28.

    No `__init__` of its own — task 2.36's repair collapsed this class's own 19-line
    forwarding body into `UnresolvedNameInPipelineResolutionError` above, which it now
    inherits unmodified; see that class's own docstring for why the shared body lives
    here rather than in `weft_kernel.resolution`, and why `valid_options` staying
    required and keyword-only, with no default, is unaffected by the collapse.

    **Refused here, and deliberately not in `weft_kernel.resolution`.** That module carries
    a document's `fallback:` names through unchecked, on purpose and at length (see
    `ResolvedStage.fallback`'s own docstring): a pipeline document may legitimately name
    `ocr` as a fallback before any pack ships one, and it must stay authorable, storable,
    diffable and derivable while that is true. What this class refuses is a different
    claim — making that document **runnable**. The two are separable because
    `Runner.resolve` is a later step than `resolve()`, and keeping them separate is what
    lets the late-binding promise and the no-silent-fallback rule both hold.

    **Why not at try time.** Refusing when the chain is first *reached* would make the
    failure depend on encountering a document the primary cannot read, so a pipeline could
    be green for a year and fail in production the first time it met a scanned page.
    Skipping the unknown name instead is `01` requirement 5's silent fallback with extra
    steps — it degrades quality precisely on the inputs the fallback existed for.

    Fitness function 12's family: `valid_options` is every name registered for the
    stage's own contract.
    """


class FallbackNotSubstitutableError(PipelineResolutionError):
    """A `fallback:` entry demands more or promises less than the primary it stands in for.

    A repair to task 2.28, which checked a fallback only for existence. Every
    `requires`, `intact` and downstream `IntactViolationError` check `resolve` performs
    was answered by the **primary**'s declarations, because the primary is the only
    candidate resolution knows will run. A fallback that `destroys` a `Property` the
    primary does not therefore resolves clean and then corrupts a later stage's input —
    and it does so only on the documents the primary could not read, which is precisely
    where a test never looks. `02` §3 names that asymmetry as the one the kernel exists
    to close: "forgetting `destroys` silently corrupts a stranger's, and the pack that
    caused it never sees a failure." `provides` is the mirror: a downstream
    `UnmetRequiresError` satisfied by the primary's declaration leaves a later stage
    running against an `ExtModel` that is not there.

    So the rule is one sentence — **a fallback may demand no more and promise no less
    than the primary** — and its four halves are `requires`, `intact`, `provides` and
    `destroys`. Declaring *more* than the primary in the safe direction (providing an
    extra model, destroying one property fewer) is not refused: it is the difference
    that would invalidate a check already made that is.

    **Read off the class, not off an instance** — `weft_kernel.registry.unwrap_factory`,
    exactly as `weft_kernel.resolution.resolve` and `Registry`'s own `destroys`
    mandatoriness already read the same four declarations. That is what lets this check
    cost a `getattr` while candidates stay built lazily, at try time.
    """


class TenantMismatchError(WeftError):
    """`run()` was given a `Context` for a tenant this pipeline was not resolved for.

    `docs/02-extension-model.md`'s cache note is explicit: the instance
    cache is keyed `(tenant_id, contract, name, config_hash)`, and "the
    tenant is in the key or multi-tenancy is broken on day one." A
    `RunnablePipeline` remembers the tenant `resolve()` built it for; `run()`
    refuses rather than silently executing it against a different tenant's
    `Context`, naming both.
    """


class FlushError(WeftError):
    """One or more resolved stages failed to flush. Raised once, after every stage was tried.

    `Runner._flush_all` gives every stage a chance to flush regardless of an
    earlier one's failure — a completed run must stay durable even when an
    unrelated stage's flush raised, and the store is normally last in the
    list. `__cause__` is the first failure encountered, so its traceback is
    never lost; the message names every stage that failed.
    """


@dataclass(frozen=True, slots=True)
class StageSpec:
    """One named position in an explicit, fully-written-out pipeline.

    `06` step 6's half of G2's minimal, reversible choice: a pipeline is a
    plain `Sequence[StageSpec]`, never a derivation. `id` is what resolution
    errors and `weft_kernel.seam.wrap`'s span both use to say which stage
    failed or ran.

    **Not `weft_kernel.pipeline.StageDeclaration`, and 1.3 reconciles the two.**
    That one is a stage as an author *wrote* it — a bare `use:` name and an
    unvalidated `with:` block; this one is a stage already resolved far enough
    to run, carrying the contract type and the plugin's own config object.
    They are the two ends of resolution, which neither of them performs.
    """

    id: str
    contract: type[object]
    name: str
    config: object = None
    fallback: tuple[str, ...] = ()
    """Plugin names to try, in order, when `name` refuses this position — task 2.28.

    The same list `StageDeclaration.fallback` holds in a document, reaching the runner
    at last. Every entry names a plugin under the *same* `contract`, so composition needs
    no second check: a fallback is substitutable for the primary by construction.

    **A fallback carries no `with:` block, and that is a stated narrowing rather than an
    oversight.** The document grammar has nowhere to put one — `fallback:` is a list of
    bare names — so a fallback runs on its plugin's own defaults (`_build` calls
    `factory(None)`). Widening the grammar is not this task's, and inventing a place for
    the configuration here would put a second spelling of `with:` in the kernel instead of
    in the document that owns it. The cost is real and is not to be papered over
    elsewhere: one plugin in two configurations — the same parser in two modes — is the
    most natural chain there is, and it cannot be expressed at all until the grammar
    carries a configuration. Nothing routes a failed batch into another pipeline either,
    so there is no mechanism standing in for it today.
    """


@dataclass(slots=True)
class _Candidate:
    """One entry in a stage's chain: how to build a plugin, and the instance once built.

    Not frozen, unlike everything else resolution produces, and the mutability is the
    point: `instance` is filled in **at try time**, so a fallback that is never reached is
    never constructed and an uninstantiable one costs nothing while the primary works.
    It is also what `_built_of` reads, so a fallback the chain did reach is flushed like
    any other stage rather than losing whatever it buffered.
    """

    name: str
    distribution: str
    factory: Callable[..., object]
    instance: object | None = None


@dataclass(frozen=True, slots=True)
class _ResolvedStage:
    """One `StageSpec`, checked and instantiated. Built only by `Runner.resolve`."""

    id: str
    contract_name: str
    plugin_name: str
    distribution: str
    instance: object
    chain: tuple[_Candidate, ...] = ()
    """`[primary, *fallbacks]` when this stage declared any, and empty when it did not.

    Empty rather than a one-element chain for a stage with no `fallback:`, so the
    ordinary path through `_invoke_stage` is the one it always was — a combinator
    silently interposed on every stage in the tree would be a change to every pipeline
    in exchange for a uniformity nothing reads.
    """


@dataclass(frozen=True, slots=True)
class RunnablePipeline:
    """A `StageSpec` list after every resolution check in `06` step 6 has passed.

    What `Runner.run` executes. Never constructed directly — see
    `Runner.resolve`. `tenant_id` is the tenant `resolve()` built every
    cached instance for; `run()` checks a `Context` against it — see
    `TenantMismatchError`.

    **Renamed from `ResolvedPipeline` at task 1.3.** `docs/02-extension-model.md`
    §3 → *Derivation* uses "the resolved form" for something else entirely: a
    frozen, printable, diffable **Pydantic model** — no live plugin instance
    anywhere in it — that a pipeline document derives into, built by
    `weft_kernel.resolution.resolve`. This dataclass is the opposite of that
    on purpose: `instance` on every `_ResolvedStage` it carries is a
    constructed plugin object, which is exactly what makes it runnable and
    exactly what makes it unfit to log, diff or compare across two runs — an
    instance carries no `__eq__` a comparison could trust and holds open
    resources a frozen data value must not. Keeping the old name on this
    class once the data-shaped one existed would have made "the resolved
    pipeline" ambiguous between the two in every docstring and every log
    line that used it, so this one takes the name that says what it is:
    the runnable — built by a resolver, held by a `Runner`, run once.
    """

    tenant_id: str
    stages: tuple[_ResolvedStage, ...]


class RunSummary(BaseModel):
    """What a run produced, sized by outcome count — never by a batch's payload.

    See the module docstring, *"`run` returns a `RunSummary`..."*. Every
    field is a count or a tuple of short reason strings, never a produced
    value, so this object's size tracks the number of batches a run saw, not
    the volume of data any one of them carried.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    produced: int = 0
    nothing_to_produce: int = 0
    failed: int = 0
    nothing_to_produce_reasons: tuple[str, ...] = ()
    failed_reasons: tuple[str, ...] = ()


_FlushFn = Callable[[], Awaitable[None]]


class Runner:
    """Resolves an explicit `StageSpec` list once, then runs it batch by batch.

    One `Runner` is expected to live for the process — its instance cache is
    where `Lifetime.PROCESS` stages are actually reused across separate
    `resolve()` calls; a `Runner` rebuilt per call defeats that half of the
    contract.
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry
        self._process_cache: dict[tuple[str, type[object], str, str], object] = {}

    def resolve(self, specs: Sequence[StageSpec], *, tenant_id: str) -> RunnablePipeline:
        """Check plugin existence, `requires`/`provides`, `intact`/`destroys` and composition.

        Raises `UnknownPluginError` (via `Registry.entry`) if a plugin name
        was never registered; `UnmetRequiresError` if a `requires` goes
        unmet; `IntactViolationError` if an `intact` property was already
        destroyed by an earlier stage; or `StageCompositionError` if two
        consecutive stages do not compose — task 1.13: three distinct
        `PipelineResolutionError` subclasses, never one bare class covering
        all three (see that class's own docstring). Nothing here runs a
        stage — see `run`.
        """
        if not specs:
            return RunnablePipeline(tenant_id=tenant_id, stages=())

        _check_composition(specs)

        resolved: list[_ResolvedStage] = []
        provided_models: set[type[ExtModel]] = set()
        destroyed_by: dict[type[Property], str] = {}
        for spec in specs:
            entry = self._registry.entry(spec.contract, spec.name)
            key = (tenant_id, spec.contract, spec.name, _config_hash(spec.config))

            instance = self._process_cache.get(key)
            if instance is None:
                instance = entry.factory(spec.config)
                if _lifetime_of(instance) is Lifetime.PROCESS:
                    self._process_cache[key] = instance

            for required in _requires_of(instance):
                if required not in provided_models:
                    raise UnmetRequiresError(
                        f"stage '{spec.id}' ({spec.contract.__name__}:{spec.name}) requires "
                        f"'{required.__name__}' — namespace '{required.__namespace__}', "
                        f"published by the pack of that name — but no earlier stage in this "
                        f"pipeline provides it.",
                        stages=(spec.id,),
                        distributions=(required.__namespace__,),
                        remedy=(
                            f"add an earlier stage that provides '{required.__name__}', or "
                            f"reorder this StageSpec list so one already does."
                        ),
                    )
            for needed_intact in _intact_of(instance):
                destroyer = destroyed_by.get(needed_intact)
                if destroyer is not None:
                    raise IntactViolationError(
                        f"stage '{spec.id}' ({spec.contract.__name__}:{spec.name}) needs "
                        f"'{needed_intact.__name__}' intact — namespace "
                        f"'{needed_intact.__namespace__}' — but stage '{destroyer}' earlier in "
                        f"this pipeline already destroys it. The only legal positions for "
                        f"'{spec.id}' are before '{destroyer}', never after.",
                        stages=(spec.id, destroyer),
                        remedy=f"move '{spec.id}' to before '{destroyer}', never after.",
                    )
            provided_models.update(_provides_of(instance))
            for destroyed in _destroys_of(instance):
                destroyed_by.setdefault(destroyed, spec.id)

            resolved.append(
                _ResolvedStage(
                    id=spec.id,
                    contract_name=spec.contract.__name__,
                    plugin_name=spec.name,
                    distribution=entry.distribution,
                    instance=instance,
                    chain=self._chain(spec, primary=entry, instance=instance),
                )
            )

        return RunnablePipeline(tenant_id=tenant_id, stages=tuple(resolved))

    def _chain(
        self, spec: StageSpec, *, primary: RegistryEntry, instance: object
    ) -> tuple[_Candidate, ...]:
        """`spec`'s whole chain — `[primary, *fallbacks]` — or empty when it declares none.

        Every fallback name is looked up **now**, so an unregistered one is refused before
        a single batch runs (`UnknownFallbackError`), and none of them is *built* now, so
        the lookup costs a dict read and nothing more. The primary is already constructed
        — `resolve` did it above, under the full `requires`/`intact`/`Lifetime` treatment
        — and is carried in as candidate zero rather than rebuilt.

        **And every fallback is checked to be substitutable, which costs no instance.**
        Task 2.28 shipped this checking existence only, on the stated ground that the four
        declarations are read off a constructed instance; that ground was wrong.
        `weft_kernel.resolution.resolve` reads all four off the *unconstructed* class
        through `unwrap_factory`, and `Registry` reads `destroys` the same way at
        registration — so the check is available for a `getattr` with laziness intact, and
        `FallbackNotSubstitutableError` is what it raises. It has to be made here rather
        than left to the author's claim: every `requires`/`intact` check `resolve` performs
        was answered by the *primary*'s declarations, so a fallback that destroys more or
        provides less runs against checks nobody made — and only on the documents the
        primary could not read.

        What is still not checked is a declaration a plugin computes in `__init__` and
        never states on its class, which reads as empty here. That direction is safe by
        construction: an unstated declaration narrows nothing and fails nothing, it only
        leaves this check with less to compare.
        """
        if not spec.fallback:
            return ()
        expected = _declared_by(unwrap_factory(primary.factory))
        candidates = [
            _Candidate(
                name=spec.name,
                distribution=primary.distribution,
                factory=primary.factory,
                instance=instance,
            )
        ]
        for position, name in enumerate(spec.fallback, start=1):
            try:
                entry = self._registry.entry(spec.contract, name)
            except UnknownPluginError as exc:
                registered = tuple(sorted(self._registry.names_for(spec.contract)))
                options = (
                    ", ".join(f"'{option}'" for option in registered) if registered else "none"
                )
                raise UnknownFallbackError(
                    f"stage '{spec.id}' names '{name}' as fallback {position} of "
                    f"{len(spec.fallback)}, but no distribution registered that name for "
                    f"{spec.contract.__name__}, so this pipeline cannot be run. Names "
                    f"registered for {spec.contract.__name__}: {options}.",
                    valid_options=registered,
                    stages=(spec.id,),
                    remedy=(
                        f"install a distribution that registers '{name}' for "
                        f"{spec.contract.__name__}, or remove '{name}' from stage "
                        f"'{spec.id}'s fallback list."
                    ),
                ) from exc
            differences = _substitutability_differences(
                expected, _declared_by(unwrap_factory(entry.factory))
            )
            if differences:
                raise FallbackNotSubstitutableError(
                    f"stage '{spec.id}' names '{name}' as fallback {position} of "
                    f"{len(spec.fallback)}, but it cannot stand in for '{spec.name}' at that "
                    f"position: it {'; and it '.join(differences)}. Every requires, intact and "
                    f"ordering check this pipeline passed was answered by '{spec.name}'s "
                    f"declarations, and a chain reaching '{name}' would run against checks "
                    f"nobody made.",
                    stages=(spec.id,),
                    distributions=(primary.distribution, entry.distribution),
                    remedy=(
                        f"declare on '{name}' what '{spec.name}' declares — a fallback may "
                        f"demand no more and promise no less than the plugin it replaces — or "
                        f"give '{name}' a stage of its own instead of '{spec.id}'s fallback list."
                    ),
                )
            candidates.append(
                _Candidate(name=name, distribution=entry.distribution, factory=entry.factory)
            )
        return tuple(candidates)

    async def run(
        self, pipeline: RunnablePipeline, batches: AsyncIterator[object], ctx: Context
    ) -> RunSummary:
        """Run every batch through the whole stage list, one batch in flight, `flush()` at the end.

        Raises `TenantMismatchError`, naming both tenants, if `ctx.tenant_id`
        does not match the tenant `pipeline` was resolved for — the instance
        cache is keyed by tenant, so running it for a different one would
        silently reach across that boundary. A batch that any stage answers
        with `NothingToProduce` or `Failed` stops there — the remaining
        stages never see it, and that outcome counts toward the returned
        `RunSummary` without its payload (there is none) or reason being
        retained past that count. `flush()` is called on every resolved
        instance that has one, once, whether this loop finishes normally or
        an exception — `CancelledError` above all — cuts it off mid-batch; a
        flush failure in that second case never displaces the exception
        already propagating, which continues on unmodified. See `_flush_all`.
        """
        _check_tenant(pipeline, ctx, called="run()")

        produced = 0
        nothing_to_produce = 0
        failed = 0
        nothing_to_produce_reasons: list[str] = []
        failed_reasons: list[str] = []
        try:
            async for batch in batches:
                outcome = await self._run_one_batch(pipeline, batch, ctx)
                if isinstance(outcome, Produced):
                    produced += 1
                elif isinstance(outcome, NothingToProduce):
                    nothing_to_produce += 1
                    nothing_to_produce_reasons.append(outcome.reason)
                else:
                    failed += 1
                    failed_reasons.append(outcome.reason)
        except BaseException as exc:
            # An exception already in flight — `CancelledError` above all — must reach the
            # caller untouched. `_flush_all` still runs and every stage still gets its chance,
            # but a flush failure is attached to `exc` rather than raised as `FlushError`,
            # which would otherwise replace `exc` in Python's exception chain. See the module
            # docstring, *"`CancelledError` propagates untouched."*
            await self._flush_all(pipeline, in_flight=exc)
            raise
        else:
            await self._flush_all(pipeline)
        return RunSummary(
            produced=produced,
            nothing_to_produce=nothing_to_produce,
            failed=failed,
            nothing_to_produce_reasons=tuple(nothing_to_produce_reasons),
            failed_reasons=tuple(failed_reasons),
        )

    async def run_once(
        self, pipeline: RunnablePipeline, payload: object, ctx: Context
    ) -> Outcome[object]:
        """Run one payload through the whole stage list and give the caller its outcome back.

        Task **2.4**. `run` above returns a `RunSummary` — counts and reason
        strings, no payload — which is right for ingest, where the result is
        in the store and a batch's payload is nobody's business once it has
        landed. A query path is the opposite shape: exactly one payload, and
        the payload *is* the point. There is no way to get it out of `run`,
        and the alternatives are worse than fifteen lines here — a pack
        re-implementing applicability routing, seam wrapping, tenant checking
        and flush is exactly the four things this module's own docstring says
        not to hand-write, and a mutable box passed in through a `Context`
        field would make the answer a side effect.

        Everything else is `run`'s behaviour unchanged, because it is
        literally the same code: the same tenant check, the same
        `_run_one_batch` walk (so `applies_to`, the seam and fallback chains
        all still apply), and the same `_flush_all` discipline — flushed once
        on the way out, flushed again with the exception in flight when one
        cuts the walk off, `CancelledError` above all, which continues on
        unmodified.
        """
        _check_tenant(pipeline, ctx, called="run_once()")
        try:
            outcome = await self._run_one_batch(pipeline, payload, ctx)
        except BaseException as exc:
            await self._flush_all(pipeline, in_flight=exc)
            raise
        await self._flush_all(pipeline)
        return outcome

    async def _run_one_batch(
        self, pipeline: RunnablePipeline, batch: object, ctx: Context
    ) -> Outcome[object]:
        payload = batch
        for stage in pipeline.stages:
            outcome = await self._run_stage(stage, payload, ctx)
            if not isinstance(outcome, Produced):
                return outcome
            payload = outcome.value
        return Produced(value=payload)

    async def _run_stage(
        self, stage: _ResolvedStage, payload: object, ctx: Context
    ) -> Outcome[object]:
        """One stage's whole contribution to a batch — routed by `applies_to`, task 1.6.

        See the module docstring, *"Applicability is routed here"*. An empty
        `applies_to` (every stage before this task, and most after it) or an
        unroutable payload calls `stage.instance.run` once, exactly as
        before this task existed. A non-empty `applies_to` over a
        `Sequence[Node]` instead calls it once per maximal contiguous run of
        matching nodes — `_segment_by_applicability` — threading every
        non-matching run through untouched, and stops at the first outcome
        that is not `Produced`, exactly the short-circuit `_run_one_batch`
        itself already applies stage to stage.
        """
        applies_to = _applies_to_of(stage.instance)
        if not applies_to or not _is_routable(payload):
            return await self._invoke_stage(stage, payload, ctx)

        items = cast("Sequence[object]", payload)
        produced: list[object] = []
        for matches, segment in _segment_by_applicability(items, applies_to):
            if not matches:
                produced.extend(segment)
                continue
            outcome = await self._invoke_stage(stage, segment, ctx)
            if not isinstance(outcome, Produced):
                return outcome
            produced.extend(cast("Sequence[object]", outcome.value))
        return Produced(value=tuple(produced))

    async def _invoke_stage(
        self, stage: _ResolvedStage, payload: object, ctx: Context
    ) -> Outcome[object]:
        """One call into this stage's position — through its whole chain when it has one.

        A stage that declared no `fallback:` takes the path it always took, unchanged: one
        wrapped call, one span named for the stage id. A stage that declared one hands
        `weft_kernel.fallback.try_in_order` the candidates and lets it decide what
        continues a chain — the runner itself has no opinion on `Outcome` types here, which
        is what keeps the three-outcome rule in one testable place instead of two.
        """
        if not stage.chain:
            return await _wrapped_run(
                stage.instance,
                distribution=stage.distribution,
                contract=stage.contract_name,
                plugin=stage.plugin_name,
                stage=stage.id,
            )(payload, ctx)
        return await try_in_order(
            payload,
            ctx,
            stage=stage.id,
            attempts=[_attempt(stage, candidate) for candidate in stage.chain],
        )

    async def _flush_all(
        self, pipeline: RunnablePipeline, *, in_flight: BaseException | None = None
    ) -> None:
        """Flush every instance a run built, once, regardless of an earlier one's failure.

        Every instance, not every resolved stage: a fallback is constructed at try time,
        so a chain that reached one has an instance resolution never saw. Skipping it here
        would lose whatever it buffered, silently — the exact shape of failure `flush`
        being the runner's rather than a plugin's exists to make impossible. `_built_of`
        is what asks the question, and a fallback that was never reached was never built
        and so has nothing to answer for.

        Each flush runs through `weft_kernel.seam.wrap_flush`, so a failure
        carries the same span and pack/contract/plugin/stage attribution a
        stage's `run()` gets. Every stage is tried — a completed run must
        stay durable even when one stage's flush fails and another (normally
        the store, last in the list) would otherwise never get the chance.

        `in_flight` is the exception already propagating out of `run()`'s
        batch loop, if any. When it is `None` (the ordinary end of a
        successful run), flush failures are collected and raised together,
        once, as a single `FlushError` whose `__cause__` is the first one
        encountered — the caller has nothing else it is already about to
        raise, so `FlushError` is the loudest correct thing to raise. When
        `in_flight` is not `None`, raising here would replace it — Python
        lets an exception raised inside an `except` block's handling
        displace the one being handled — so a flush failure is instead
        attached to `in_flight` as a note and `in_flight` is left to
        propagate exactly as it arrived. This is what keeps a `CancelledError`
        a `CancelledError` even when the cleanup it triggers itself fails; see
        the module docstring, *"`CancelledError` propagates untouched."*
        """
        failures: list[WeftError] = []
        for stage in pipeline.stages:
            for plugin_name, distribution, instance in _built_of(stage):
                flush = _flush_of(instance)
                if flush is None:
                    continue
                wrapped_flush = wrap_flush(
                    flush,
                    distribution=distribution,
                    contract=stage.contract_name,
                    plugin=plugin_name,
                    stage=stage.id,
                )
                try:
                    await wrapped_flush()
                except WeftError as exc:
                    failures.append(exc)

        if not failures:
            return

        failed_stages = ", ".join(f"'{exc.stage}'" for exc in failures)
        message = (
            f"{len(failures)} of {len(pipeline.stages)} stage(s) failed to flush: {failed_stages}."
        )
        if in_flight is not None:
            in_flight.add_note(f"FlushError: {message}")
            return
        raise FlushError(message) from failures[0]


def _wrapped_run(
    instance: object, *, distribution: str, contract: str, plugin: str, stage: str
) -> Callable[[object, Context], Awaitable[Outcome[object]]]:
    """`instance.run`, through the registration seam. The only place this module calls `wrap`."""
    return wrap(
        cast("Stage[object, object]", instance).run,
        distribution=distribution,
        contract=contract,
        plugin=plugin,
        stage=stage,
    )


def _attempt(stage: _ResolvedStage, candidate: _Candidate) -> Attempt[object, object]:
    """One chain candidate as an `Attempt` — built the moment the chain reaches it, never before.

    The span is named `f"{stage.id}:{candidate.name}"` rather than `stage.id`, which is
    what makes *which backend answered* readable off a trace with nothing else to consult:
    a chain of three produces three spans, and their names say which position was being
    filled and by whom.
    """

    async def _run(payload: object, ctx: Context) -> Outcome[object]:
        if candidate.instance is None:
            candidate.instance = _build(stage, candidate)
        return await _wrapped_run(
            candidate.instance,
            distribution=candidate.distribution,
            contract=stage.contract_name,
            plugin=candidate.name,
            stage=f"{stage.id}:{candidate.name}",
        )(payload, ctx)

    return Attempt(name=candidate.name, run=_run)


def _build(stage: _ResolvedStage, candidate: _Candidate) -> object:
    """Construct `candidate`, turning a construction failure into an attributed `WeftError`.

    `weft_kernel.seam.wrap` covers a plugin's `run`, and construction happens outside it —
    so without this, a fallback whose factory raises escapes as a bare `TypeError` naming
    neither the pack nor the stage, and it does so only on the inputs the primary could not
    read. Raising `WeftError` instead puts it where `try_in_order` records it, which means
    a chain that ends with an unbuildable last candidate reports *"could not be built"*
    beside every other candidate's reason rather than replacing them with a traceback.

    `except Exception` is the same deliberate breadth `seam.wrap` declares for the same
    reason: a factory is third-party code, nothing is swallowed, and `__cause__` keeps the
    traceback. `CancelledError` is a `BaseException` and passes through untouched.
    """
    label = f"{stage.id}:{candidate.name}"
    try:
        # `fallback:` carries no `with:` block — see `StageSpec.fallback` — so a fallback
        # is built on its plugin's own defaults, the same call an unconfigured stage gets.
        return candidate.factory(None)
    except Exception as exc:
        raise WeftError(
            f"'{label}' could not be built: {exc}",
            pack=candidate.distribution,
            contract=stage.contract_name,
            plugin=candidate.name,
            stage=label,
        ) from exc


def _built_of(stage: _ResolvedStage) -> tuple[tuple[str, str, object], ...]:
    """Every `(plugin_name, distribution, instance)` this stage actually built.

    The primary always; a fallback only once a chain reached it, which is precisely when
    it can have buffered anything worth flushing. `stage.chain[1:]` rather than the whole
    chain because candidate zero *is* `stage.instance` — including it twice would flush
    the primary twice, and `flush` is documented idempotent rather than free.
    """
    return (
        (stage.plugin_name, stage.distribution, stage.instance),
        *(
            (candidate.name, candidate.distribution, candidate.instance)
            for candidate in stage.chain[1:]
            if candidate.instance is not None
        ),
    )


def _check_tenant(pipeline: RunnablePipeline, ctx: Context, *, called: str) -> None:
    """Refuse a `Context` for a tenant `pipeline` was not resolved for. One place, two callers.

    Extracted from `run` when `run_once` arrived (task 2.4). The instance cache is keyed
    by tenant, so an entry point that forgot this check would silently reach across the
    boundary the key exists to draw — and the failure would look like a data leak rather
    than like a missing guard. `called` names the entry point in the message because
    which one was used is the first thing a reader wants and the traceback is the last
    place they should have to find it.
    """
    if ctx.tenant_id != pipeline.tenant_id:
        raise TenantMismatchError(
            f"this pipeline was resolved for tenant '{pipeline.tenant_id}', but {called} "
            f"was given a Context for tenant '{ctx.tenant_id}'. An instance cached for "
            f"one tenant must never run for another."
        )


def _stage_signature(contract: type[object]) -> tuple[object, object]:
    """The `(In, Out)` `contract` declared via `Stage[In, Out]` as one of its own bases."""
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


def _check_composition(specs: Sequence[StageSpec]) -> None:
    """Every consecutive pair of `specs` composes: one stage's `Out` is the next stage's `In`."""
    previous: tuple[str, object] | None = None
    for spec in specs:
        payload_type, produced_type = _stage_signature(spec.contract)
        if previous is not None:
            previous_id, previous_produced = previous
            if previous_produced != payload_type:
                raise StageCompositionError(
                    f"stage '{spec.id}' ({spec.contract.__name__}:{spec.name}) expects "
                    f"{payload_type!r}, but the previous stage '{previous_id}' produces "
                    f"{previous_produced!r}. Consecutive stages must compose by type.",
                    stages=(previous_id, spec.id),
                    remedy=(
                        f"reorder this StageSpec list so '{previous_id}' precedes a stage "
                        f"expecting {previous_produced!r}, or so '{spec.id}' follows one "
                        f"producing {payload_type!r}."
                    ),
                )
        previous = (spec.id, produced_type)


def _config_hash(config: object) -> str:
    """A stable digest of `config`, for the instance cache key.

    A content hash rather than `config` itself: the cache key must be
    hashable even when `config` is a Pydantic model carrying an unhashable
    field (a plain `dict`, say), which `frozen=True` alone does not fix.
    """
    payload = config.model_dump_json() if isinstance(config, BaseModel) else repr(config)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lifetime_of(instance: object) -> Lifetime:
    return cast(Lifetime, getattr(instance, "lifetime", Lifetime.RUN))


def _requires_of(instance: object) -> tuple[type[ExtModel], ...]:
    return cast("tuple[type[ExtModel], ...]", getattr(instance, "requires", ()))


def _provides_of(instance: object) -> tuple[type[ExtModel], ...]:
    return cast("tuple[type[ExtModel], ...]", getattr(instance, "provides", ()))


def _applies_to_of(instance: object) -> tuple[Applies, ...]:
    """`instance.applies_to`, read defensively — task 1.6, on `_requires_of`'s own footing.

    An empty default means every node satisfies it vacuously — `02` §3: "A
    stage that declares no `applies_to` applies to everything." Nothing
    refuses a plugin that never mentions it, unlike `destroys`: applicability
    narrows a stage's own reach, so forgetting it costs nothing to a
    stranger's pipeline the way forgetting `destroys` would.
    """
    return cast("tuple[Applies, ...]", getattr(instance, "applies_to", ()))


def _is_routable(payload: object) -> bool:
    """Whether `payload` is shaped like a batch of nodes `applies_to` could filter.

    A repair, not part of the original task 1.6 lift: this used to read
    `isinstance(payload, Sequence) and not isinstance(payload, str | bytes)`,
    which checks only the *container*. A `Sequence[SourceDoc]` — an
    extractor's own payload type — satisfies that check exactly as well as a
    `Sequence[Node]` does, so a stage that declared `applies_to` over a
    non-node payload was not falling back to the unfiltered call this
    docstring promises; it was falling into `_segment_by_applicability`
    instead, where `isinstance(item, Node)` marks every one of its items
    non-matching. The whole payload came back unchanged — the stage's `run`
    was never invoked at all — which is silent by construction: nothing
    records that `applies_to` was ignored, and the first symptom shows up as
    an `AttributeError` inside whatever stage runs next.

    So this now also confirms the *elements*, not only the container: a
    `Sequence`, excluding `str`/`bytes` (both satisfy `Sequence[object]`
    structurally, but iterating either one apart is never what a pipeline
    author meant by "a batch of nodes"), that is both non-empty and holds
    only `Node`s. An **empty** sequence is deliberately excluded too — with
    it included, a non-empty `applies_to` over zero items would segment into
    nothing and hand back `Produced(value=())` without ever calling the
    stage, the exact silently-empty `Produced` every contract docstring in
    this tree forbids; excluded, an empty batch instead takes the unfiltered
    path below and lets the stage answer for itself, the same
    `NothingToProduce` guard every shipped `Cleaner`/`Chunker` already opens
    its own `run` with. Anything else that fails this check (a `Query`, an
    `Answer`, a `Sequence[SourceDoc]`, an ordinary `str` a `str`-shaped stage
    happens to receive) is not a routable node-level payload, so `_run_stage`
    calls the stage once, unfiltered, exactly as an empty `applies_to`
    already does — applicability has nothing to route without nodes to
    route.
    """
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes):
        return False
    items = cast("Sequence[object]", payload)
    return len(items) > 0 and all(isinstance(item, Node) for item in items)


def _segment_by_applicability(
    items: Sequence[object], applies_to: tuple[Applies, ...]
) -> list[tuple[bool, list[object]]]:
    """`items` split into its maximal contiguous runs of "every `Applies` matches".

    See the module docstring, *"Applicability is routed here"*, for why a
    run rather than one filtered call: a chunker's output is not shape-
    preserving, so the only way to know where an untouched node belongs once
    the matching nodes around it have been transformed is to never let them
    separate from their neighbours before the call happens. A node not
    matching *every* `Applies` in the tuple — the tuple is a conjunction,
    the same reading `requires` already gives a stage's own tuple of models
    — starts (or extends) a non-matching run instead; an item that is not
    even a `Node` (a payload `_is_routable` let through structurally, that
    nonetheless holds something with no `ext` to carry a fact at all) is
    treated the identical way — not matching, failing to the safe side
    exactly as an absent fact does.
    """
    segments: list[tuple[bool, list[object]]] = []
    for item in items:
        matches = isinstance(item, Node) and all(applies.matches(item) for applies in applies_to)
        if segments and segments[-1][0] == matches:
            segments[-1][1].append(item)
        else:
            segments.append((matches, [item]))
    return segments


@dataclass(frozen=True, slots=True)
class _Declarations:
    """The four facts one plugin states about its place in a pipeline, as sets.

    Sets rather than the declared tuples because the only question asked of them is
    membership — see `_substitutability_differences` — and order carries no meaning in
    any of the four.
    """

    requires: frozenset[type[ExtModel]]
    provides: frozenset[type[ExtModel]]
    intact: frozenset[type[Property]]
    destroys: frozenset[type[Property]]


def _declared_by(target: object) -> _Declarations:
    """The four declarations, read off an unconstructed plugin class.

    `target` is what `weft_kernel.registry.unwrap_factory` returns — the class itself,
    with any `functools.partial` binding pack settings peeled away, since `partial` does
    not proxy attribute access. Reading a class is what keeps a fallback unbuilt until
    the chain reaches it; it is also exactly what `weft_kernel.resolution.resolve` does
    for a pipeline document, so the two resolvers judge the same declarations.
    """
    return _Declarations(
        requires=frozenset(_requires_of(target)),
        provides=frozenset(_provides_of(target)),
        intact=frozenset(_intact_of(target)),
        destroys=frozenset(_destroys_of(target)),
    )


def _substitutability_differences(
    primary: _Declarations, fallback: _Declarations
) -> tuple[str, ...]:
    """Every way `fallback` demands more or promises less than `primary`. Empty means it fits.

    One direction only, and that asymmetry is the point: a fallback providing an extra
    model or destroying one property fewer invalidates no check `Runner.resolve` already
    made against the primary, so it is not refused. See
    `FallbackNotSubstitutableError`.
    """
    differences: list[str] = []
    if extra_requires := fallback.requires - primary.requires:
        differences.append(f"requires {_named(extra_requires)}, which the primary does not")
    if extra_intact := fallback.intact - primary.intact:
        differences.append(f"needs {_named(extra_intact)} intact, which the primary does not")
    if missing_provides := primary.provides - fallback.provides:
        differences.append(
            f"declares no {_named(missing_provides)}, which the primary provides to every "
            f"stage after it"
        )
    if extra_destroys := fallback.destroys - primary.destroys:
        differences.append(f"destroys {_named(extra_destroys)}, which the primary does not")
    return tuple(differences)


def _named(types: frozenset[type[ExtModel]] | frozenset[type[Property]]) -> str:
    """A stable, readable list of type names for a refusal's message."""
    return ", ".join(
        f"'{declared.__name__}'" for declared in sorted(types, key=lambda t: t.__name__)
    )


def _intact_of(instance: object) -> tuple[type[Property], ...]:
    """`instance.intact`, read defensively — an optional convention, never enforced at registration.

    `02` §3: "`intact` stays an optional convention." Unlike `destroys`,
    nothing refuses a plugin that never mentions it — the cost of forgetting
    `intact` lands on the forgetful stage itself, the moment it needs a
    property some earlier stage already destroyed, so there is nothing here
    to guard against beyond the check `resolve` already performs with what
    this returns.
    """
    return cast("tuple[type[Property], ...]", getattr(instance, "intact", ()))


def _destroys_of(instance: object) -> tuple[type[Property], ...]:
    """`instance.destroys`, read defensively — mandatory *at registration* for a governed contract.

    Reading it the same defensive way `_requires_of`/`_provides_of` do is
    still correct here even though `weft_kernel.registry` already refused an
    ungoverned-contract plugin that omits `destroys`: an ungoverned
    contract's plugin is never required to declare it at all, and this
    function is the one place both cases have to be read uniformly.
    """
    return cast("tuple[type[Property], ...]", getattr(instance, "destroys", ()))


def _flush_of(instance: object) -> _FlushFn | None:
    """`instance.flush`, if it has one and it is callable — never a bare `TypeError` later.

    An attribute merely named `flush` that is not callable (a plain value, an
    author's typo) is treated the same as no `flush` at all: `flush` is
    documented as an optional method, not a required, checked-elsewhere one.
    """
    found = getattr(instance, "flush", None)
    if found is None or not callable(found):
        return None
    return cast(_FlushFn, found)
