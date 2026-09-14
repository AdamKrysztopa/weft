"""Closing plugin instances without displacing the exception already propagating — `R18.1`.

`weft_kernel.runner.Runner._flush_all`'s shape for `flush`, applied to `weft_kernel.seam.aclose`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from weft_kernel.errors import WeftError
from weft_kernel.seam import aclose


@dataclass(frozen=True, slots=True)
class CloseTarget:
    """One instance `close_each` will close, and the attribution its failure is reported under."""

    instance: object
    distribution: str
    contract: str
    plugin: str
    stage: str | None = None


async def close_each(targets: Sequence[CloseTarget], *, in_flight: BaseException | None) -> None:
    """Close every target in order, trying each even when an earlier one failed.

    With `in_flight` set, every close failure becomes a note on it and nothing is raised, so a
    `CancelledError` stays one. With nothing in flight, the first failure is raised with its
    attribution intact and later failures noted on it.
    """
    failures: list[WeftError] = []
    for target in targets:
        try:
            await aclose(
                target.instance,
                distribution=target.distribution,
                contract=target.contract,
                plugin=target.plugin,
                stage=target.stage,
            )
        except WeftError as failure:
            failures.append(failure)

    if not failures:
        return

    if in_flight is not None:
        for failure in failures:
            in_flight.add_note(f"close failed during cleanup: {failure}")
        return

    first, rest = failures[0], failures[1:]
    for failure in rest:
        first.add_note(f"close failed during cleanup: {failure}")
    raise first


__all__ = ["CloseTarget", "close_each"]
