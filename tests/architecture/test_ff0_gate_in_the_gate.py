"""Fitness function 0 — the gate must be in the gate.

Every architecture check runs inside the composite task the documentation calls
canonical, and this test asserts that membership.

It exists because of the reference. `a prior project` shipped a 316-line hexagonal boundary
checker that was **not** in `poe ci-checks`: the composite its own `CLAUDE.md`
called the canonical full gate resolved to `quality`, which omitted it, and
`.pre-commit-config.yaml` omitted it too. A fitness function that is not wired
into the canonical task is not a fitness function.

The waiver constant below is the ratchet, copied from the one genuinely good
check in the reference (`tests/unit/architecture/test_allowlist_empty.py`). It is
pinned empty. Adding a name to it is a deliberate, visible act in a diff rather
than a silent edit to a script nobody reads.
"""

from typing import Final

from .conftest import str_list_at, table_at

CANONICAL_GATE: Final[str] = "ci-checks"

#: Architecture checks permitted to sit outside the canonical gate.
#: **Pinned empty.** A check outside the gate does not run, and a check that does
#: not run is documentation. If you believe you need an entry here, the honest
#: options are to fix the check or to delete it.
CHECKS_WAIVED_FROM_GATE: Final[frozenset[str]] = frozenset()

#: Tasks that constitute the architecture checks. Every one must be reachable
#: from the canonical gate.
ARCHITECTURE_TASKS: Final[frozenset[str]] = frozenset({"arch"})


def test_waiver_list_is_empty() -> None:
    assert not CHECKS_WAIVED_FROM_GATE, (
        "A check has been waived out of the canonical gate. The waiver policy is that "
        "there is no waiver policy: a check outside the gate does not run. Fix it or "
        "delete it, but do not park it here."
    )


def test_canonical_gate_exists(workspace_config: dict[str, object]) -> None:
    tasks = table_at(workspace_config, "tool", "poe", "tasks")

    assert CANONICAL_GATE in tasks, (
        f"The canonical gate '{CANONICAL_GATE}' is not defined. Fitness function 0 has "
        f"nothing to check membership against, which is exactly the reference's failure."
    )


def test_every_architecture_check_runs_in_the_canonical_gate(
    workspace_config: dict[str, object],
) -> None:
    gate = table_at(workspace_config, "tool", "poe", "tasks", CANONICAL_GATE)

    missing = ARCHITECTURE_TASKS - CHECKS_WAIVED_FROM_GATE - set(str_list_at(gate, "sequence"))

    assert not missing, (
        f"Architecture checks {sorted(missing)} are not in '{CANONICAL_GATE}'. They will "
        f"not run in CI. The reference shipped a boundary checker in exactly this state and it "
        f"passed a tree with 11 violations."
    )
