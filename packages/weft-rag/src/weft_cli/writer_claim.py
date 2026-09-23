"""Claiming a store's writer before the first write — carried repair **R43.15**.

`claim_writer` had exactly one caller before this (`run_index`'s own inline block, task
**43.18**): `weft delete` and `weft reconcile` wrote unclaimed, so a delete landing between a
layer's record read and its own `put_source` could bring a deleted source's record back. Every
command that writes a store now claims it first, released again when it is done, through the
one helper below rather than a copy of the same block at each call site.

Two shapes, because a single store instance and a fan-out build their instance differently.
`claim_writer_for` takes an instance its caller already built — `run_index`'s own primary store
stage. `claim_all_writers` takes a fan-out's own `Participant`s and builds each one itself,
through `weft_cli.fanout.built`, exactly as `weft_cli.deletion`/`weft_cli.reconcile` build
theirs: a claim is state the backend records against the claim itself, not against the Python
object that made the call, so `delete_everywhere`/`reconcile_everywhere` building their own
instance per participant to do the actual work does not race the claim held here.

Only a `SingleWriter` is claimed. Most participants are not one, and skipping them is not a
waiver — nothing in any other contract promises one writer at a time, so there is nothing to
enforce. `WriterBusyError` propagates out of both context managers unchanged; the CLI already
maps it to exit 1 and no new exit code is needed.

**Never nest two claims on one store in one process.** pgvector refuses a second session and
Qdrant admits the same host/pid, so the two backends would disagree about whether a second claim
from the same command is even visible as a conflict. `IndexCommand._auto_reconcile` claims its
own store only after `run_index` released its claim, never while holding one.
"""

from __future__ import annotations

import os
import socket
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime

from weft_cli.fanout import Participant, built
from weft_store.contract import SingleWriter, WriterClaim


def _claim_of(command: str) -> WriterClaim:
    return WriterClaim(
        host=socket.gethostname(), pid=os.getpid(), started_at=datetime.now(UTC), command=command
    )


@asynccontextmanager
async def claim_writer_for(instance: object, *, command: str) -> AsyncGenerator[None]:
    """Claim `instance` for the block's length, if it is a `SingleWriter`; release in `finally`.

    An instance that is not a `SingleWriter` passes through untouched: nothing is claimed and
    nothing is released.
    """
    claimed = isinstance(instance, SingleWriter)
    if claimed:
        await instance.claim_writer(_claim_of(command))
    try:
        yield
    finally:
        if claimed:
            await instance.release_writer()


@asynccontextmanager
async def claim_all_writers(
    targets: tuple[Participant, ...], *, store_target: str | None, command: str
) -> AsyncGenerator[None]:
    """Build every participant once, claim each one that is a `SingleWriter`, and hold all of
    them open for the block's length — see the module docstring for why holding them open
    costs no extra connection to the one a fan-out's own `_ask` will build again.

    A refusal from one participant's `claim_writer` propagates immediately, before any
    participant is asked to do anything: raised here, it reaches the caller directly rather
    than through `delete_everywhere`/`reconcile_everywhere`'s own per-participant
    `except Exception`, which would otherwise turn `WriterBusyError` into one participant's
    reported failure instead of refusing the command outright.
    """
    async with AsyncExitStack() as stack:
        for participant in targets:
            instance = await stack.enter_async_context(
                built(participant, store_target=store_target)
            )
            if isinstance(instance, SingleWriter):
                await instance.claim_writer(_claim_of(command))
                stack.push_async_callback(instance.release_writer)
        yield
