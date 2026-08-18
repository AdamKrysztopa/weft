"""`Applies` — what a stage operates on, declared as data. Task 1.6.

Settled in G2, `docs/02-extension-model.md` §3 → *Applicability*: "A stage
declares what it operates on; the runner routes everything else past it,
untouched. This is the reference's stage 0 as a mechanism instead of a rule an
author must remember." `docs/11-multimodal.md` §2's own worked example is
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

from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

from weft_kernel.payload.ext import ExtModel
from weft_kernel.payload.node import Node

type _FactRef = Annotated[
    type[ExtModel], PlainSerializer(lambda fact: fact.__name__, return_type=str, when_used="json")
]
"""`Applies.fact` in a document: the class in memory, its bare name once dumped to JSON.

The same shape `weft_kernel.resolution.StageConfig` already gives a validated
config object — pydantic knows how to write a plain string back into a
document and has no serializer at all for an arbitrary `type`, so
`model_dump(mode='json')` on a `ResolvedStage.applies_to` would otherwise
raise outright rather than merely print something ugly.
"""


class Applies(BaseModel):
    """One constraint a stage's `applies_to` tuple carries: a fact, optionally narrowed.

    See the module docstring for the reasoning; this class carries only the
    shape and the one check that has to happen at construction, before a
    typo can ship as a stage that silently never runs.
    """

    model_config = ConfigDict(frozen=True)

    fact: _FactRef
    constraints: tuple[tuple[str, object], ...] = ()

    def __init__(self, fact: type[ExtModel], /, **field_values: object) -> None:
        unknown = sorted(set(field_values) - set(fact.model_fields))
        if unknown:
            valid = ", ".join(sorted(fact.model_fields)) or "(no fields)"
            raise TypeError(
                f"Applies({fact.__name__}, {', '.join(f'{key}=...' for key in unknown)}) named "
                f"field(s) {fact.__name__} does not have. {fact.__name__} declares: {valid}."
            )
        super().__init__(fact=fact, constraints=tuple(sorted(field_values.items())))

    def matches(self, node: Node) -> bool:
        """Whether `node` carries `fact` — and, if narrowed, every named field equals it.

        `node.ext_as(self.fact)` returning `None` is an ordinary absence —
        "the stage does not apply", the safe-side reading the module
        docstring describes — never treated as an error here, unlike a
        namespace collision, which `ext_as` itself already raises on and
        this method makes no attempt to catch.
        """
        value = node.ext_as(self.fact)
        if value is None:
            return False
        return all(getattr(value, name) == expected for name, expected in self.constraints)

    def __repr__(self) -> str:
        if not self.constraints:
            return f"Applies({self.fact.__name__})"
        fields = ", ".join(f"{name}={value!r}" for name, value in self.constraints)
        return f"Applies({self.fact.__name__}, {fields})"
