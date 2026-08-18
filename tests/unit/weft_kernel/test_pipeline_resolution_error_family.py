"""Every `PipelineResolutionError` subclass carries the same four structured fields.

Task **1.13**, `docs/02-extension-model.md` §3 → *When resolution fails*: "all carrying
the same required fields — the pipeline, the stage ids, the distributions in conflict,
and the remedy." Before this task the four were readable only by parsing each subclass's
own message string — real information for a human, useless for a caller (the CLI, a
future report) that wants to act on *which* stages or *which* distributions without a
regex over English prose. This test proves the fields are real, on the shared family
base, uniformly across every member — and it is driven off the subclass *set* itself
rather than a hand-written list of names, exactly as the task instructions require: add a
new `PipelineResolutionError` subclass later, and this test fails for it the moment its
`__init__` (inherited or overridden) stops forwarding all four to the base, rather than
staying silent the way a hand-picked list of "the ones I remembered" would.

`weft_kernel.runner` and `weft_kernel.resolution` are the only two modules that define a
member of this family today (see their own module docstrings) — importing both is enough
for `__subclasses__()` to see every one that exists in this tree, on the identical
reasoning `tests/docs/test_troubleshooting_coverage.py`'s own module-walk already uses for
the wider `WeftError` hierarchy. The walk is filtered to classes whose `__module__` starts
with `weft_kernel` for the same reason that file filters to first-party packages: a
throwaway subclass a *test* defines (see `_ForgetfulError` below) must never count toward, or
be required by, the real coverage this file checks — `WeftError.__subclasses__()`, and
therefore `PipelineResolutionError.__subclasses__()`, is process-global.
"""

from __future__ import annotations

from typing import Final

from weft_kernel import resolution, runner
from weft_kernel.runner import PipelineResolutionError

_SENTINEL_MESSAGE: Final[str] = "a representative message"
_SENTINEL_PIPELINE: Final[str] = "acme-pipeline"
_SENTINEL_STAGES: Final[tuple[str, ...]] = ("stage-a", "stage-b")
_SENTINEL_DISTRIBUTIONS: Final[tuple[str, ...]] = ("acme-pack",)
_SENTINEL_REMEDY: Final[str] = "do the thing the message names"


def _carries_the_four_fields(cls: type[PipelineResolutionError]) -> bool:
    """Whether constructing `cls` with all four keyword fields actually stores them.

    Pure, and driven purely off `cls`'s own `__init__` — kept separate from both the main
    walk below and the self-test at the foot of this file, the same shape
    `tests/docs/test_troubleshooting_coverage.py`'s own `missing_troubleshooting_entries`
    already uses: something the self-test can call that is not the exact assertion it is
    protecting.
    """
    exc = cls(
        _SENTINEL_MESSAGE,
        pipeline=_SENTINEL_PIPELINE,
        stages=_SENTINEL_STAGES,
        distributions=_SENTINEL_DISTRIBUTIONS,
        remedy=_SENTINEL_REMEDY,
    )
    return (
        exc.pipeline == _SENTINEL_PIPELINE
        and exc.stages == _SENTINEL_STAGES
        and exc.distributions == _SENTINEL_DISTRIBUTIONS
        and exc.remedy == _SENTINEL_REMEDY
    )


def _every_family_member() -> frozenset[type[PipelineResolutionError]]:
    """Every `PipelineResolutionError` subclass defined under `weft_kernel`, walked recursively.

    Recursive, not `.__subclasses__()` alone, on the same reasoning
    `tests/docs/test_troubleshooting_coverage.py`'s own `_all_weft_error_subclasses` already
    documents: a class that subclasses an existing subclass rather than
    `PipelineResolutionError` directly must still be found.
    """
    found: set[type[PipelineResolutionError]] = set()
    frontier = list(PipelineResolutionError.__subclasses__())
    while frontier:
        cls = frontier.pop()
        if cls in found:
            continue
        found.add(cls)
        frontier.extend(cls.__subclasses__())
    return frozenset(cls for cls in found if cls.__module__.startswith("weft_kernel"))


# --- the floor ----------------------------------------------------------------------------


def test_the_family_has_more_than_a_couple_of_members() -> None:
    # Floor — a walk that silently found nothing (or almost nothing) would let the
    # assertion below pass by having nothing real to require, exactly the shape
    # `docs/08-manuals.md` §3's own floor rule forbids for a comparison like this one.
    members = _every_family_member()
    assert len(members) >= 10, (
        f"only {sorted(cls.__name__ for cls in members)} found under PipelineResolutionError "
        "in weft_kernel — the walk itself is broken, or the family shrank without this test "
        "being told where to look next."
    )


def test_resolution_reuses_runner_s_classes_rather_than_shadowing_them() -> None:
    # Regression for the fat-class bug this task's audit found and fixed:
    # `weft_kernel.runner.Runner.resolve` used to raise the bare `PipelineResolutionError`
    # for these same three checks instead of the specific names
    # `weft_kernel.resolution.resolve` already had for a pipeline document. `is`, not `==`
    # — this proves there is exactly one class per kind, never two classes that merely
    # share a name and would each need their own troubleshooting entry.
    assert resolution.UnmetRequiresError is runner.UnmetRequiresError
    assert resolution.StageCompositionError is runner.StageCompositionError
    assert resolution.IntactViolationError is runner.IntactViolationError


# --- the coverage check itself -------------------------------------------------------------


def test_every_family_member_carries_the_four_required_fields() -> None:
    # Arrange / Act / Assert — one construction per subclass, all through the identical
    # base `__init__` signature every member is expected to inherit unmodified: no member of
    # this family overrides `__init__` today, which is what makes one shared call safe to
    # drive off the subclass set rather than one hand-written construction per class.
    for cls in sorted(_every_family_member(), key=lambda c: c.__name__):
        assert _carries_the_four_fields(cls), (
            f"{cls.__name__} does not forward pipeline/stages/distributions/remedy to "
            f"PipelineResolutionError.__init__ — a caller reading these fields on this "
            f"class would get stale defaults instead of what actually failed."
        )


def test_the_family_base_defaults_every_field_to_an_honest_empty_value() -> None:
    # Edge case — a failure with genuinely nothing to name for one of the four (no pipeline
    # at all, say, for `weft_kernel.runner.Runner.resolve`'s anonymous `StageSpec` list —
    # `02` §3's own worked case for `UnknownParentPipelineError` having "no stage ids and no
    # distribution to name") must default to an honest absence, never a placeholder value
    # that reads as real data a caller could act on.
    exc = PipelineResolutionError("message only")

    assert exc.pipeline is None
    assert exc.stages == ()
    assert exc.distributions == ()
    assert exc.remedy == ""


def test_a_subclass_that_drops_a_field_would_fail_the_coverage_check() -> None:
    # Error case — the self-test `docs/08-manuals.md` §3 style requires of a floor: prove
    # the comparison can actually fail before trusting that it passing means anything. A
    # subclass that overrides `__init__` and never forwards `remedy` (or any of the four) to
    # the base is exactly the defect `test_every_family_member_carries_the_four_required_
    # fields` exists to catch the moment a new subclass like this one ships.
    class _ForgetfulError(PipelineResolutionError):
        def __init__(self, message: str, **_ignored: object) -> None:
            super().__init__(message)  # never forwards pipeline/stages/distributions/remedy

    assert not _carries_the_four_fields(_ForgetfulError)
