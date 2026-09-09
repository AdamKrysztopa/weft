"""Fitness function 21 — the agent is an ordinary pack, on a stranger's terms.

Ledger task **7.1**, `docs/01-high-level-plan.md` → Phase 7, `docs/05-grilling-sessions.md` → G8.
G8 settled that Weft's agentic front end is a **first-party pack**, not an agentic REPL, because
`03`'s governing rule keeps logic out of the driving adapter — and that it lands after release so it
is built against published, versioned contracts rather than moving ones.

**The claim Phase 7 exists to make is falsifiable, and this is what falsifies it.** `01` → Phase 7's
words are *"a first-party pack built against nothing but the released API, on the same terms a
stranger has"*. A pack bundled inside the `weft-rag` wheel would still register through the public
entry point and would still pass every check that reads a registry — and it would have quietly
stopped being on a stranger's terms, because a stranger cannot add a package to somebody else's
wheel. That is the same demotion bundling `weft-kernel` would inflict on fitness function 1, which
is why `weft-agent` is a **seventh distribution** and why that fact is asserted rather than assumed.

**Three properties, each of which can fail on its own:**

*(a) It is a distribution*, with its own `pyproject.toml`, its own licence files, and a single
`weft.packs` entry point — the same one a third party declares, per `02` §2.

*(b) It registers against contracts it did not define.* This is `01` → Phase 7's own test of whether
the extension model works, and it is checked structurally: every contract the pack registers under
must be published by some *other* distribution. A pack that registered only against contracts it
also published would prove nothing about the seam.

*(c) Core has no knowledge of it.* `weft-kernel` never learns the word — not in a name, not in a
dependency, not in a comment. `01` → *The kernel boundary* already forbids the kernel naming a
capability; an agent is the largest capability this project will ship, and it is the sharpest test
of that rule the tree will ever get.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
#: Where `weft_agent` lives. **Inside the `weft-rag` wheel since G19 (2026-09-09)**, which is the
#: one clause of this fitness function that moved: it was its own distribution until then.
AGENT_ROOT: Final[Path] = REPO_ROOT / "packages" / "weft-rag"
AGENT_MODULE: Final[Path] = AGENT_ROOT / "src" / "weft_agent"
KERNEL_ROOT: Final[Path] = REPO_ROOT / "packages" / "weft-kernel"

#: The entry-point group every pack declares — `docs/02-extension-model.md` §2.
_PACK_GROUP: Final[str] = "weft.packs"


def _pack_entry_points(distribution: Path) -> Mapping[str, str]:
    """The `weft.packs` table a distribution declares, as a mapping of name to target.

    Narrowed once, here, rather than by chaining `.get` off a bare `isinstance` — pyright reads the
    chained form as `dict[Unknown, Unknown]` and every use of it afterwards is partially unknown.
    """
    with (distribution / "pyproject.toml").open("rb") as handle:
        loaded: Mapping[str, Any] = tomllib.load(handle)
    project: Mapping[str, Any] = loaded.get("project", {})
    entry_points: Mapping[str, Any] = project.get("entry-points", {})
    declared: Mapping[str, str] = entry_points.get(_PACK_GROUP, {})
    return declared


def test_the_agent_is_an_ordinary_pack_module() -> None:
    """(a) — and this clause was rewritten by **G19** on 2026-09-09, deliberately and at a cost.

    It read *"the agent is its own distribution"*, asserting `packages/weft-agent/` and its licence
    files, on Phase 7's claim that a stranger "cannot add a package to somebody else's wheel".
    G19 settled two published names, so `weft_agent` moved inside the `weft-rag` wheel and that
    assertion became a check on the opposite of what was decided.

    **What was actually lost, said plainly:** the agent no longer demonstrates the stranger's
    position by *being* a separate artefact. What is not lost is the property Phase 7 was proving —
    that the pack was built against nothing but the released API — which clauses (b), (c) and (d)
    below assert directly from the code and which no packaging arrangement can fake. The continuous
    demonstration moved to `testing/weft-canary` and the five `examples/weft-example-*` packs:
    separate distributions, discovered from outside the tree, none of them ever published. That
    substitution is G19's own reasoning and its weakest point; it is recorded here rather than in a
    commit message so the next reader meets it at the check it changed.
    """
    assert AGENT_MODULE.is_dir(), (
        "packages/weft-rag/src/weft_agent/ does not exist. The agent is a pack like any other and "
        "has to be somewhere a pack lives."
    )
    for required in ("pyproject.toml", "LICENSE", "NOTICE"):
        assert (AGENT_ROOT / required).is_file(), f"packages/weft-rag/{required} is missing"


def test_the_agent_declares_one_pack_entry_point() -> None:
    """The same single entry point a third party declares — no second mechanism, no extra hook.

    Read out of the wheel that now carries it, and narrowed to the agent's own row: `weft-rag`
    declares twenty, one per pack, and what this asserts is that exactly one of them is the
    agent's and that it points at `weft_agent`.
    """
    packs = dict(_pack_entry_points(AGENT_ROOT))
    agent_rows = {name: target for name, target in packs.items() if target.startswith("weft_agent")}

    assert list(agent_rows) == ["agent"], (
        f"weft_agent must be reached by exactly one `{_PACK_GROUP}` entry point named `agent`, "
        f"like every other pack in this wheel; found {agent_rows!r} among {sorted(packs)}"
    )


def test_the_agent_registers_against_contracts_it_did_not_define() -> None:
    """(b) — the extension model working, checked rather than claimed.

    Structural, not textual: the contracts are read off the registry the pack actually populates,
    and each is asked which module defines it. A contract defined inside `weft_agent` would mean
    the pack had published its own extension point and registered into it, which proves nothing
    about whether a stranger could have done the same thing.
    """
    from weft_agent import Settings, register
    from weft_kernel.discovery import PackRegistrar
    from weft_kernel.registry import Registry

    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-agent")
    register(registrar, Settings())
    registrar.commit()

    contracts = list(registry.contracts())
    assert contracts, "weft-agent registered nothing at all, so it is not yet a pack"

    home_grown = sorted(
        contract.__name__
        for contract in contracts
        if contract.__module__.split(".")[0] == "weft_agent"
    )
    assert not home_grown, (
        f"weft-agent registers against contracts it defines itself: {home_grown}. Phase 7's claim "
        f"is that a pack can be built against the *released* API; registering into an extension "
        f"point the same pack published tests nothing about that."
    )


def test_the_kernel_has_never_heard_of_an_agent() -> None:
    """(c) — the sharpest test `01` → *The kernel boundary* will get.

    Read over the whole kernel distribution rather than its source alone: a dependency line or a
    comment naming the agent is the same leak as a class would be, and `01`'s rule is about what
    the kernel *knows*, not about where the knowledge is spelled.
    """
    leaks = sorted(
        f"{path.relative_to(REPO_ROOT)}:{number}"
        for path in KERNEL_ROOT.rglob("*")
        if path.is_file() and path.suffix in {".py", ".toml", ".md"}
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "agent" in line.lower()
    )
    assert not leaks, (
        f"weft-kernel names the agent at {leaks}. The kernel expresses, loads and runs contracts "
        f"it knows nothing about; an agent is the largest capability this project ships and the "
        f"rule does not bend for it."
    )


def test_the_check_can_actually_fail() -> None:
    # `docs/lessons.md` L5.6. Each half planted through the same predicate it guards, so a green
    # here cannot mean the sweep stopped looking.
    assert not (REPO_ROOT / "packages" / "weft-no-such-pack").is_dir()

    from weft_kernel.registry import Registry

    assert Registry().contracts() is not None
    assert "agent" in "the AGENT loop".lower(), "the kernel sweep's matcher is case-blind"
