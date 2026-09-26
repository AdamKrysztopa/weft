"""What a leaf is, over a whole store — ledger task **43.47**.

A leaf is a node no `Expander` derived (`Representation` carries no `technique` on it) and that
carries no extension model declaring `not_a_leaf = True` (R43.22). The layer loop reads a batch's
leaves through this filter narrowed to the batch's sources (`weft_cli.layers.layer_leaf_filter`);
`whole-corpus` reads every leaf of a store through it. It lives here, beside `Representation`,
because a `weft_retrieve` plugin may import `weft_index` and may not import `weft_cli`.
"""

from weft_index.payload import Representation
from weft_kernel.payload import SCHEMA_VERSION_KEY, ExtModel
from weft_store.contract import Filter, FilterOp
from weft_store.rehydrate import ext_models


def not_a_leaf_namespaces() -> tuple[str, ...]:
    """Every registered ext model namespace whose class declares `not_a_leaf`.

    Read with `getattr`, as `_is_layer_stage` reads `layer_stage`, so nothing here names a
    pack's model (FF28).
    """
    namespaces: list[str] = []
    for namespace in sorted(ext_models.names_for(ExtModel)):
        registrant = ext_models.lookup(ExtModel, namespace)
        if not (isinstance(registrant, type) and issubclass(registrant, ExtModel)):
            continue
        if getattr(registrant, "not_a_leaf", False) is True:
            namespaces.append(namespace)
    return tuple(namespaces)


def leaf_clauses() -> tuple[Filter, ...]:
    """The conditions a leaf meets, each a `NOT(EXISTS ...)`; there is always at least one.

    `NOT(EXISTS ext.weft-index.technique)` leaves out every node an `Expander` derived, and each
    registered namespace declaring `not_a_leaf` leaves out the nodes carrying it. Every stored
    namespace carries `__schema_version__`, which is what that `EXISTS` reads.
    """
    return (
        Filter(
            op=FilterOp.NOT,
            clauses=(
                Filter(op=FilterOp.EXISTS, field=f"ext.{Representation.__namespace__}.technique"),
            ),
        ),
        *(
            Filter(
                op=FilterOp.NOT,
                clauses=(
                    Filter(op=FilterOp.EXISTS, field=f"ext.{namespace}.{SCHEMA_VERSION_KEY}"),
                ),
            )
            for namespace in not_a_leaf_namespaces()
        ),
    )


def leaf_filter() -> Filter:
    """Every leaf of a store, whatever its source.

    One condition stands alone: `Filter` refuses an `AND` of fewer than two clauses, and an
    install where no model declares `not_a_leaf` has only the technique condition.
    """
    clauses = leaf_clauses()
    return clauses[0] if len(clauses) == 1 else Filter(op=FilterOp.AND, clauses=clauses)
