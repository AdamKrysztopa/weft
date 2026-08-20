"""`exit_code_for` — one mapping from a caught `WeftError` to the exit code `docs/03-cli.md`
reserves for it. Task 1.13.

`docs/02-extension-model.md` §3 → *When resolution fails*: "The CLI maps the whole family to
exit code 4." Before this task that mapping was written out twice, by hand, inside
`handle_index` and `handle_ask` — `except (UnknownPluginError, PipelineResolutionError): ...
except WeftError: ...` — and a malformed pipeline document (`weft_cli.pipeline_catalogue`'s own
`PipelineDocumentError`/`MalformedPipelineError`/`DuplicatePipelineNameError`, task 1.9) was in
neither tuple: were a future handler to open a pipeline document the same way `handle_index`
opens a registry, it would fall through to the generic `except WeftError` and exit `1`
("operation failed") instead of `4` ("fix the pipeline") — the exact split `docs/03-cli.md` →
*Output* draws and a malformed document is squarely on the `4` side of. This module is where
that mapping is written exactly once, so `weft_cli.cli` calls it and a later handler cannot
reintroduce the two-copies drift by hand-writing a third `except` chain.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast

from weft_cli.exit_codes import ExitCode, exit_code_for
from weft_cli.pipeline_catalogue import (
    DuplicatePipelineNameError,
    MalformedPipelineError,
    PipelineDocumentError,
)
from weft_kernel.errors import WeftError
from weft_kernel.registry import DuplicateRegistrationError, UnknownPluginError
from weft_kernel.runner import IntactViolationError, PipelineResolutionError


def _boom(cls: type[PipelineResolutionError]) -> PipelineResolutionError:
    """Construct `cls` with `"boom"` and, for every other keyword `__init__` requires,
    a placeholder — fitness function 12 widened some family members to require
    `valid_options`, and this walk cannot know each subclass's own signature ahead of
    time, only that a required keyword named for options wants an empty tuple.
    """
    kwargs: dict[str, object] = {}
    for name, param in inspect.signature(cls.__init__).parameters.items():
        if name in ("self", "message") or param.default is not inspect.Parameter.empty:
            continue
        kwargs[name] = () if "options" in name else "boom"
    # `kwargs` is built from each subclass's own signature, discovered at runtime — pyright
    # cannot narrow it to any one subclass's concrete parameter types, and it should not have
    # to: this cast states that fact rather than working around it with a suppression comment.
    constructor = cast("Callable[..., PipelineResolutionError]", cls)
    return constructor("boom", **kwargs)


def test_every_pipeline_resolution_error_subclass_maps_to_resolution_failed() -> None:
    # Arrange / Act / Assert — driven off the family, not a hand-picked sample: every subclass
    # `PipelineResolutionError.__subclasses__()` (recursively) finds under `weft_kernel` must
    # map to exit 4, the same guarantee `test_pipeline_resolution_error_family.py` already
    # proves the four *fields* have.
    frontier = list(PipelineResolutionError.__subclasses__())
    found: set[type[PipelineResolutionError]] = set()
    while frontier:
        cls = frontier.pop()
        if cls in found:
            continue
        found.add(cls)
        frontier.extend(cls.__subclasses__())

    assert found, "no PipelineResolutionError subclass found — the walk itself is broken"
    for cls in found:
        assert exit_code_for(_boom(cls)) is ExitCode.RESOLUTION_FAILED, cls.__name__


def test_unknown_plugin_error_maps_to_resolution_failed_though_it_is_not_in_the_family() -> None:
    # Edge case — `UnknownPluginError` is a direct `WeftError` subclass, never
    # `PipelineResolutionError` (`weft_kernel.resolution`'s own module docstring: "reused
    # unchanged, never re-implemented"), yet `docs/03-cli.md` -> *Output* puts it on the same
    # exit-4 side as the family: "a name no pack provides... stays 4."
    assert (
        exit_code_for(UnknownPluginError("no 'x' is registered", valid_options=()))
        is ExitCode.RESOLUTION_FAILED
    )


def test_a_malformed_pipeline_document_maps_to_resolution_failed() -> None:
    # `weft_cli.pipeline_catalogue`'s own family is not `PipelineResolutionError` either — its
    # own module docstring is explicit that it is deliberately *not* one of those subclasses —
    # but `docs/03-cli.md` reserves exit 4 for "fix the pipeline", and a document that will not
    # even parse is exactly that. Named individually, not derived, since none of the three is a
    # `PipelineResolutionError` subclass for the family walk above to find automatically.
    assert exit_code_for(PipelineDocumentError("bad yaml")) is ExitCode.RESOLUTION_FAILED
    assert exit_code_for(MalformedPipelineError("bad document")) is ExitCode.RESOLUTION_FAILED
    assert exit_code_for(DuplicatePipelineNameError("dup name")) is ExitCode.RESOLUTION_FAILED


def test_a_project_pipeline_name_collision_maps_to_resolution_failed() -> None:
    # Task 3.7 — the wider guarantee `weft_cli.pipeline_catalogue.full_catalogue` closes:
    # two sources naming the same pipeline is exactly "fix the pipeline", the identical
    # exit-4 side `DuplicatePipelineNameError`/`ContributedPipelineNameCollisionError`
    # already sit on.
    from weft_cli.pipeline_catalogue import ProjectPipelineNameCollisionError

    exc = ProjectPipelineNameCollisionError("shared name")
    assert exit_code_for(exc) is ExitCode.RESOLUTION_FAILED


def test_an_unknown_config_key_maps_to_resolution_failed() -> None:
    # Task 3.7 — `weft config get/set` naming a key nothing reads is "fix the command",
    # `docs/03-cli.md`'s own exit-4 family, one surface over from a pipeline name.
    from weft_cli.config_surface import UnknownConfigKeyError

    exc = UnknownConfigKeyError("unknown key", valid_options=("services.embed",))
    assert exit_code_for(exc) is ExitCode.RESOLUTION_FAILED


def test_an_unrelated_weft_error_maps_to_operation_failed() -> None:
    # Error case — a `WeftError` that is none of the above (a registry-time collision, say)
    # falls to the generic "something failed" exit, never silently upgraded to 4.
    assert exit_code_for(DuplicateRegistrationError("collision")) is ExitCode.OPERATION_FAILED


def test_exit_code_for_reads_the_type_not_the_message() -> None:
    # A message that happens to contain resolution-sounding words must not change the answer —
    # the mapping is by exception *class*, never by parsing English, which is the whole point
    # of moving this out of two hand-written `except` chains and into one function.
    exc = IntactViolationError("this text mentions PipelineResolutionError but is irrelevant")
    assert exit_code_for(exc) is ExitCode.RESOLUTION_FAILED

    other = WeftError("this text says resolution failed but is not the family")
    assert exit_code_for(other) is ExitCode.OPERATION_FAILED
