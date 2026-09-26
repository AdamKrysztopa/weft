"""A leaf selection evaluated in Python, for tests of the leaf filter (R43.22, 43.47).

The evaluator reads an extension path the way the stores do: `EXISTS` holds when the path
reaches a value that is not `None`, and a namespace's `__schema_version__` is a value every
stored namespace carries.
"""

from typing import ClassVar

from weft_kernel.payload import ExtModel, MediaType, Node, SourceId
from weft_store.contract import Filter, FilterOp
from weft_store.fields import FieldKind, field_for
from weft_store.rehydrate import ext_models, register_ext_model


class DeclaredNotALeaf(ExtModel):
    __namespace__ = "test-r4322-declared"
    __schema_version__ = "1"
    not_a_leaf: ClassVar[bool] = True
    note: str


class Undeclared(ExtModel):
    __namespace__ = "test-r4322-undeclared"
    __schema_version__ = "1"
    note: str


def ensure_registered(*models: type[ExtModel]) -> None:
    held = ext_models.names_for(ExtModel)
    for model in models:
        if model.__namespace__ not in held:
            register_ext_model(model)


def selects(node: Node, filter: Filter) -> bool:
    if filter.op is FilterOp.AND:
        return all(selects(node, clause) for clause in filter.clauses)
    if filter.op is FilterOp.OR:
        return any(selects(node, clause) for clause in filter.clauses)
    if filter.op is FilterOp.NOT:
        return not selects(node, filter.clauses[0])
    return selects_field(node, filter)


def selects_field(node: Node, filter: Filter) -> bool:
    path = field_for(filter.op, filter.field or "")
    if filter.op is FilterOp.IN and path.kind is FieldKind.TEXT_SET:
        wanted = filter.value if isinstance(filter.value, tuple) else (filter.value,)
        return bool({str(source) for source in node.lineage.sources} & {str(v) for v in wanted})
    if filter.op is FilterOp.EXISTS and path.kind is FieldKind.EXTENSION:
        value: object = node.ext.get(path.namespace)
        for key in path.keys:
            value = None if value is None else getattr(value, key, None)
        return value is not None
    raise AssertionError(f"the layer selection used an operator this evaluator lacks: {filter}")


SOURCE = SourceId("file:///corpus/curie.md")


def chunk_node() -> Node:
    return Node.synthetic(
        content="Marie Curie discovered polonium in Paris.",
        media_type=MediaType.TEXT,
        reason="R43.22 fixture chunk",
        sources=frozenset({SOURCE}),
    )
