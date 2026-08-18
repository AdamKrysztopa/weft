"""The pipeline as data — the authored document, published by the kernel.

Settled in G2 and specified in `docs/02-extension-model.md` §3 → *One model,
two directions*: "The pipeline **is** a frozen Pydantic model published by the
kernel. YAML is a serialisation of it; Python code constructs the same model
directly. That is 'both' with one implementation — one validator, one error
set, one resolved form, no builder DSL and therefore no second grammar to keep
in step."

**Two directions, one model, and no third way in.** `Pipeline.model_validate`
takes the mapping a YAML loader hands back; `Pipeline(...)` takes the same
thing as arguments. There is no builder, no `PipelineBuilder.add_stage()`, no
`from_yaml` classmethod — a second construction path is a second grammar, and
a second grammar is a place for the two to disagree about what a pipeline is.
For the same reason **the kernel parses no YAML**: G1 fixes its dependencies at
`pydantic` and `opentelemetry-api`, so whoever opens the file brings the loader
and hands a mapping in, exactly as `weft-cli` already does for `weft.toml`.

**The error set is `pydantic.ValidationError`, deliberately, and it is not
`PipelineResolutionError`.** `02` §3 → *When resolution fails* gives every
resolution failure its own `WeftError` subclass carrying the pipeline, the
stage ids, the distributions in conflict and the remedy. None of that exists
yet at this point: a document that will not validate has no resolved parent, no
registry lookup and no distributions to name — it is malformed text, not a
pipeline that could not be resolved. Keeping the two apart is what stops the
resolution family from becoming the place every failure is filed, which is the
shape `02` §3 rules out for the failure-mode ratchet's sake.

**Loud is still required of it.** `extra="forbid"` alone names the key it
refused but never the keys that exist, which fails `01`'s rule that an unknown
name says what the valid options are. `_document_keys_only` runs first and says
both, so a mistyped `steps:` is answered with `stages`.

**What this module deliberately does not carry.** The declarations behind ordering
constraints (task 1.2 — `intact`/`destroys`) live on a *plugin class*, never on a
document: a pipeline names a plugin, it does not restate what that plugin declares, so
there is nothing of task 1.2's for this module to hold. `extends` and `vars` are here as
*data* — resolution gives them meaning in tasks 1.3 and 1.14 — because they are what `02`
§3's own `base-de.yaml` is made of, and a model that could not hold the specification's
smallest example would not be the model the specification describes.

**Slots — task 1.11, `02` §3 → *Slots*.** `Pipeline.slots` is where the root opens a
named position for a pack's contribution: "a pipeline may contribute into a slot a
pipeline opted into. It may never rewrite a pipeline that did not ask." Declaring one is
the opt-in; `SlotDeclaration.after`/`before` position it against the root's own stages,
on `InsertOperator`'s own terms. What this module refuses, rather than half-reads: a
slot id wearing a pack's qualified spelling (`_refuse_qualified_id`, shared with
`StageDeclaration.id` and `remove`'s own targets), a slot colliding with a stage id or
another slot, and `slots:` alongside `extends` — a slot is a position in *this*
pipeline's own list, so it belongs where `stages:` does. What this module does **not**
do: fill a slot. That needs a registry, a caller's contributions and the resolved chain
`stages:` alone cannot see — `weft_kernel.resolution.resolve` (task 1.11's other half) is
where a slot actually gets a contribution, or is recorded as landing nowhere.

**The four derivation operators — task 1.4, `02` §3 → the operator table.**
`insert`, `replace`, `remove` and `set` are **four keyed blocks**, exactly as
`02` §3's `specific.yaml` prints them, never flattened into one tagged
sequence: a document says `insert:` and `remove:` as its own top-level keys,
and a model that instead carried one `operators: list[Operator]` field would
have to invent a discriminator the specification never asks an author to
write, purely to get back to the shape already on the page.

**Four separate fields cannot, by themselves, say what order they apply in.**
`02` §3: "Operators apply in written order" — and a `remove` undoing an
`insert` at the same id, or the reverse, are different pipelines with
different resolved forms. A pydantic model's *field* order is fixed once for
every document — declaration order, not the order a particular author's
mapping happened to list keys in — so if application order were read off
field order, one of *remove-then-insert* and *insert-then-remove* would be
permanently unwritable no matter which order the four fields were declared
in. Application order is therefore read from the *document* (or the *call*),
not assumed from the schema: `_operator_order` is a private attribute filled
by `_track_operator_order`, a `mode="wrap"` validator that inspects the raw
mapping's key order before delegating to ordinary field validation, and
`operator_order` is its public, read-only face — `weft_kernel.resolution`
reads it to decide which block to apply first. `Pipeline(remove=..., insert=
...)` gets the identical treatment: Python's own keyword-argument evaluation
already preserves call order into the `**data` dict `BaseModel.__init__`
builds, which is the same dict a document's loader hands to
`model_validate`, so there is exactly one code path computing "the order",
not one per direction. This is what task 1.4 settles from the note 1.1 left
open in `docs/build-ledger.md`.

**`fallback` is data here too.** `02` §1 gives the kernel a fallback combinator
over any contract, and `11` §4 keeps `fallback:` a per-stage list "tried in
order until one produces". This module records the list; nothing in it runs.

**Two stage-shaped models now live in the kernel, and 1.3 reconciles them.**
`StageDeclaration` here is a stage as *written* — a bare `use:` name and an
unvalidated `with:` block; `weft_kernel.runner.StageSpec` is a stage as
*resolved enough to run* — a contract type, a plugin name and that plugin's
own config object. They are the two ends of resolution, which is the step
neither of them performs, and the resolved form task 1.3 builds is what turns
one into the other. Until it exists they are deliberately not related by
inheritance or conversion, because a converter written before resolution
exists would have to guess at the contract a bare name belongs to — which is
exactly the lookup resolution does against a registry.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Final, Self, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    PlainSerializer,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic.fields import FieldInfo

type Scalar = str | int | float | bool
"""What a `vars:` value may be. `02` §3: "Scalars only; no var may reference another"."""

_QUALIFIER: Final[str] = ":"
"""What separates a distribution from a stage id in a pack's contribution. `02` §3 → *Slots*."""


def _refuse_qualified_id(value: str, *, subject: str) -> str:
    """Refuse a `:`-qualified spelling wherever an author, not a pack, is naming something.

    Shared by every place task 1.11 draws the same line: a stage id
    (`StageDeclaration.id`), a slot id (`SlotDeclaration.id`), and a `remove` target
    (`Pipeline._remove_targets_are_not_a_packs_to_name`). All three read the identical
    reserved spelling `weft-graph:entities` and refuse it for the identical reason — the
    qualifier belongs to a pack's contribution, never to anything an author writes,
    including the string an author writes to *remove* one. `subject` only changes the
    message's noun, never the check.
    """
    if _QUALIFIER in value:
        raise ValueError(
            f"{subject} '{value}' contains '{_QUALIFIER}', which is reserved: a pack's "
            f"contribution into a slot is qualified by its distribution name "
            f"(weft-graph{_QUALIFIER}entities) so that it can never collide with anything "
            f"you write. Name this {subject} without it."
        )
    return value


type ConfigBlock = Annotated[
    Mapping[str, object], PlainSerializer(dict, return_type=dict[str, object], when_used="always")
]
"""A `with:` block: read-only in memory (see `_read_only`), a plain mapping in a document."""

type VarBlock = Annotated[
    Mapping[str, Scalar], PlainSerializer(dict, return_type=dict[str, Scalar], when_used="always")
]
"""A `vars:` block, on the same terms as `ConfigBlock`."""

_NO_CONFIG: Final[Mapping[str, object]] = MappingProxyType({})
_NO_VARS: Final[Mapping[str, Scalar]] = MappingProxyType({})
"""The empty blocks, shared rather than built per instance — safe precisely because `_read_only`
makes every mapping on these models un-writable, so there is nothing an instance could do to a
shared default. It is also what keeps `model_dump(exclude_defaults=True)` able to recognise an
untouched block and leave it out of the document it writes back."""


class StageDeclaration(BaseModel):
    """One stage as written in a pipeline document: a position, a plugin name, its configuration.

    `use` is a **bare** plugin name, which G3 settled and `02` §2 records:
    "Pipelines select plugins by bare name (§3 — `use: docling`)". It is not
    qualified by contract or by distribution, and a collision between two packs
    claiming it is refused at registration and pinned in `weft.toml` — never
    disambiguated here, because that would put operator policy in a document
    that has to stay portable between machines.

    `config` is spelled `with` in the document and `config` in Python, which is
    the one place the two directions cannot use the same word: `with` is a
    Python keyword, so a field literally named for it could never be passed by
    a Python caller at all. It is a `validation_alias`/`serialization_alias`
    pair rather than a plain `alias` for exactly that reason — a plain `alias`
    is what a type checker reads as the constructor's parameter name, and it
    would report every `StageDeclaration(config=...)` call as an error while
    offering a keyword in its place. `populate_by_name` accepts either
    spelling, and `model_dump(by_alias=True)` writes the document's back.

    **That has a cost worth naming in a module whose thesis is "no second
    grammar": a document writing `config:` validates too.** `populate_by_name`
    cannot tell a YAML mapping from a Python call — both arrive here as a
    mapping — so accepting `config` for the Python direction accepts it for
    the document as well, and a document that used it would be written back as
    `with:`. The alternative is worse: refusing the field name would make the
    Python direction unwritable, since `with=` is a syntax error. `with` is the
    spelling this module names, teaches and writes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: str = Field(min_length=1)
    use: str = Field(min_length=1)
    config: ConfigBlock = Field(
        default_factory=lambda: _NO_CONFIG,
        validation_alias="with",
        serialization_alias="with",
    )
    fallback: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _stage_keys_only(cls, value: object) -> object:
        return _known_keys_only(cls, value, subject="stage")

    @field_validator("id", mode="after")
    @classmethod
    def _id_is_not_a_pack_s_to_give(cls, value: str) -> str:
        """`weft-graph:entities` is a contributed id, and an author may not write one.

        `02` §3 → *Slots*: a contributed stage id "is qualified by
        distribution (`weft-graph:entities`) so they cannot collide with the
        author's". Nothing makes that true unless the qualified spelling is
        reserved — an author free to use it could collide with a pack that is
        not installed yet, and the collision would arrive with the
        installation rather than with the edit that caused it. This is an
        invariant that holds with no registry present, which is what puts it
        in the authored form rather than in slot filling.
        """
        return _refuse_qualified_id(value, subject="stage id")

    @field_validator("config", mode="after")
    @classmethod
    def _config_is_read_only(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _read_only(value)


PIPELINE_OPERATOR_MARK: Final[str] = "pipeline_operator"
"""The `json_schema_extra` key task 1.15's ratchet reads off `Pipeline.model_fields`.

`tests/architecture/test_ff11_pipeline_integrity.py` pins the closed operator set as a
ratchet, and `01` -> *Fitness functions* item 11(a) requires its "actual" side to be
"derived from the code (the actual operator fields on the model), never a hand-written
list" — a second tuple of the same four strings, sitting in the test file with no
structural link back to this class, is exactly the drift `docs/README.md` opens by
describing. Each of the four operator fields below carries `Field(...,
json_schema_extra={PIPELINE_OPERATOR_MARK: True})` for exactly that reason: it is the
one place in the tree that *decides* a field is an operator block, so the ratchet reads
`Pipeline.model_fields` itself rather than retyping the decision. `_OPERATOR_KEYS`
immediately below is the first reader of that mark, not a second one — see its own
docstring.
"""


def _operator_key_order(value: object) -> tuple[str, ...]:
    """Which of `_OPERATOR_KEYS` a document (or call) wrote, in the order it wrote them.

    Reads the **raw** value `Pipeline` was handed — a `Mapping` for both a YAML loader's
    result and a Python call's `**kwargs`, per the module docstring — before any field
    validation reorders or drops anything. A `Pipeline` passed back in (pydantic re-
    validating an already-built instance, e.g. through a nested model) carries its own
    `operator_order` forward instead of losing it to a fresh, order-blind read of `dict(
    instance)`. Anything else — a mapping missing entirely, or garbage that later
    validation will refuse anyway — resolves to no operators written, which is exactly
    what an empty `_OPERATOR_KEYS` intersection already means.
    """
    if isinstance(value, Pipeline):
        return value.operator_order
    if isinstance(value, Mapping):
        written = cast("Mapping[object, object]", value)
        return tuple(str(key) for key in written if str(key) in _OPERATOR_KEYS)
    return ()


def _reorder_operator_keys(dumped: dict[str, object], order: tuple[str, ...]) -> dict[str, object]:
    """Rewrite `dumped`'s operator keys into `order`, everything else exactly where it was.

    Pydantic's default serializer walks fields in **declaration** order — `insert` before
    `replace` before `remove` before `set`, always — which is precisely the field-order
    assumption the module docstring rules out for *reading* a document, and round-
    tripping would silently reintroduce it on the way back out: a document that wrote
    `remove:` above `insert:` would serialise with `insert:` first, indistinguishable from
    a document that never made that choice. This runs after `handler(self)` has already
    applied `by_alias`/`exclude_defaults`/`mode`, so it only ever reorders keys that
    survived those — an operator block excluded by `exclude_defaults=True` because it was
    never written is not reinserted here either. Non-operator keys keep their original
    relative order and position; the four operator keys, wherever they were, are emitted
    together at the position the first of them held, in `order`.
    """
    present = [key for key in order if key in dumped]
    if not present:
        return dumped
    reordered: dict[str, object] = {}
    operators_placed = False
    for key, value in dumped.items():
        if key in _OPERATOR_KEYS:
            if not operators_placed:
                for operator_key in present:
                    reordered[operator_key] = dumped[operator_key]
                operators_placed = True
            continue
        reordered[key] = value
    return reordered


class SlotDeclaration(BaseModel):
    """A named position the root opens for a pack to fill — `02` §3 → *Slots*.

    "A pack may ship complete named pipelines, and it may contribute into a slot a
    pipeline opted into. It may never rewrite a pipeline that did not ask." A slot is that
    opt-in, made data: declaring one is choosing, deliberately, that some installed pack's
    contribution may land at this exact position — never a stage id, which `replace` and
    `remove` already exist to change, and never ambient just because a pack happens to be
    on the machine. `after`/`before` position it against one of the pipeline's own stages,
    on the identical terms `InsertOperator` already gives a newly inserted stage — the
    validator below is that one's twin for exactly that reason, not a coincidence of
    shape.

    `id` is checked against the same reserved-qualifier rule `StageDeclaration.id` already
    carries: a slot is the *author's* name for a position, so the qualified spelling a
    pack's contribution wears (`weft-graph:entities`) can never be it — the two vocabularies
    (an author's slot names, a pack's contributed ids) must never collide, or a document
    could accidentally "declare" a slot that is actually the ghost of some other pack's
    contribution.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    after: str | None = None
    before: str | None = None

    @field_validator("id", mode="after")
    @classmethod
    def _id_is_the_authors_not_a_packs(cls, value: str) -> str:
        return _refuse_qualified_id(value, subject="slot")

    @model_validator(mode="after")
    def _exactly_one_position(self) -> Self:
        if (self.after is None) == (self.before is None):
            got = "neither" if self.after is None else "both 'after' and 'before'"
            raise ValueError(
                f"slot '{self.id}' names {got}. A slot names exactly one existing stage id "
                f"to position against — 'after:' or 'before:', never both, never neither."
            )
        return self


class InsertOperator(BaseModel):
    """One `insert:` entry — `02` §3's operator table: add `stage`, `after:` or `before:` an id.

    Exactly one of `after`/`before` is required, never both and never neither: a
    position with two anchors or none is not a position, and refusing it here — before a
    parent exists to check the anchor against — keeps that check as cheap as
    `StageDeclaration`'s own invariants are.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    after: str | None = None
    before: str | None = None
    stage: StageDeclaration

    @model_validator(mode="after")
    def _exactly_one_position(self) -> Self:
        if (self.after is None) == (self.before is None):
            got = "neither" if self.after is None else "both 'after' and 'before'"
            raise ValueError(
                f"insert operator for stage '{self.stage.id}' names {got}. An insert names "
                f"exactly one existing stage id to position against — 'after:' or 'before:', "
                f"never both, never neither."
            )
        return self


class SetOperator(BaseModel):
    """One `set:` entry — `02` §3's operator table: override `id`'s configuration in place.

    No `use:` field on purpose: `set` is the operator that "override[s] configuration of
    an existing stage **without changing the plugin**" — a document that wants a
    different plugin at that id writes `replace`, and this model refusing `use:` by name
    (`extra="forbid"`) is what makes the distinction a checked one rather than a naming
    convention an author has to remember.

    `config`'s `with`/`config` split is `StageDeclaration.config`'s own, for the same
    reason: `with` is a Python keyword, so `populate_by_name=True` alongside the alias is
    what keeps `SetOperator(config=...)` constructible from Python at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: str = Field(min_length=1)
    config: ConfigBlock = Field(
        default_factory=lambda: _NO_CONFIG,
        validation_alias="with",
        serialization_alias="with",
    )

    @field_validator("config", mode="after")
    @classmethod
    def _config_is_read_only(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _read_only(value)


class Pipeline(BaseModel):
    """A pipeline document as its author wrote it — frozen, checked, not yet resolved.

    This is the *authored* form, distinct from the resolved one: `extends` is
    unfollowed, `vars` are unsubstituted, and no plugin named in `use` has been
    looked up. Everything here can be true of a pipeline whose parent does not
    exist and whose plugins are not installed, which is precisely why
    resolution is a separate step that produces a separate frozen value.

    The document's invariants are the ones that hold without a registry: a
    pipeline is named, its keys are keys this model has, its stage ids are
    unique, and its vars are scalars.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    extends: str | None = None
    vars: VarBlock = Field(default_factory=lambda: _NO_VARS)
    stages: tuple[StageDeclaration, ...] = ()
    slots: tuple[SlotDeclaration, ...] = ()
    insert: tuple[InsertOperator, ...] = Field(
        default=(), json_schema_extra={PIPELINE_OPERATOR_MARK: True}
    )
    replace: tuple[StageDeclaration, ...] = Field(
        default=(), json_schema_extra={PIPELINE_OPERATOR_MARK: True}
    )
    remove: tuple[str, ...] = Field(default=(), json_schema_extra={PIPELINE_OPERATOR_MARK: True})
    set: tuple[SetOperator, ...] = Field(
        default=(), json_schema_extra={PIPELINE_OPERATOR_MARK: True}
    )

    _operator_order: tuple[str, ...] = PrivateAttr(default=())

    @property
    def operator_order(self) -> tuple[str, ...]:
        """Which of `insert`/`replace`/`remove`/`set` this pipeline wrote, in written order.

        See the module docstring's *The four derivation operators* section for why this
        cannot be read off field declaration order. `weft_kernel.resolution` is the one
        caller: it applies this pipeline's operator blocks against its resolved parent in
        exactly this order, which is what makes `remove` written above `insert` a move and
        the reverse a collision — `02` §3, settled by task 1.4.
        """
        return self._operator_order

    @model_validator(mode="wrap")
    @classmethod
    def _track_operator_order(cls, value: object, handler: ModelWrapValidatorHandler[Self]) -> Self:
        """Read operator key order off the raw input, before delegating to field validation.

        `mode="wrap"` is the one validator kind that sees both ends: the value exactly as
        `model_validate`/`__init__` received it, and the constructed instance `handler`
        returns. Every other `model_validator` here only ever sees one side — `mode=
        "before"` transforms the raw value onward but builds nothing, `mode="after"` gets
        the built instance but never the mapping that built it — so key order, which only
        the raw value carries, would already be gone by the time any of them ran. Stamped
        onto `_operator_order` through an ordinary attribute assignment, not `object.
        __setattr__`: `BaseModel.__setattr__` already special-cases a declared private
        attribute so the write lands in `__pydantic_private__` (where equality and
        serialization actually look), and `frozen=True` never enters into it either way —
        a private attribute is not a field, so it sits outside the rebinding check that
        blocks `pipeline.name = ...`. `object.__setattr__` would instead bypass that
        override and land the value in the instance's own `__dict__`, which every *later*
        plain read of `instance._operator_order` would still see (attribute lookup finds
        it before falling through to `__pydantic_private__`) while `==` — which compares
        `__pydantic_private__` directly, never the shadow — would not: two pipelines built
        with their operators in opposite written order would then wrongly compare equal.
        """
        order = _operator_key_order(value)
        instance = handler(value)
        instance._operator_order = order
        return instance

    @model_serializer(mode="wrap")
    def _serialise_operators_in_written_order(
        self, handler: SerializerFunctionWrapHandler
    ) -> object:
        """Undo pydantic's field-declaration serialisation order for the four operator keys.

        `handler(self)` already applied whatever `by_alias`/`exclude_defaults`/`mode` the
        caller asked `model_dump` for; this only reshuffles the operator keys that
        survived that call, back into `operator_order` — the order this pipeline's own
        document (or constructor call) actually wrote them in. Without this, round-
        tripping a document that wrote `remove:` above `insert:` would come back with
        `insert:` first every time, because pydantic serialises fields in the order they
        are *declared* on the class, and that is exactly the assumption the rest of this
        module goes to the trouble of not making. See `_reorder_operator_keys`.
        """
        dumped = handler(self)
        if not isinstance(dumped, dict):
            return dumped
        return _reorder_operator_keys(cast("dict[str, object]", dumped), self.operator_order)

    @model_validator(mode="before")
    @classmethod
    def _document_keys_only(cls, value: object) -> object:
        return _known_keys_only(cls, value, subject="pipeline")

    @field_validator("vars", mode="before")
    @classmethod
    def _vars_are_scalars(cls, value: object) -> object:
        """Refuse a structured var in one sentence, rather than in four union branches.

        Pydantic would refuse it anyway — `Mapping[str, Scalar]` sees to that —
        but its answer is one error per branch of the union and none of them
        says what a var is for. This one does.
        """
        if not isinstance(value, Mapping):
            return value

        declared = cast("Mapping[object, object]", value)
        for key, item in declared.items():
            if not isinstance(item, str | int | float | bool):
                raise ValueError(
                    f"var '{key}' is a {type(item).__name__}; a var is a scalar — a "
                    f"string, an integer, a float or a boolean. A var carries a decision "
                    f"several stages must agree on and is substituted into a stage's "
                    f"`with:` value, so there is nothing structured for it to be."
                )
        return declared

    @field_validator("vars", mode="after")
    @classmethod
    def _vars_are_read_only(cls, value: Mapping[str, Scalar]) -> Mapping[str, Scalar]:
        return _read_only(value)

    @model_validator(mode="after")
    def _extends_and_stages_are_mutually_exclusive_with_operators(self) -> Self:
        """A pipeline is either a root that lists `stages:`, or a child that operates on one.

        `02` §3 → *Derivation*: a child changes its parent "by operator and never by
        copy" — `insert`, `replace`, `remove`, `set` (task 1.4). That splits this model's
        two "what do I run" surfaces cleanly by whether `extends` is set: `extends` plus a
        non-empty `stages:` still has no meaning — a document that both names a parent and
        lists its own stages has not said whether that list is the whole pipeline or a
        change to hand the parent, and guessing either answer is exactly the silent
        fallback `01` rules out. The new half, now that operators exist to guess with: no
        `extends` plus a non-empty operator block is refused too, because `insert`/
        `replace`/`remove`/`set` change a **parent**, and a pipeline with none named has
        nothing for them to change — silently ignoring the block would be the same
        species of silent fallback in the other direction. This is an invariant that holds
        with no registry and no parent lookup present, which is what keeps it in the
        authored form rather than in resolution (task 1.3): resolving a parent this
        pipeline may not even name yet would be answering a question that has not been
        asked.

        Task 1.11 gives `slots:` the identical restriction `stages:` already has, for the
        identical reason: a slot is a position in *this* pipeline's own stage list, exactly
        as a stage is, so it belongs on the root that owns that list — never on a pipeline
        whose own contribution to the chain is a set of operators. A child that wants to
        refuse a slot it inherited writes `remove: <slot>` (below); it does not declare a
        second, competing one.
        """
        if self.extends is not None and self.stages:
            raise ValueError(
                f"pipeline '{self.name}' sets 'extends: {self.extends}' and also lists its own "
                f"'stages:'. A pipeline that extends a parent expresses what changes with an "
                f"operator (insert, replace, remove, set), never with its own 'stages:' list — "
                f"drop 'stages:', or drop 'extends' and author this as a standalone pipeline."
            )
        if self.extends is not None and self.slots:
            raise ValueError(
                f"pipeline '{self.name}' sets 'extends: {self.extends}' and also declares its "
                f"own 'slots:'. A slot is a position in the root's own stage list — declare it "
                f"there, or drop 'extends' and author this as a standalone pipeline. A pipeline "
                f"that inherited a slot and wants to refuse it writes 'remove: <slot-id>'."
            )
        if self.extends is None and self._writes_an_operator():
            raise ValueError(
                f"pipeline '{self.name}' writes an operator (insert, replace, remove, set) but "
                f"sets no 'extends:'. An operator changes a parent pipeline, and this pipeline "
                f"names none to change — add 'extends: <parent>', or drop the operator and "
                f"author this pipeline's own 'stages:' directly."
            )
        return self

    def _writes_an_operator(self) -> bool:
        return bool(self.insert or self.replace or self.remove or self.set)

    @model_validator(mode="after")
    def _stage_ids_are_unique(self) -> Self:
        """A stage id is the only handle anything else has on a position, so it names one.

        Operators address stages by id, slots and resolution errors report
        them by id, and `02` §3 makes every operator strict about the id it
        names. Two stages answering to `chunk` would make `insert: {after:
        chunk}` mean two different things depending on which one resolution
        happened to reach first.
        """
        seen: set[str] = set()
        for stage in self.stages:
            if stage.id in seen:
                raise ValueError(
                    f"two stages share the id '{stage.id}'. A stage id is how an operator, a "
                    f"slot and a resolution error each name one position in this pipeline, so "
                    f"it is unique within it."
                )
            seen.add(stage.id)
        return self

    @field_validator("remove", mode="after")
    @classmethod
    def _remove_targets_are_not_a_packs_to_name(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """`02` §3 → *Slots*: a contributed stage "may be `set` but never `replaced` or
        `removed`". `remove`'s targets are a bare `tuple[str, ...]` — unlike `replace`'s
        (`StageDeclaration.id`, already refused by `_id_is_not_a_pack_s_to_give`) — so
        without this, `remove: [weft-graph:entities]` would validate as a document today
        and only fail later, as an ordinary `StaleOperatorTargetError`, indistinguishable
        from a typo. Refusing it here says what it actually is: a pack's contribution can
        never be named away, only the slot that admits it — `remove: <slot-id>` is the
        document's way to refuse every contribution to a slot without naming any pack.
        """
        for target in value:
            _refuse_qualified_id(target, subject="remove target")
        return value

    @model_validator(mode="after")
    def _slot_ids_are_unique_and_free(self) -> Self:
        """A slot id is a position name, on the identical footing a stage id already is.

        Checked here, alongside `_stage_ids_are_unique`, because both only ever run
        against the root's own lists — `slots:` carries the same `extends`-exclusivity
        `stages:` does, so a pipeline with either non-empty is always the pipeline that
        owns both. A slot sharing a stage's id would make `remove: <that-id>` genuinely
        ambiguous between the two `02` §3 gives it the power to drop; a slot sharing
        another slot's id would make the same operator target two positions at once.
        """
        stage_ids = {stage.id for stage in self.stages}
        seen: set[str] = set()
        for slot in self.slots:
            if slot.id in stage_ids:
                raise ValueError(
                    f"slot '{slot.id}' shares its id with a stage in this pipeline. A slot id "
                    f"and a stage id are both names 'remove' can target, so the two "
                    f"vocabularies must stay disjoint — rename the slot or the stage."
                )
            if slot.id in seen:
                raise ValueError(
                    f"two slots share the id '{slot.id}'. A slot id is how 'remove' and a "
                    f"pack's contribution both name one position in this pipeline, so it is "
                    f"unique within it."
                )
            seen.add(slot.id)
        return self


def is_pipeline_operator_field(field: FieldInfo) -> bool:
    """Whether `field` carries `PIPELINE_OPERATOR_MARK` — the one thing task 1.15's ratchet
    (`_OPERATOR_KEYS` just below, and `tests/architecture/test_ff11_pipeline_integrity.py`,
    which imports this function rather than re-deriving the same narrowing itself) needs to
    know about a `Pipeline` field. Public for exactly that reason: the ratchet's "actual"
    side has to read this off the model somehow, and a second, private copy of the
    `json_schema_extra` narrowing below would be the same two-lists risk one function away.

    Pydantic types `FieldInfo.json_schema_extra` as `dict[str, JsonValue] | JsonSchemaExtraCallable
    | None` — a union `pyright` cannot narrow `.get(...)` through cleanly even after `isinstance
    (..., dict)`, since a plain-`dict` branch of that union is still typed as `dict[Unknown,
    Unknown]` in strict mode. The `cast` below states the one fact this module already relies on:
    every `json_schema_extra` it ever sets is a `dict[str, object]` literal, never the callable
    form pydantic also allows.
    """
    extra = field.json_schema_extra
    if not isinstance(extra, dict):
        return False
    return cast("dict[str, object]", extra).get(PIPELINE_OPERATOR_MARK) is True


_OPERATOR_KEYS: Final[tuple[str, ...]] = tuple(
    name for name, field in Pipeline.model_fields.items() if is_pipeline_operator_field(field)
)
"""`02` §3's closed operator table's four names — **read off `Pipeline.model_fields`
itself**, never retyped. Defined only now, after the class body that carries the marks
`PIPELINE_OPERATOR_MARK` documents, because a module-level constant evaluates
immediately at import time and `Pipeline.model_fields` does not exist until the class
statement above has finished running; the functions that consume this tuple
(`_operator_key_order`, `_reorder_operator_keys`) are declared earlier in the file but,
being function bodies, read the name only when *called* — well after the whole module,
this constant included, has finished loading. Not itself an ordering claim — it is only
the vocabulary `_operator_key_order` filters a document's own keys against, and the
sequence `_reorder_operator_keys` reorders a serialised document's keys back into, once
the actual written order is known (`Pipeline.operator_order`, per-instance). The set
stays closed at the ratchet in `tests/architecture/test_ff11_pipeline_integrity.py`
(`01` -> *Fitness functions* item 11(a)): a fifth field carrying
`PIPELINE_OPERATOR_MARK` changes what this tuple *contains*, which is exactly what
that ratchet compares against its own pinned expectation.
"""


def _known_keys_only(model: type[BaseModel], value: object, *, subject: str) -> object:
    """Refuse an unknown key by naming it *and* the keys that exist. `01`'s loud-failure rule.

    Runs before validation proper, so the answer to a mistyped key is the list
    of real ones rather than `extra="forbid"`'s bare "Extra inputs are not
    permitted" — which tells an author that the word they wrote is wrong and
    nothing about which word is right. `extra="forbid"` stays on underneath as
    the backstop for anything that reaches the model another way.

    Keys are reported in the document's spelling, so `with` rather than
    `config`; both are accepted, per `StageDeclaration`.
    """
    if not isinstance(value, Mapping):
        return value

    written = cast("Mapping[object, object]", value)
    known = {_document_spelling(name, field) for name, field in model.model_fields.items()}
    accepted = known | set(model.model_fields)
    unknown = sorted(str(key) for key in written if key not in accepted)
    if unknown:
        raise ValueError(
            f"unknown {subject} key(s): {', '.join(repr(key) for key in unknown)}. "
            f"A {subject} accepts {', '.join(sorted(known))}."
        )
    return written


def _read_only[K, V](value: Mapping[K, V]) -> Mapping[K, V]:
    """Make a mapping field as frozen as the model that carries it.

    `frozen=True` stops a field being rebound; it does nothing about what a
    field *holds*, and pydantic validates `Mapping[...]` into an ordinary
    mutable `dict`. That gap matters here rather than being a nicety: `02` §3
    makes derivation "the parent is referenced, never copied", so a child's
    resolved stages share their parent's `with:` mapping — and an operator
    implemented as an in-place update would edit the parent through it,
    silently, for every other child too. A read-only view makes that a
    `TypeError` at the moment of the write instead of a mystery two pipelines
    away.

    The cost is one annotation each: pydantic knows how to write a `dict` back
    to a document and refuses a `mappingproxy`, so `ConfigBlock` and `VarBlock`
    carry a `PlainSerializer` that unwraps the view. It has to be an annotated
    serializer rather than a `field_serializer` method, because a
    field-serializer method also switches off `exclude_defaults` — and an
    untouched `with:` block reappearing in every document written back is
    exactly the kind of drift between the two directions this module exists to
    prevent. The view is the model's own protection, not part of what a
    pipeline document says.
    """
    return MappingProxyType(dict(value))


def _document_spelling(name: str, field: FieldInfo) -> str:
    """The key a field wears in a document: its alias where it has one, its own name otherwise."""
    return field.serialization_alias or name
