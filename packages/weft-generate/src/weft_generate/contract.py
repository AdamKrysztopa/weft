"""The `Generator` contract — published here, never by the kernel.

Task **2.4**. One `Stage` subtype, closing the query path: `Stage[Passages, Answer]`,
domain types on both sides, and the last seam `weft_kernel.runner._check_composition`
checks before a run produces something a reader sees.

**Why this is a separate distribution from `weft-retrieve`.** G3 settled that discovery is
*eager* — installed means `register()` runs on every registry-touching command — so a
retrieval-only deployment (rerank-and-return enterprise search) must be able to *not
install* a generator, its prompts and its citation machinery rather than merely not name
them. `Answer` is also the only Phase 2 type an embedding host application consumes, and
a host that wants it should not thereby acquire every retrieval technique this project
ships.

`Passages` and `Query` come from `weft-retrieve`, which this pack depends on: dependencies
flow one way along the pipeline and never back. See `weft_generate.payload`'s module
docstring for why `Answer` is published *here* even though a retrieval-shaped technique
wants it.

The emptiness rule, the `applies_to` note and the `publishes_property_vocabulary`
declining argument in `weft_retrieve.contract`'s module docstring all apply verbatim to
this contract; they are stated there once rather than copied.
"""

from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.payload import Outcome
from weft_kernel.runner import Stage
from weft_retrieve.payload import Passages

#: Fitness function 6's subject for this contract — see the module docstring.
GENERATE_CONTRACT_VERSION = "1.0.0"


@runtime_checkable
class Generator(Stage[Passages, Answer], Protocol):
    """Turns packed, labelled evidence into an answer that cites it.

    Taking `Passages` rather than a `Ranking` is what makes task 2.9 mechanical: the
    citation labels are already assigned and final by the time a generator sees them, so
    `Answer`'s own validator can refuse a marker that resolves to nothing. A generator
    that decides the evidence does not answer the question returns
    `Answer(stance=NOT_IN_CORPUS)` — `Produced`, with an honest claim inside it — never
    `NothingToProduce`, which would stop the pipeline and leave the caller with no answer
    at all where `09` §4's V2 requires one.
    """

    if TYPE_CHECKING:
        #: Declared only for a type checker, assigned for real after the class body, so it
        #: never joins `__protocol_attrs__`.
        version: ClassVar[str]

    async def run(self, payload: Passages, ctx: Context) -> Outcome[Answer]: ...


Generator.version = GENERATE_CONTRACT_VERSION
