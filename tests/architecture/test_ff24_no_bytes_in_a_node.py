"""Fitness function **24** — bytes never enter a node. Ledger task 9.5.

`01` → *Fitness functions this phase turns on* carries the argument; this file is the check, and
filing it mints the number: 22 went to task 9.0 and 23 to task 9.2, both on 2026-09-06, so 24 is the
first free one. The plan named a `test_ff22_...` path for this check while 9.0 was already filing a
different check under that number — `docs/lessons.md` `L9.44` — which is why `01` now writes
`test_ff<NN>_` until a file exists.

**The property, in two clauses, each able to fail alone.**

*(a)* No `ExtModel` anywhere in `packages/`, `testing/` or `examples/` declares a field that can
hold raw bytes — `bytes`, `bytearray` or `memoryview`.

*(b)* No first-party `Extractor` answers `Produced` with a `Node.content` that is a base64
rendering of the bytes it was handed. **Clause (a) structurally cannot see this**, and that is why
there are two: base64 of a megabyte of pixels is a `str`, so it satisfies every type this file
checks and lands in the same JSONB column by a different door. `11` §1's account of the
anti-pattern names the encoded form, not the Python type — *"a multi-MB base64 blob reaching
JSONB"* — and `tests/unit/weft_kernel/payload/test_node.py:37 'class _Tr'` already carries a fixture
called
`_TransientBlob` whose field is `payload_b64: str`, which is the shape drawn from life. The honest
answer for an input an extractor cannot read is `Failed` or `NothingToProduce`, never the input
back in another alphabet.

**Why a fitness function and not a review note.** `__transient__` exists because a decode buffer in
`ext` would be written into a JSONB column (`02` §1 → *The payload model*). After task `9.4` bytes
leave the payload through `BlobStore` and only a non-transient `BlobRef` remains, so an ext model
that grows a bytes field is not a small convenience — it is the reintroduction of the transport
`__transient__` never was, and the strip that used to be a backstop no longer covers it. Nothing
in a green gate would say so: the model would validate, serialise (pydantic base64-encodes `bytes`
into JSON quite happily), and grow a corpus's worth of pixels inside the node store one row at a
time.

**Read off pydantic's own core schema, never off `field.metadata` or an annotation string.**
`test_ff19_persisted_models_round_trip.py`'s `_customises_writing_without_reading` records what the
other two cost: `field.metadata` is **empty** for a field annotated through a PEP 695 alias, so a
check reading it passed on the exact model it was written for and kept passing when the thing it
looked for was deleted (`docs/lessons.md` `L5.19`, `L8.25`). A source-text sweep has the mirror
problem — an alias, a `TypeAlias`, or `Annotated[bytes, ...]` behind a name declared in another
module all read as innocent. The core schema is what pydantic itself will use to validate, so it is
the only account of a field's type that cannot disagree with the runtime.

**Clause (b) lives here rather than in a conformance kit, and `01` said otherwise.** `01`'s entry
placed it *"as a conformance case in `weft_extract`'s kit"*; measured 2026-09-06, no such kit
exists — `weft_extract` ships `accept`, `contract`, `payload`, `render` and `text`, and the only
conformance kit in the tree is the store's, which lives under `tests/` and is published nowhere.
Inventing a kit module to hold one case would be the heavier half of this task and would ship a
seam with one user; the clause is asserted here, against every `Extractor` the real registry holds,
and `01` is corrected to say so.

**The waiver is pinned empty.** A blob's bytes have a home; nothing else in this tree has a reason
to carry them in a payload.
"""

from __future__ import annotations

import base64
import sys
import typing
from collections.abc import Callable, Sequence
from importlib import import_module
from pathlib import Path
from typing import Final

import pytest
from pydantic import BaseModel, create_model
from pydantic.errors import PydanticSchemaGenerationError

from tests.discovery import discover_for_tests
from weft_extract.contract import Extractor, SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, MediaType, Node, Produced, SourceId

type _OpaqueBytes = bytes
"""A PEP 695 alias over `bytes` — the shape `field.metadata` is empty for, used by the alias plant
below. Module scope because a `type` statement is only legal there."""

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: Every source root a first-party or example pack ships from. `tests/` is deliberately absent: a
#: throwaway `ExtModel` inside a test is a fixture, and one that carries bytes on purpose is how
#: this check's own non-vacuity is proved below.
_SOURCE_ROOTS: Final[tuple[Path, ...]] = (
    REPO_ROOT / "packages",
    REPO_ROOT / "testing",
    REPO_ROOT / "examples",
)

#: The core-schema type names pydantic gives a field that can hold raw bytes.
_BYTES_SCHEMA_TYPES: Final[frozenset[str]] = frozenset({"bytes", "bytearray", "memoryview"})

#: Ext models permitted to carry bytes. **Pinned empty.** Widening this is an argument recorded in
#: `docs/README.md`'s decision log and named here — never a name parked to make a red check green.
EXT_MODELS_CARRYING_BYTES: Final[frozenset[str]] = frozenset()


def _import_every_first_party_package() -> None:
    """Import every shippable package, so `ExtModel.__subclasses__()` has seen them all.

    Imported rather than parsed: a class that exists only after an import is exactly the class a
    source sweep would miss, and this check's whole argument is that the runtime's own account of a
    field is the only trustworthy one.

    An `examples/*` pack is deliberately not a workspace member (fitness function 9(a)), so nothing
    installs it and its `src/` goes on `sys.path` for the length of the import — the identical
    technique `tests/discovery.register_out_of_tree_examples` uses, and the reason that helper
    exists at all. An example pack left out here would leave this check's population one pack short
    while reporting nothing.
    """
    for root in _SOURCE_ROOTS:
        if not root.is_dir():
            continue
        for dist_dir in sorted(root.iterdir()):
            src = dist_dir / "src"
            if not src.is_dir():
                continue
            added = str(src) not in sys.path
            if added:
                sys.path.insert(0, str(src))
            try:
                for package_dir in sorted(src.iterdir()):
                    if (package_dir / "__init__.py").is_file():
                        import_module(package_dir.name)
            finally:
                if added:
                    sys.path.remove(str(src))


def _every_ext_model() -> tuple[type[ExtModel], ...]:
    """Every `ExtModel` subclass a first-party or example package declares.

    Filtered by module rather than taken whole: `__subclasses__()` answers about the *process*, and
    a pytest run has already imported test modules that declare their own throwaway subclasses.
    Including those would make the check's population depend on collection order.
    """
    _import_every_first_party_package()
    shipped: dict[str, type[ExtModel]] = {}
    stack: list[type[ExtModel]] = list(ExtModel.__subclasses__())
    while stack:
        model = stack.pop()
        stack.extend(model.__subclasses__())
        if model.__module__.split(".")[0] in _SHIPPED_PACKAGES:
            shipped[f"{model.__module__}.{model.__qualname__}"] = model
    return tuple(model for _, model in sorted(shipped.items()))


def _shipped_packages() -> frozenset[str]:
    found: set[str] = set()
    for root in _SOURCE_ROOTS:
        if not root.is_dir():
            continue
        for dist_dir in sorted(root.iterdir()):
            src = dist_dir / "src"
            if src.is_dir():
                found |= {p.name for p in src.iterdir() if (p / "__init__.py").is_file()}
    return frozenset(found)


_SHIPPED_PACKAGES: Final[frozenset[str]] = _shipped_packages()


def _bytes_fields(model: type[BaseModel]) -> tuple[str, ...]:
    """Every field of `model` whose core schema can hold raw bytes, by name.

    Walks the schema pydantic itself validates against, so an alias, an `Annotated[...]`, a
    `NewType` and a plain annotation all answer identically — which is the whole point, and the
    thing `field.metadata` and a source sweep each get wrong in their own direction.
    """
    schema = typing.cast("object", model.__pydantic_core_schema__)
    found: list[str] = []
    for name, field_schema in _fields_of(schema).items():
        if _holds_bytes(field_schema):
            found.append(str(name))
    return tuple(sorted(found))


def _fields_of(schema: object) -> dict[str, object]:
    """The `fields` mapping of the first model-fields node in `schema`."""
    if isinstance(schema, dict):
        mapping = typing.cast("dict[str, object]", schema)
        if mapping.get("type") == "model-fields":
            return typing.cast("dict[str, object]", mapping.get("fields", {}))
        for value in mapping.values():
            found = _fields_of(value)
            if found:
                return found
    if isinstance(schema, (list, tuple)):
        for value in typing.cast("Sequence[object]", schema):
            found = _fields_of(value)
            if found:
                return found
    return {}


def _holds_bytes(schema: object) -> bool:
    """Whether any node reachable in `schema` is one of pydantic's bytes-shaped types."""
    if isinstance(schema, dict):
        mapping = typing.cast("dict[str, object]", schema)
        if mapping.get("type") in _BYTES_SCHEMA_TYPES:
            return True
        return any(_holds_bytes(value) for value in list(mapping.values()))
    if isinstance(schema, (list, tuple)):
        return any(_holds_bytes(value) for value in typing.cast("Sequence[object]", schema))
    return False


def test_no_ext_model_can_hold_bytes() -> None:
    # Arrange
    models = _every_ext_model()

    # Act
    offenders = {
        f"{model.__module__}.{model.__qualname__}": _bytes_fields(model)
        for model in models
        if _bytes_fields(model) and model.__qualname__ not in EXT_MODELS_CARRYING_BYTES
    }

    # Assert
    assert not offenders, (
        f"these ext models declare a field that can hold raw bytes: {offenders}. Bytes leave the "
        f"payload through `BlobStore` and only a `BlobRef` comes back (`02` §1 → The payload "
        f"model, task 9.4) — a bytes field here writes them into the node store's own column "
        f"instead, one row at a time, and `__transient__` no longer covers it."
    )


def test_the_waiver_is_empty() -> None:
    # Arrange / Act / Assert — a ratchet, so widening it shows up in a diff.
    assert frozenset() == EXT_MODELS_CARRYING_BYTES


def test_the_sweep_finds_the_ext_models_this_tree_actually_ships() -> None:
    """Non-vacuity: a population of zero would satisfy the check above and mean nothing.

    Named across three distributions and two source roots, because they arrive by different
    mechanisms — a workspace package, an add-on distribution, and an out-of-tree example — and any
    one of the three could break alone.
    """
    # Arrange / Act
    found = {f"{model.__module__}.{model.__qualname__}" for model in _every_ext_model()}

    # Assert
    assert {
        "weft_blob.payload.BlobRef",
        "weft_chunk.payload.ChunkOffset",
        "weft_pdf.document.PdfPages",
    } <= found, f"the sweep found {sorted(found)}"


def test_a_planted_bytes_field_would_be_caught() -> None:
    """The disagreement the check exists to find, planted deliberately."""

    # Arrange
    class _CarriesBytes(BaseModel):
        payload: bytes

    # Act / Assert
    assert _bytes_fields(_CarriesBytes) == ("payload",)


@pytest.mark.parametrize("annotation", [bytearray, memoryview])
def test_the_other_two_spellings_cannot_be_declared_at_all(annotation: type) -> None:
    """`01`'s statement of this property names `bytes`, `bytearray` and `memoryview`. Only the
    first is reachable, and this is where that is written down rather than assumed.

    pydantic refuses to build a core schema for the other two — `PydanticSchemaGenerationError`,
    *"Unable to generate pydantic-core schema"* — so a field annotated with either fails at class
    definition, before this check or any other could see it. That makes them unrepresentable rather
    than unchecked, which is a stronger guarantee than the sweep gives for `bytes`; `_BYTES_SCHEMA_
    TYPES` still names all three so that a pydantic release adding support does not open the hole
    silently. Measured 2026-09-06 against pydantic 2.13, not read off its documentation.
    """
    # Act / Assert
    with pytest.raises(PydanticSchemaGenerationError):
        create_model("_CannotExist", payload=(annotation, ...))


def test_a_bytes_field_behind_an_alias_is_still_caught() -> None:
    """The case `field.metadata` gets wrong, and the reason this reads the core schema.

    `L5.19` and `L8.25` are the same failure twice: a check that looked at annotation metadata was
    blind to a field annotated through an alias, and read as green about the one model it existed
    for.
    """

    # Arrange
    class _CarriesBytesBehindAnAlias(BaseModel):
        payload: _OpaqueBytes

    # Act / Assert
    assert _bytes_fields(_CarriesBytesBehindAnAlias) == ("payload",)


def test_a_model_carrying_no_bytes_is_not_reported() -> None:
    """The contrast: a detector that answered `True` for everything would also pass the plants."""

    # Arrange
    class _CarriesNoBytes(BaseModel):
        text: str
        count: int

    # Act / Assert
    assert _bytes_fields(_CarriesNoBytes) == ()


# --- clause (b): no extractor answers with its own input in another alphabet -------------------


def _first_party_extractors() -> tuple[tuple[str, object], ...]:
    """Every `Extractor` the real registry holds, by plugin name.

    The registry `weft plugins doctor` builds, never a hand-written list: an extractor added
    tomorrow is covered here without an edit, which is the difference between a check and an
    inventory (`docs/lessons.md` `L5.14`).
    """
    registry = discover_for_tests()
    return tuple(
        (name, registry.entry(Extractor, name).factory)
        for name in sorted(registry.names_for(Extractor))
    )


async def test_no_first_party_extractor_answers_with_its_input_in_base64() -> None:
    """Clause (b). Every extractor is handed bytes no parser can read, and must refuse.

    The input is deliberately not a broken PDF or a malformed anything — it is bytes with no
    format at all, which is the case an author reaches for a fallback on. What must not happen is
    a `Produced` whose content contains the input re-encoded: that answer looks like success to
    every caller, embeds as noise, and fills a JSONB column with pixels one row at a time.

    `async def` rather than `asyncio.run`, because fitness function 7 permits exactly one
    `asyncio.run` in the tree and it is `weft-cli`'s entry point — caught by that check on this
    file's first full gate run, which is the check doing its job.
    """
    # Arrange
    raw = bytes(range(256)) * 8
    encoded = base64.b64encode(raw).decode("ascii")
    doc = SourceDoc(source_id=SourceId("s-1"), uri="mem://unreadable.bin", content=raw)
    ctx = Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")

    # Act
    offenders: dict[str, str] = {}
    for name, factory in _first_party_extractors():
        outcome = await _run_extractor(factory, doc, ctx)
        if not isinstance(outcome, Produced):
            continue
        produced = typing.cast("Produced[Sequence[Node]]", outcome)
        for node in produced.value:
            if encoded[:64] in node.content:
                offenders[name] = node.content[:80]

    # Assert
    assert not offenders, (
        f"these extractors answered `Produced` with their own input re-encoded: {offenders}. "
        f"Base64 of an unreadable input is not an extraction — it is the input, in an alphabet "
        f"that survives a `str` field and lands in the node store. `Failed` or `NothingToProduce` "
        f"is the honest answer (`02` §1 → the `Outcome` rule)."
    )


async def _run_extractor(factory: object, doc: SourceDoc, ctx: Context) -> object:
    """Build and run one extractor, treating a raise as a refusal rather than a failure here.

    An extractor that raises on unreadable bytes has not produced base64, which is all this clause
    asks. Whether raising is the right refusal is `02` §1's `Outcome` rule and another test's.
    """
    built = typing.cast("Callable[[object], object]", factory)(None)
    runnable = typing.cast("Extractor", built)
    try:
        return await runnable.run([doc], ctx)
    except Exception:  # noqa: BLE001 — a raise is not a base64 answer; see the docstring
        return None


def test_the_extractor_sweep_finds_the_ones_this_tree_ships() -> None:
    """Non-vacuity for clause (b): zero extractors would satisfy it and mean nothing."""
    # Act
    found = {name for name, _ in _first_party_extractors()}

    # Assert
    assert {"text", "pdf-text", "pdf-layout"} <= found, f"the sweep found {sorted(found)}"


def test_an_extractor_that_base64s_its_input_would_be_caught() -> None:
    """The plant for clause (b), against the same comparison the check makes.

    Written as the comparison rather than by registering a bad extractor into the real registry,
    which would need a pack: what is being proved is that the detector separates an honest answer
    from the input in another alphabet.
    """
    # Arrange
    raw = bytes(range(256)) * 8
    encoded = base64.b64encode(raw).decode("ascii")
    dishonest = Node.synthetic(content=encoded, reason="planted", media_type=MediaType.TEXT)
    honest = Node.synthetic(content="a real paragraph", reason="planted", media_type=MediaType.TEXT)

    # Act / Assert
    assert encoded[:64] in dishonest.content
    assert encoded[:64] not in honest.content
