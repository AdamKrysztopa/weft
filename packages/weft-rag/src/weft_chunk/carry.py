"""`carry_forward` — a derived node keeps every fact its parent's `ext` carried.

Lifted out of `weft_chunk.fixed_size` (where it was `_carry_forward`, private) by ledger
task `9.14`, because `weft_chunk.table_rows.TableRowChunker` needs the identical shape for
a second caller: a table row is `Node.derive`d from its table exactly the way a fixed-size
window is `Node.derive`d from whatever it is chunking, and `derive` drops `ext` on purpose
in both cases — "later stages attach their own." A fact a pack attached to the whole
node — `weft_pdf.PdfPages`, a future heading map — is still a fact about a piece derived
from it, and this is the one place that fact would otherwise be lost. Two private copies of
this function would have been the same drift risk `weft_extract.table_text.row_text`'s own
docstring names for two renderers of one row: one gets fixed, the other does not.
"""

from weft_kernel.payload import Node, SyntheticOrigin


def carry_forward(child: Node, *, parent: Node) -> Node:
    """`child`, plus every namespace `parent.ext` carries except its root-origin marker.

    `SyntheticOrigin` is excluded by name: it states that a node has no real lineage, and
    `child` was just given one — by `Node.derive`, whichever stage called this — so copying
    it forward would attach a claim about `child` that is false the moment it is read.
    Every other namespace is copied verbatim, last-write-wins is never a concern here since
    `child` carries no `ext` of its own yet (`derive` starts it empty); a caller that wants
    its own fact to win over a carried-forward one — `weft_chunk.table_rows` does, for its
    row's own `TableGrid` — attaches it with `with_ext` *after* calling this.
    """
    for namespace, model in parent.ext.items():
        if namespace == SyntheticOrigin.__namespace__:
            continue
        child = child.with_ext(model)
    return child


__all__: list[str] = ["carry_forward"]
