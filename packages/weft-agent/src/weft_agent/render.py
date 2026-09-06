"""The renderer for `weft_agent.command.AgentCommandResult` — registered through the identical
`weft_kernel.discovery.PackRegistrar.add_renderer` seam a stranger's pack uses (task **6.20**,
G13's third repair). Ledger task **7.4**.

**What a reader pipes goes to stdout, everything about the run goes to stderr** —
`docs/03-cli.md` → *Output*. The final answer is the one thing a caller piping `weft agent`'s
output into another program wants; the transcript summary and why the loop stopped are about the
run itself, not its answer, and belong on stderr with everything else this tree already reports
that way.

**Exit code.** `ExitCode.SUCCESS` when the loop answered
(`weft_agent.loop.StopReason.ANSWERED`) — the only member `stopped_because` carries that comes
with a `final_answer`; `ExitCode.OPERATION_FAILED` for the other two, on the same footing
`weft_cli.render`'s own renderers use for "the run finished but did not produce what was asked
for": budget exhaustion and a cascade that never decided are both real outcomes, never raised as
exceptions (`weft_agent.loop.run_agent`'s own docstring), but neither is a caller getting an
answer.
"""

from __future__ import annotations

from typing import cast

from weft_agent.command import AgentCommandResult
from weft_agent.loop import StopReason
from weft_command import ExitCode, Rendered


def render_agent(result: object) -> Rendered:
    """`weft_kernel.discovery.PackRegistrar.add_renderer`'s own callable shape: `object` in,
    a `Rendered` out. Narrowed to `AgentCommandResult` immediately, exactly as every renderer
    `weft_cli.render` registers narrows its own result type first — `cast`, not `assert`: the
    latter is stripped under `-O`, and `weft_agent.command_tools._observation_of`'s own
    docstring already states why this tree does not rely on one for a type it must actually
    have.
    """
    agent_result = cast(AgentCommandResult, result)

    steps_taken = len(agent_result.transcript.steps)
    summary = (
        f"goal: {agent_result.transcript.goal}\n"
        f"steps taken: {steps_taken}\n"
        f"stopped because: {agent_result.stopped_because.value}"
    )
    exit_code = (
        ExitCode.SUCCESS
        if agent_result.stopped_because is StopReason.ANSWERED
        else ExitCode.OPERATION_FAILED
    )
    return Rendered(stdout=agent_result.final_answer, stderr=summary, exit_code=exit_code)


__all__ = ["render_agent"]
