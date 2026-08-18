"""`Property` — a namespaced marker for a fact about a stage's payload that ordering cares about.

Settled in G2, `docs/02-extension-model.md` §3 → *Ordering constraints —
`intact` and `destroys`*: G5's `requires`/`provides` solve ordering by **data
dependency** — a stage that reads what an earlier one produced — and that
cannot express a constraint that exists for the opposite reason: hyphenation
repair must run before whitespace normalization not because anything reads
its output, but because whitespace normalization is **destructive** to a fact
no dependency graph can see. `intact`/`destroys` are the mirror G2 added, and
this is what they carry: "The representation is the mirror of `requires` /
`provides`... The properties are published by whichever pack publishes the
contract — namespaced marker classes exactly as G5 gives ext models their
namespaces."

**Never instantiated, and never a `Node`'s data.** `weft_kernel.runner.Stage`'s
`requires`/`provides` already demonstrate the shape ordering borrows: an
`ExtModel` *subclass* is a tag a stage's tuple carries, never an instance the
stage constructs. `intact`/`destroys` need that same tagging shape, but not
an `ExtModel`'s own machinery — a property is not payload data a `Node`
carries, is never written, validated or persisted, and gets no `ext`
namespace of its own — so it gets a lightweight base rather than reusing
`ExtModel` for a job it was never shaped for.

**`__namespace__` is mandatory, and enforced the same way `ExtModel`
enforces it** — at class definition, via `__init_subclass__`, never at first
use — for the identical reason: "no plugin ever names another plugin." A
hyphenation fixer's `intact = (WordBoundaries,)` and a whitespace
normalizer's `destroys = (WordBoundaries,)` compare by **type identity**,
never by a string either side had to agree on — see
`weft_kernel.runner.Runner.resolve`, which is what actually walks a stage
list accumulating what earlier stages destroyed. The namespace is what stops
two unrelated packs from silently colliding on the same class name and
having their unrelated properties compare as equal by accident; it plays no
role in the comparison itself, exactly as `ExtModel.__namespace__` plays no
role in `requires`/`provides` matching by model type.
"""

from typing import ClassVar


class Property:
    """Base for a namespaced marker declaring a fact about a stage's payload.

    A subclass carries no fields and is never instantiated — see the module
    docstring. `intact`/`destroys` on a plugin class name `Property`
    subclasses exactly the way `requires`/`provides` name `ExtModel`
    subclasses: the type itself is the whole payload, so two packs can
    publish their own properties with no coordination and no shared registry
    of names.
    """

    __namespace__: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.__namespace__:
            raise TypeError(
                f"{cls.__name__} must declare a non-empty __namespace__ — the "
                f"distribution name that owns this property"
            )
