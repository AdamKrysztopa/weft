"""Unit tests for `weft_kernel.pipeline`.

Mirrors `packages/weft-kernel/src/weft_kernel/pipeline.py`. Task **1.1**: *a
pipeline is a frozen Pydantic model the kernel publishes, which YAML
deserialises into and Python constructs directly — one validator, one error
set, no builder DSL* (`docs/02-extension-model.md` §3 → *One model, two
directions*). Extended by task **1.4**, which settles the question
`docs/build-ledger.md` left open after 1.1: the four derivation operators
stay four keyed document blocks — `insert`, `replace`, `remove`, `set` — and
the order those blocks appear in a document (or a Python call's keyword
arguments) is the order they apply, read off the input rather than assumed
from field declaration order.

The load-bearing test is the first one. "One model, two directions" is not a
claim about a file format; it is a claim that **there is only one thing to be
wrong about**, and the way to check it is to build the same pipeline twice —
once from the mapping a YAML loader hands back, once from a Python call — and
demand the two be equal. A second grammar would show up here as a difference,
and the round trip immediately after it is the same claim in reverse. The
operator-order tests below make the identical claim about the order operators
were written in: a Python call whose keyword arguments are written in the
same order as a document's keys must agree with it there too.

`BASE_DOCUMENT` is `02` §3's own `base.yaml` example as a parsed mapping, so a
document the specification prints is a document the model accepts.
`SPECIFIC_DOCUMENT` does the same for an operator-bearing child, with `remove`
written above `insert` on purpose — round-tripping it is what proves key
order, not merely key content, survives `model_dump`.
"""

from typing import Final

import pytest
from pydantic import ValidationError

from weft_kernel.pipeline import InsertOperator, Pipeline, SlotDeclaration, StageDeclaration

BASE_DOCUMENT: Final[dict[str, object]] = {
    "name": "base",
    "stages": [
        {"id": "extract", "use": "docling", "fallback": ["pdfplumber", "ocr"]},
        {"id": "clean", "use": "standard"},
        {"id": "chunk", "use": "sentence", "with": {"size": 512, "overlap": 50}},
        {"id": "embed", "use": "bge-m3"},
        {"id": "store", "use": "pgvector"},
    ],
}

SPECIFIC_DOCUMENT: Final[dict[str, object]] = {
    "name": "specific",
    "extends": "base",
    "remove": ["clean"],
    "insert": [
        {"after": "chunk", "stage": {"id": "keywords", "use": "keybert", "with": {"top_n": 8}}}
    ],
}


def test_a_parsed_document_and_a_python_construction_are_the_same_model() -> None:
    # Arrange
    written_in_python = Pipeline(
        name="base",
        stages=(
            StageDeclaration(id="extract", use="docling", fallback=("pdfplumber", "ocr")),
            StageDeclaration(id="clean", use="standard"),
            StageDeclaration(id="chunk", use="sentence", config={"size": 512, "overlap": 50}),
            StageDeclaration(id="embed", use="bge-m3"),
            StageDeclaration(id="store", use="pgvector"),
        ),
    )

    # Act
    deserialised = Pipeline.model_validate(BASE_DOCUMENT)

    # Assert
    assert deserialised == written_in_python


@pytest.mark.parametrize(
    "document",
    [BASE_DOCUMENT, SPECIFIC_DOCUMENT],
    ids=["no-operators", "remove-written-above-insert"],
)
def test_the_model_serialises_back_to_the_document_it_was_read_from(
    document: dict[str, object],
) -> None:
    # Arrange — task 1.4: `list(...items())`, not `==`, because a document must round-trip
    # with its *key order* intact wherever that order is load-bearing, and a plain dict `==`
    # cannot tell `{"remove": ..., "insert": ...}` from the same content in the other order.
    pipeline = Pipeline.model_validate(document)

    # Act
    written_back = pipeline.model_dump(mode="json", by_alias=True, exclude_defaults=True)

    # Assert
    assert list(written_back.items()) == list(document.items())


def test_a_python_call_and_a_document_agree_on_the_order_operators_were_written_in() -> None:
    # Arrange — task 1.4's settled claim: kwargs preserve call order exactly as a document's
    # own mapping preserves key order, so the two directions read the same `operator_order`.
    from_document = Pipeline.model_validate(SPECIFIC_DOCUMENT)
    from_python = Pipeline(
        name="specific",
        extends="base",
        remove=("clean",),
        insert=(
            InsertOperator(
                after="chunk",
                stage=StageDeclaration(id="keywords", use="keybert", config={"top_n": 8}),
            ),
        ),
    )

    # Act / Assert
    assert from_document == from_python
    assert from_document.operator_order == ("remove", "insert")
    assert from_python.operator_order == ("remove", "insert")


def test_the_same_operators_written_in_a_different_order_are_different_pipelines() -> None:
    # Arrange — the ledger note's own example: remove-then-insert on one id is a move,
    # insert-then-remove is not the same pipeline, and this is where that becomes visible
    # before either one is ever resolved against a parent.
    stage = StageDeclaration(id="keywords", use="keybert")
    remove_then_insert = Pipeline(
        name="specific",
        extends="base",
        remove=("clean",),
        insert=(InsertOperator(after="chunk", stage=stage),),
    )
    insert_then_remove = Pipeline(
        name="specific",
        extends="base",
        insert=(InsertOperator(after="chunk", stage=stage),),
        remove=("clean",),
    )

    # Act / Assert
    assert remove_then_insert.operator_order == ("remove", "insert")
    assert insert_then_remove.operator_order == ("insert", "remove")
    assert remove_then_insert != insert_then_remove


def test_an_operator_without_extends_is_refused_naming_the_pipeline() -> None:
    # Arrange — an operator changes a *parent*; a pipeline naming none has nothing for it
    # to change, which is the mirror of `extends` plus `stages:` refusing the other guess.
    document: dict[str, object] = {"name": "orphan", "remove": ["clean"]}

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    message = str(excinfo.value)
    assert "orphan" in message
    assert "extends" in message


def test_an_insert_operator_needs_exactly_one_of_after_or_before() -> None:
    # Arrange
    stage = StageDeclaration(id="keywords", use="keybert")

    # Act / Assert — neither anchor
    with pytest.raises(ValidationError):
        InsertOperator(stage=stage)

    # Act / Assert — both anchors
    with pytest.raises(ValidationError):
        InsertOperator(after="chunk", before="clean", stage=stage)


def test_a_pipeline_that_only_retargets_its_parent_needs_no_stages() -> None:
    # Arrange
    document: dict[str, object] = {
        "name": "base-de",
        "extends": "base",
        "vars": {"target_lang": "de"},
    }

    # Act
    pipeline = Pipeline.model_validate(document)

    # Assert
    assert pipeline.stages == ()
    assert pipeline.extends == "base"
    assert pipeline.vars == {"target_lang": "de"}


def test_a_pipeline_is_frozen() -> None:
    # Arrange
    pipeline = Pipeline.model_validate(BASE_DOCUMENT)

    # Act / Assert
    with pytest.raises(ValidationError):
        pipeline.name = "something-else"  # type: ignore[misc]


def test_an_unknown_document_key_is_refused_naming_the_keys_that_exist() -> None:
    # Arrange
    document: dict[str, object] = {"name": "typo", "steps": []}

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    message = str(excinfo.value)
    assert "steps" in message
    assert "stages" in message
    assert "extends" in message


def test_an_unknown_stage_key_is_refused_naming_the_keys_that_exist() -> None:
    # Arrange
    document: dict[str, object] = {
        "name": "typo",
        "stages": [{"id": "chunk", "use": "sentence", "using": {}}],
    }

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    message = str(excinfo.value)
    assert "using" in message
    assert "with" in message


def test_two_stages_sharing_an_id_are_refused_naming_the_id() -> None:
    # Arrange
    document: dict[str, object] = {
        "name": "twice",
        "stages": [{"id": "chunk", "use": "sentence"}, {"id": "chunk", "use": "fixed-size"}],
    }

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    assert "chunk" in str(excinfo.value)


def test_a_var_that_is_not_a_scalar_is_refused_naming_the_var() -> None:
    # Arrange
    document: dict[str, object] = {"name": "structured-var", "vars": {"targets": ["de", "pl"]}}

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    message = str(excinfo.value)
    assert "targets" in message
    assert "scalar" in message


def test_an_author_may_not_write_a_stage_id_a_pack_would_contribute() -> None:
    # Arrange
    document: dict[str, object] = {
        "name": "squatting",
        "stages": [{"id": "weft-graph:entities", "use": "sentence"}],
    }

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    assert "weft-graph:entities" in str(excinfo.value)


def test_a_frozen_pipeline_is_frozen_all_the_way_down() -> None:
    # Arrange
    pipeline = Pipeline.model_validate(
        {"name": "shared", "vars": {"target_lang": "de"}, "stages": BASE_DOCUMENT["stages"]}
    )

    # Act / Assert
    with pytest.raises(TypeError):
        pipeline.stages[2].config["size"] = 4096  # type: ignore[index]
    with pytest.raises(TypeError):
        pipeline.vars["target_lang"] = "pl"  # type: ignore[index]


def test_a_pipeline_that_extends_a_parent_may_not_also_declare_its_own_stages() -> None:
    # Arrange — task 1.3: only `insert`/`replace`/`remove`/`set` (task 1.4) may change what an
    # extending pipeline runs; `stages:` is the authoring surface for a pipeline with no parent.
    # Both present at once has no defined meaning yet, so it is refused here rather than resolved
    # into a guess — the same "refused where it is read" boundary `02` §3 draws for every other
    # invariant that holds with no registry present.
    document: dict[str, object] = {
        "name": "confused",
        "extends": "base",
        "stages": [{"id": "chunk", "use": "sentence"}],
    }

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    message = str(excinfo.value)
    assert "confused" in message
    assert "extends" in message


def test_a_stage_with_no_configuration_carries_an_empty_one() -> None:
    # Arrange
    document: dict[str, object] = {"name": "bare", "stages": [{"id": "clean", "use": "standard"}]}

    # Act
    pipeline = Pipeline.model_validate(document)

    # Assert
    assert pipeline.stages[0].config == {}
    assert pipeline.stages[0].fallback == ()


def test_a_pipeline_declares_a_slot_positioned_against_one_of_its_own_stages() -> None:
    # Arrange — `02` §3 → *Slots*: "a pipeline may contribute into a slot a pipeline opted
    # into." Declaring one is the opt-in; `after`/`before` gives it a position the same way
    # `insert` gives a new stage one.
    document: dict[str, object] = {
        "name": "extensible",
        "stages": [{"id": "chunk", "use": "sentence"}],
        "slots": [{"id": "enrich", "after": "chunk"}],
    }

    # Act
    pipeline = Pipeline.model_validate(document)

    # Assert
    assert pipeline.slots == (SlotDeclaration(id="enrich", after="chunk"),)


def test_a_slot_needs_exactly_one_of_after_or_before() -> None:
    # Arrange / Act / Assert — neither anchor
    with pytest.raises(ValidationError):
        SlotDeclaration(id="enrich")

    # Act / Assert — both anchors
    with pytest.raises(ValidationError):
        SlotDeclaration(id="enrich", after="chunk", before="store")


def test_a_slot_id_may_not_carry_a_packs_qualifier() -> None:
    # Arrange — a slot is the author's own name for a position, never a pack's; the qualified
    # spelling is reserved for what a pack contributes, per `_id_is_not_a_pack_s_to_give`.
    document: dict[str, object] = {
        "name": "confused-slot",
        "stages": [{"id": "chunk", "use": "sentence"}],
        "slots": [{"id": "weft-graph:enrich", "after": "chunk"}],
    }

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    assert "weft-graph:enrich" in str(excinfo.value)


def test_a_slot_id_colliding_with_a_stage_id_is_refused() -> None:
    # Arrange
    document: dict[str, object] = {
        "name": "collision",
        "stages": [{"id": "chunk", "use": "sentence"}],
        "slots": [{"id": "chunk", "after": "chunk"}],
    }

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    assert "chunk" in str(excinfo.value)


def test_a_pipeline_that_extends_a_parent_may_not_also_declare_its_own_slots() -> None:
    # Arrange — slots, like `stages:`, belong to the root; a child changes what it inherited
    # by operator, and `remove: <slot>` (task 1.11) is how it refuses one, never by declaring
    # a second one of its own.
    document: dict[str, object] = {
        "name": "confused",
        "extends": "base",
        "slots": [{"id": "enrich", "after": "chunk"}],
    }

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    message = str(excinfo.value)
    assert "confused" in message
    assert "extends" in message


def test_remove_may_not_name_a_contributed_stage_id() -> None:
    # Arrange — `02` §3 → *Slots*: a contributed stage "may be `set` but never `replaced` or
    # `removed`"; only the slot itself can be refused by name, never a pack's contribution to
    # it — the same reserved qualifier `StageDeclaration.id` already refuses, applied to
    # `remove`'s plain-string targets too.
    document: dict[str, object] = {
        "name": "reaching-into-a-pack",
        "extends": "base",
        "remove": ["weft-graph:entities"],
    }

    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        Pipeline.model_validate(document)

    assert "weft-graph:entities" in str(excinfo.value)
