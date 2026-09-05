"""`Representation` — the fact an `Expander`-derived node carries about itself.

Namespaced extension data, per `docs/02-extension-model.md` section 1: everything a pack
wants to attach to a `Node` beyond its six core fields is a declared `ExtModel` subclass,
read and written through `Node.ext_as`/`Node.with_ext`, never a bare dict key. `technique`
is the plugin name (registered under `weft_index.contract.Expander`) that built this node —
`weft_kernel.payload.node.SyntheticOrigin`'s own precedent for "explicit, greppable,
doctor-reportable" applied here: a future `weft plugins doctor` sweep can enumerate every
derived representation in a corpus and say which technique produced it, the same way it can
already enumerate every synthetic root.

Not transient: this fact is kept through storage and retrieval, on purpose. It is also read
outside this pack — structurally, never by importing it — by `weft_generate.cited_answer`,
to resolve a citation past a representation to the one node it stands in for rather than
attributing a claim to a question or a rephrasing nobody wrote as a passage. See that
module's `weft_generate.representation` for the duck-typed read and why it replaces an
import, the same precedent `weft_generate.page.page_for` already set for a chunk's offset.
"""

from weft_kernel.payload import ExtModel


class Representation(ExtModel):
    """Marks a node as an `Expander`-derived stand-in for the one parent it was built from.

    Only meaningful together with exactly one `Lineage.parents` entry — the shape
    `Node.derive` always produces. A node `Node.combine` built from several members (a
    cluster summary) has no single "the" parent to stand in for and is cited as itself, on
    purpose: `weft_generate.representation`'s reader checks the parent count before ever
    trusting this marker, rather than this model trying to declare a rule it cannot enforce
    on its own.
    """

    __namespace__ = "weft-index"
    __schema_version__ = "1.0.0"

    #: The `Expander` plugin name that generated this node — `weft_index.hypothetical_
    #: questions.NAME` for this task's own registration.
    technique: str
