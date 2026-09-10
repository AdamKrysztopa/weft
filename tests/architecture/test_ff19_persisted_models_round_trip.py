"""Fitness function 19 — a model that reaches a persisted artefact can be read back.

`docs/lessons.md` `L8.23`. `weft_kernel.payload.applicability.Applies` had a `PlainSerializer` and
no validator, and a positional-only `fact`, so `model_dump(mode="json")` worked from the day it was
written and `model_validate` on its own output could never work. **Nothing failed while records
were being created**; the failure arrived later, in three commands that merely *read* the directory
those records live in — `weft index`, `weft reconcile` and `weft delete` all load every run record
through one shared helper, so a single unreadable JSON file stopped all three in that project with
no hint which file. It was found by running the binary on a real wheel install at Phase 8's close
review, not by 2,012 tests.

**The property is one line and it holds for a whole population**: for every model that can reach a
persisted artefact, `type(m).model_validate(m.model_dump(mode="json")) == m`. That is what
distinguishes a format from a serialiser — `L6.14` says a read method with no writer answers
emptily, and this is the reverse, which is worse because the artefact persists and outlives the
session that could not read it.

**Scope is the models a run record actually contains**, walked from `RunRecord` rather than listed:
a hand-kept list of "models that get persisted" is the thing that goes stale the moment a field is
added, and `L8.25` is what a hand-kept scope constant does when the tree moves under it. Every model
reachable from `RunRecord`'s field graph is in, with instances built by the same constructors
production uses.
"""

from __future__ import annotations

from typing import Annotated, Final, get_args

import pytest
from pydantic import BaseModel, BeforeValidator

from weft_kernel.payload import MediaType
from weft_kernel.payload.applicability import Applies
from weft_kernel.payload.ext import ExtModel

#: Models reachable from a persisted artefact that cannot round-trip. **Pinned empty.** A model
#: here is one this project knowingly writes and cannot read, which is the defect itself.
MODELS_WAIVED_FROM_ROUND_TRIP: Final[frozenset[str]] = frozenset()


class _Language(ExtModel):
    """A fact model standing in for a pack's own — the shape `index-polish` actually declares."""

    __namespace__ = "weft-test-lang"
    __schema_version__ = "1.0.0"
    code: str


def _models_reachable_from(root: type[BaseModel]) -> set[type[BaseModel]]:
    """Every `BaseModel` in `root`'s field graph, including the containers' element types."""
    seen: set[type[BaseModel]] = set()
    pending: list[type[BaseModel]] = [root]
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        for field in model.model_fields.values():
            for candidate in (field.annotation, *_unwrap(field.annotation)):
                if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                    pending.append(candidate)
    return seen


def _unwrap(annotation: object) -> tuple[object, ...]:
    """`tuple[Applies, ...]` → `(Applies, ...)`, one level at a time, recursively.

    **A PEP 695 alias is resolved through `__value__` before `get_args` is asked.** `type X = A | B`
    produces a `typing.TypeAliasType`, and `get_args` on one returns `()` — not the alias's members.
    So this walk stopped dead at `weft_eval.run_record.MetricRunResult`
    (`type MetricRunResult = Produced[MetricAggregate] | NotAggregated`) and never reached
    `MetricAggregate`, which a `RunRecord` persists on every scored run. The population was five
    models when it should have been eight, and the check reported nothing wrong about the three it
    could not see — measured 2026-09-06 while surveying for ledger task `9.12`, whose own line
    asserts *"FF19 round-trips it"* about a field on one of the missing three (`docs/lessons.md`
    `L9.59`).

    This is the third time this file has been blind to something reached through an alias, and the
    module docstring records the first two: `field.metadata` is empty for a field annotated through
    a PEP 695 alias, which is why the serialiser check reads the core schema. Same language feature,
    same file, a different reader.
    """
    resolved = getattr(annotation, "__value__", annotation)
    args = get_args(resolved)
    if not args:
        return ()
    return args + tuple(inner for arg in args for inner in _unwrap(arg))


def test_the_population_reaches_through_a_pep_695_alias() -> None:
    """Non-vacuity with a name on it: the four models this walk could not see until 2026-09-06.

    `MetricAggregate` is what a `RunRecord` persists for every scored metric, and it sat outside
    this check's population entirely because `MetricRunResult` is a `type X = A | B` alias and
    `get_args` answers `()` for one. The population was five models and read as complete. Naming
    the members here rather than asserting a count means a regression says *which* model went
    missing, and a count would drift every time a field is added (`docs/lessons.md` `L9.59`).
    """
    from weft_eval.run_record import RunRecord

    # Act
    reachable = {model.__name__ for model in _models_reachable_from(RunRecord)}

    # Assert
    assert {"MetricAggregate", "NotAggregated", "ResolvedPipeline", "CorpusIdentity"} <= reachable


def test_applies_round_trips() -> None:
    """The instance the class was written from — `index-polish`'s own `applies_to`."""
    # Arrange
    original = Applies(_Language, code="pl")

    # Act
    dumped = original.model_dump(mode="json")
    restored = Applies.model_validate(dumped)

    # Assert
    assert restored == original, f"Applies did not survive {dumped}"
    assert restored.fact is _Language, "the fact resolved to something other than the class itself"


def test_a_fact_reference_names_its_module() -> None:
    # A bare `__name__` cannot find a class again: two packs may each declare a `Language`, and the
    # record has to say whose. This is why the form changed rather than only gaining a validator.
    dumped = Applies(_Language, code="pl").model_dump(mode="json")
    assert dumped["fact"] == f"{_Language.__module__}:{_Language.__qualname__}"


def test_a_fact_from_a_pack_that_is_gone_refuses_loudly() -> None:
    # Nothing is imported to answer this. A pack that is installed was imported at discovery, so a
    # reference this cannot resolve means the pack is gone — a refusal, never an import of whatever
    # a persisted file happens to name.
    try:
        Applies.model_validate({"fact": "no.such.pack:Language", "constraints": []})
    except Exception as exc:  # noqa: BLE001 — pydantic wraps the ValueError
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("a fact from an uninstalled pack was accepted")

    assert "no.such.pack" in message, f"the refusal does not name what is missing: {message}"


def test_every_model_a_run_record_carries_round_trips() -> None:
    """The population, walked rather than listed."""
    from weft_eval.run_record import RunRecord

    run_record: type[BaseModel] = RunRecord

    reachable = _models_reachable_from(run_record) - {run_record}
    assert reachable, "no models reachable from RunRecord — this check compares nothing"

    unserialisable = sorted(
        model.__name__
        for model in reachable
        if model.__name__ not in MODELS_WAIVED_FROM_ROUND_TRIP
        and _customises_writing_without_reading(model)
    )
    assert not unserialisable, (
        f"these models a run record carries declare a custom serialiser with no matching "
        f"validator, so they can be written and never read: {unserialisable}. The write half "
        f"passing proves nothing (lessons.md L8.23)."
    )


def _customises_writing_without_reading(model: type[BaseModel]) -> bool:
    """Whether `model` declares a custom serialiser and no custom validator beside it.

    **Read off pydantic's own core schema, not off `field.metadata`** — and that distinction is the
    whole reason this function is trustworthy. The first version of this check walked
    `field.metadata` looking for `...Serializer` / `...Validator`, and for `Applies.fact` that list
    is **empty**: the field's annotation is the PEP 695 alias `_FactRef`, so the `Annotated`
    metadata never reaches there. The check passed on the exact model it was written for, and kept
    passing when the validator was deleted to test it. `docs/lessons.md` `L5.19` and `L8.25` are the
    same failure — a check that narrowed to nothing and read as green — so this one is proved
    against a planted removal rather than reasoned about.
    """
    schema = repr(model.__pydantic_core_schema__)
    return "'serialization'" in schema and "function-before" not in schema


def test_the_check_can_actually_fail() -> None:
    """Plant both shapes and watch the detector separate them.

    This is not decoration. The **first** version of `_customises_writing_without_reading` walked
    `field.metadata`, which is empty for a field annotated through a PEP 695 alias — so it returned
    `False` for `Applies` both before and after the validator was deleted, and the whole check was
    green about the one model it was written for. The version below was chosen by planting the
    removal and watching this file go red, which is the only reason it is trustworthy.
    """
    from pydantic import PlainSerializer

    class WriteOnly(BaseModel):
        fact: Annotated[type[ExtModel], PlainSerializer(lambda f: f.__name__, return_type=str)]

    class RoundTrips(BaseModel):
        fact: Annotated[
            type[ExtModel],
            PlainSerializer(lambda f: f.__name__, return_type=str),
            BeforeValidator(lambda v: v),
        ]

    assert _customises_writing_without_reading(WriteOnly), (
        "a model that declares how it is written and not how it is read reads as fine"
    )
    assert not _customises_writing_without_reading(RoundTrips)
    assert not _customises_writing_without_reading(Applies), (
        "Applies is the model this check exists for, and it must pass now that it round-trips"
    )


def test_applies_round_trips_for_every_constraint_kind_its_own_fields_can_hold() -> None:
    """Carried repair **R9.9**. One instance is not a round-trip check over a type with three
    independent fields.

    `test_applies_round_trips` above builds `Applies(_Language, code="pl")` — a `fact` plus a
    `constraints` pair — and nothing else, so `media_type` was never dumped and never read back.
    That is **precisely** the shape that failed: a `media_type`-constrained `Applies` did not
    survive persistence and took three commands down with it (`docs/lessons.md` `L9.43`), under a
    fitness function whose whole subject is persisted models surviving a round trip.

    The population is derived from `Applies.model_fields` rather than listed here, so a fourth
    constraint kind added tomorrow is covered without an edit — and asserted below, so this test
    cannot quietly stop covering a field the class grew.
    """
    cases = {
        "fact and constraints": Applies(_Language, code="pl"),
        "media_type, one": Applies(media_type=MediaType.TABLE),
        "media_type, several": Applies(media_type=(MediaType.TABLE, MediaType.IMAGE)),
    }
    # Two shapes are deliberately absent, and both refuse rather than round-trip — which is
    # itself worth asserting, because each is a reason the coverage union below is assembled
    # from separate instances rather than from one all-fields instance.
    with pytest.raises(TypeError, match="no constraint at all"):
        Applies()
    # There is deliberately no "every field at once" case: `Applies` refuses a `fact` and a
    # `media_type` together, so the union below is assembled from separate instances rather
    # than one. Asserted rather than assumed, because it is why the coverage check underneath
    # has to union across cases and would otherwise read as an odd way to write one dump.
    with pytest.raises(ValueError, match="fact const"):
        Applies(_Language, media_type=MediaType.TEXT, code="pl")

    for label, original in cases.items():
        dumped = original.model_dump(mode="json")
        restored = Applies.model_validate(dumped)
        assert restored == original, f"an Applies constrained by {label} did not survive {dumped}"

    exercised = {
        field
        for original in cases.values()
        for field, value in original.model_dump().items()
        if value
    }
    assert exercised == set(Applies.model_fields), (
        f"`Applies` carries {sorted(set(Applies.model_fields))} and these cases only exercise "
        f"{sorted(exercised)} — the kind left out is the one this repair was filed about, and "
        f"the reason this assertion is here rather than a comment saying the list is complete."
    )
