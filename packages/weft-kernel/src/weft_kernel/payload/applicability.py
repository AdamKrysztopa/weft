"""`Applies` — what a stage operates on, declared as data. Task 1.6, extended by 9.2.

Settled in G2, `docs/02-extension-model.md` §3 → *Applicability*: "A stage
declares what it operates on; the runner routes everything else past it,
untouched." That makes applicability a mechanism the kernel enforces itself
rather than a rule every stage's author has to remember and apply by hand.
`docs/11-multimodal.md` §2's own worked example is
the ingest-path illustration: "An atomic node passes the chunker unsplit,
and the chunker does not have to know that."

**Why a predicate cannot be a callable.** A callable can be *run*; it cannot
be *printed*, checked at registration, or diffed between two resolutions of
the same pipeline — exactly the complaint `weft_kernel.pipeline`'s own
module docstring raises against a second construction path, one level down:
a predicate a plugin author hands the kernel as a function is a second,
unauditable grammar sitting next to the one `02` §3 already made data. So
`Applies` is a frozen `pydantic.BaseModel` the kernel publishes, exactly the
footing `weft_kernel.payload.property.Property` gives `intact`/`destroys` —
data a plugin's `applies_to` tuple carries, evaluated by whoever runs the
pipeline, never executed by the plugin itself.

**What a fact is.** `Applies` wraps an `ExtModel` *subclass* — a namespaced
fact a node may or may not carry, on the same footing `requires`/`provides`
already give ext models. `Applies(Language)` matches any node carrying that
fact at all; `Applies(Language, code="pl")` narrows to nodes whose `Language`
additionally has `code == "pl"`. There is no other spelling: matching is
always "this fact is present" or "this fact is present *and* these fields
equal these values" — never "this fact is absent", because the safe-side
reading below already gives absence a meaning, and giving it two would make
one of them redundant with the other.

**Keyword names are checked against the fact's own fields, immediately.**
`Applies(Language, code="pl")` validates `code` against `Language.model_fields`
the moment it is constructed — which, for the way every real plugin uses
this (a class-level `applies_to = (Applies(Language, code="pl"),)` tuple,
evaluated when the plugin's module is imported for registration), *is*
"at registration": a typo'd field name fails on the pack's own import, not
silently at the first pipeline that happens to route a node past a stage
that should have claimed it. This is the identical failure class `02` §3
rules out everywhere else — a typo that becomes a stage which silently never
applies is indistinguishable, from the outside, from a stage that correctly
declined every node it saw, and there is no doctor command that can tell
those apart after the fact. Refusing it before the mistake can be observed
is the only fix; a `TypeError`, not a `WeftError` — this is a plugin
author's own class body failing to construct, the same footing
`ExtModel.__pydantic_init_subclass__` and `Property.__init_subclass__`
already refuse a missing `__namespace__` on, neither of which is a
`PipelineResolutionError` either: nothing about a pipeline document is
involved yet.

**Absence fails to the safe side.** `02` §3 → *Language, and what a var is
for*: "unknown language flows past" a language-specific stage — a fact this
module's own `matches` makes literal. A stage that declares `applies_to`
narrows itself to nodes it can positively confirm it should touch; every
node it cannot confirm — the fact missing entirely, or present with a
different value — passes it by. There is no third state and no negation:
a chunker that wants to leave a table node alone does not declare
"not `Atomic`" (which this module does not let it spell), it declares what
it *does* want — the prose fact its own splitting logic actually depends on
— and a table simply never carries that. This is the whole mechanism behind
"the chunker does not have to know that" tables exist: the declaration
names the chunker's own requirement, in the chunker's own vocabulary, and
routing a stranger's `Atomic`-marked node past it is a byproduct of that
requirement never being met, not a rule about tables the chunker's author
had to think of and add.

**A media-type constraint, task 9.2's addition.** `media_type` is already a core `Node`
field — G5's admission rule, `node.py`'s own module docstring — rather than a namespaced
fact, so it cannot be spelled as `Applies(SomeFact, ...)`; there is no `ExtModel` to narrow.
`Applies(media_type=MediaType.TEXT)` claims a node of that type; `Applies(media_type=
(MediaType.TEXT, MediaType.IMAGE))` claims any node whose type is one of those listed —
the "any of these" reading lives *inside* one `Applies`, never across two, because a node
has exactly one media type and two media-type `Applies` in one (conjunctive) tuple would
jointly match nothing. `Applies(SomeFact, media_type=...)` is refused with a `ValueError` naming
`media_type`: one `Applies` states one kind of constraint, and a fact constraint (narrows
an `ExtModel` a node may carry) and a media-type constraint (narrows a field every node
already has) are two different conjunction rules that a single object cannot mean at once.
`Applies()` claiming neither is refused for the same reason it matters here at all — a
constraint that matches nothing is a stage that silently never runs.

**Vars never participate.** Nothing here reads `weft_kernel.pipeline`'s
`vars:` block, and nothing could: `applies_to` is a class-level declaration
a plugin's own module carries, never a field a pipeline document writes, so
there is no `${var:NAME}` token for `weft_kernel.resolution`'s substitution
to ever reach. `02` §3: "A var can say translate into English; it can never
say pretend this document is English" — enforced here not by a check but by
there being no document-authored surface for a var to land on in the first
place.

**A stage that declares no `applies_to` applies to everything, silently.**
Read defensively — `getattr(instance, "applies_to", ())` — the identical
convention `weft_kernel.runner` already uses for `requires`/`provides`/
`intact`/`destroys`. An empty tuple is not a special case the seam checks
for; it is simply zero constraints to fail, so every node satisfies it
vacuously. This is what keeps every stage written before this task — none
of which declares `applies_to` at all — running exactly as it did.
"""

import sys
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer

from weft_kernel.payload.ext import ExtModel
from weft_kernel.payload.media_type import MediaType
from weft_kernel.payload.node import Node


def _fact_to_ref(fact: type[ExtModel]) -> str:
    """`module:QualName` — enough to find the class again, and nothing more."""
    return f"{fact.__module__}:{fact.__qualname__}"


def _fact_from_ref(value: object) -> object:
    """A persisted `module:QualName` back into the class, **without importing anything**.

    The pack that declares a fact was imported at discovery if it is installed at all, so a
    reference this cannot resolve means the pack is *gone* — and that is a refusal, not an import.
    Resolving by importing whatever a persisted file names would turn a JSON artefact into an
    instruction to execute code, which is a much larger promise than reading a run record needs.
    """
    if not isinstance(value, str):
        return value
    module_name, _, qualname = value.partition(":")
    if not qualname:
        raise ValueError(
            f"{value!r} is not a fact reference. Expected 'module:QualName' — a fact written by a "
            f"version of Weft before this form was introduced cannot be read, and the record "
            f"carrying it should be deleted."
        )
    module = sys.modules.get(module_name)
    if module is None:
        raise ValueError(
            f"no installed pack has imported '{module_name}', so the fact '{qualname}' this record "
            f"was written against cannot be resolved. Install the distribution that provides it, "
            f"or delete the record. Nothing is imported to answer this — a persisted name is data."
        )
    resolved: object = module
    for part in qualname.split("."):
        resolved = getattr(resolved, part, None)
        if resolved is None:
            raise ValueError(
                f"'{module_name}' no longer declares '{qualname}'. The pack is installed and this "
                f"fact has been renamed or removed since the record was written."
            )
    return resolved


type _FactRef = Annotated[
    type[ExtModel],
    PlainSerializer(_fact_to_ref, return_type=str, when_used="json"),
    BeforeValidator(_fact_from_ref),
]
"""`Applies.fact` in a document: the class in memory, `module:QualName` once dumped to JSON.

pydantic has no serializer at all for an arbitrary `type`, so `model_dump(mode='json')` on a
`ResolvedStage.applies_to` would otherwise raise outright rather than merely print something ugly.

**It used to dump the bare `__name__` and had no validator, which made it write-only** — found at
Phase 8's close review by running the binary. The serialising half worked from the day it was
written, so nothing ever failed while records were being created; the failure arrived later and
somewhere else, in three commands that merely *read* the directory those records live in. A bare
name is also not enough to find a class again, which is why the form changed rather than only
gaining a validator: two packs may each declare a `Language`, and the record has to say whose.
"""


class _Unset:
    """The absence of an authored `fact`, distinguishable from every value one could hold."""

    __slots__ = ()


_UNSET = _Unset()


class Applies(BaseModel):
    """One constraint a stage's `applies_to` tuple carries: a fact, optionally narrowed.

    See the module docstring for the reasoning; this class carries only the
    shape and the one check that has to happen at construction, before a
    typo can ship as a stage that silently never runs.
    """

    model_config = ConfigDict(frozen=True)

    fact: _FactRef | None = None
    constraints: tuple[tuple[str, object], ...] = ()
    media_type: tuple[MediaType, ...] = ()
    """The media types this constraint claims, its own typed field rather than an entry in
    `constraints` — which is `tuple[tuple[str, object], ...]` because a *fact's* narrowed values
    are arbitrary, and `object` is exactly the annotation that makes pydantic hand a persisted
    `"text"` back as the string `"text"`. A constraint that dumps correctly and reads back as
    something `matches` compares false against is write-only, which is the defect `_FactRef`'s
    docstring above records this module already paying for once: it "worked from the day it was
    written, so nothing ever failed while records were being created", and surfaced later in three
    commands that merely read. Typed here, pydantic validates the round trip rather than this
    module hoping for it.
    """

    def __init__(
        self,
        fact: type[ExtModel] | _Unset = _UNSET,
        /,
        *,
        media_type: MediaType | tuple[MediaType, ...] | _Unset = _UNSET,
        **field_values: object,
    ) -> None:
        """Authored as `Applies(Language, code="pl")` **or** `Applies(media_type=...)`,
        and **rebuilt from JSON as well**.

        `fact` is positional-only so that a fact model declaring its own `fact` field is still
        narrowable, and that is exactly what broke reading one back: pydantic validates a persisted
        `{"fact": "Language", "constraints": [["code", "pl"]]}` by calling `__init__(**data)`, where
        a positional-only parameter cannot be reached — so `fact` and `constraints` both landed in
        `field_values`, `fact` was never supplied, and `model_validate` raised
        *"missing 1 required positional argument: 'fact'"*.

        **The writing half always worked, which is why nothing failed for a phase.** Found at Phase
        8's close review by running the binary, not by the suite: `index-polish` declares
        `applies_to = (Applies(Language, code="pl"),)`, so one `weft eval run` of it wrote a run
        record that nothing could read afterwards — and `weft_cli.commands._participating_stores`
        loads every record for `weft index`, `weft reconcile` **and** `weft delete`, so a single
        opaque JSON file stopped all three in that project with no hint which file. `L6.14` says a
        read method with no writer answers emptily; this is the reverse, and the reverse is worse,
        because the artefact persists and the failure surfaces somewhere else entirely.

        The unset sentinel is what lets one `__init__` serve every caller: `fact` and `media_type`
        both absent means pydantic is rebuilding and `field_values` already holds the model's own
        fields (`fact`, `constraints`); `fact` given with `media_type` given too is the one
        combination task 9.2 refuses outright, one `Applies` stating two conjunction rules at once.
        """
        if not isinstance(fact, _Unset) and not isinstance(media_type, _Unset):
            raise ValueError(
                f"Applies({fact.__name__}, media_type=...) is not allowed: a fact constraint "
                f"narrows an ExtModel a node may carry, and media_type narrows a field every "
                f"node already has. One Applies states one kind of constraint — declare two "
                f"separate stages, or drop whichever constraint this stage does not need."
            )
        if isinstance(fact, _Unset):
            if "fact" in field_values:
                if not isinstance(media_type, _Unset):
                    field_values["media_type"] = media_type
                super().__init__(**field_values)
                return
            if isinstance(media_type, _Unset):
                raise TypeError(
                    "Applies() states no constraint at all. Pass a fact to narrow "
                    "(Applies(Language, code='pl')) or a media type to claim "
                    "(Applies(media_type=MediaType.TEXT)); an Applies claiming nothing would "
                    "match no node and say nothing about why."
                )
            if field_values:
                unexpected = ", ".join(sorted(field_values))
                raise TypeError(
                    f"Applies(media_type=...) accepts no keyword but media_type; got "
                    f"{unexpected}. A media-type constraint narrows a field every node has, "
                    f"with nothing left to name."
                )
            claimed = (media_type,) if isinstance(media_type, MediaType) else tuple(media_type)
            super().__init__(fact=None, media_type=claimed)
            return
        unknown = sorted(set(field_values) - set(fact.model_fields))
        if unknown:
            valid = ", ".join(sorted(fact.model_fields)) or "(no fields)"
            raise TypeError(
                f"Applies({fact.__name__}, {', '.join(f'{key}=...' for key in unknown)}) named "
                f"field(s) {fact.__name__} does not have. {fact.__name__} declares: {valid}."
            )
        super().__init__(fact=fact, constraints=tuple(sorted(field_values.items())))

    def matches(self, node: Node) -> bool:
        """Whether `node` satisfies this constraint — a fact, or a media type, never both.

        `fact is None` means this `Applies` was built from `media_type=...`, and `media_type`
        is checked directly against `node.media_type` — a core field every node has, so there
        is no absence case to fail to the safe side of, unlike a fact.

        Otherwise, `node.ext_as(self.fact)` returning `None` is an ordinary absence — "the
        stage does not apply", the safe-side reading the module docstring describes — never
        treated as an error here, unlike a namespace collision, which `ext_as` itself already
        raises on and this method makes no attempt to catch.
        """
        if self.fact is None:
            return node.media_type in self.media_type
        value = node.ext_as(self.fact)
        if value is None:
            return False
        return all(getattr(value, name) == expected for name, expected in self.constraints)

    def __repr__(self) -> str:
        if self.fact is None:
            types = ", ".join(claimed.value for claimed in self.media_type)
            return f"Applies(media_type=({types}))"
        if not self.constraints:
            return f"Applies({self.fact.__name__})"
        fields = ", ".join(f"{name}={value!r}" for name, value in self.constraints)
        return f"Applies({self.fact.__name__}, {fields})"
