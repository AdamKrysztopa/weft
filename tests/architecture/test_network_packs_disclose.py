"""A distribution that reaches the network says so — ledger task **6.31**.

`docs/02-extension-model.md` §2 → *The trust model* states the posture Weft can actually keep: a
pack runs with your full privileges and installing is trusting, because signature verification and
sandboxing are out of reach without a process boundary. What it offers **instead** is visibility —
`DISCLOSURE`, a module-level value the kernel reads at import, before `register()` runs, and prints
under `weft plugins doctor`.

**Task 6.10 published that offer, and Phase 6's own close measured how thin it was.** The release
set's page — the page an index renders — tells a reader that `doctor` names "what each one
*discloses* about the network, filesystem and subprocess access it uses". Measured on 2026-08-25:
**one first-party distribution in twenty declared a `Disclosure`, and it was `weft-otel`**, whose
exporter defaults to `none`. `weft-openai` (a credentialed provider) and `weft-qdrant` (a network
client) both reported `disclosure: not disclosed`. Requirement 4 read the uncomfortable way:
built-ins were exempt from the discipline the page recommends to everyone.

**Which distributions owe one is derived, not listed.** A distribution owes a disclosure when its
own source imports a client for something outside the process — the same structural question
`tests/architecture/test_the_gate_is_decidable.py` asks of test modules, asked one layer over of
shipped code, and read from imports rather than from prose because a docstring mentioning OpenAI is
not a module calling it (`docs/lessons.md` L5.23).

**What this does not check, deliberately.** Whether a disclosure is *true*. `02` §2 is explicit
that a disclosure is "a disclosure to the operator, never a claim weft checks", and a check that
tried to verify one would be simulating the control the whole section refuses to simulate. What is
checkable is that a pack which reaches outward has said *something* — and that is the difference
between an operator reading `not disclosed` and reading a sentence written by the people who know.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from publish_set import publishing_members

#: Modules whose presence in a distribution's own source means it can reach outside the process.
#: A prefix match on the imported root, so `psycopg.rows` counts as `psycopg`.
NETWORK_CLIENTS: Final[frozenset[str]] = frozenset(
    {"openai", "httpx", "requests", "aiohttp", "qdrant_client", "psycopg", "urllib3"}
)

_IMPORT: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE
)

#: Distributions that reach the network and are permitted to disclose nothing. **Pinned empty.**
#: A pack that reaches outward and says nothing is the state task 6.31 exists to end, and an entry
#: here would be a first-party exemption from the one control `02` §2 actually offers — which is
#: requirement 4's failure exactly.
NETWORK_PACKS_WITHOUT_A_DISCLOSURE: Final[frozenset[str]] = frozenset()


def reaches_the_network(source_dir: Path) -> frozenset[str]:
    """Every network client a distribution's own source imports."""
    found: set[str] = set()
    for path in sorted(source_dir.rglob("*.py")):
        for root in _IMPORT.findall(path.read_text(encoding="utf-8")):
            if root in NETWORK_CLIENTS:
                found.add(root)
    return frozenset(found)


def declares_a_disclosure(source_dir: Path) -> bool:
    """Whether the distribution declares a module-level `DISCLOSURE`.

    Read as an assignment at the start of a line, which is what `weft_kernel.discovery` looks for
    — `getattr(module, "DISCLOSURE")` after import, so it must be module-level, not nested.
    """
    return any(
        re.search(r"^DISCLOSURE\s*[:=]", path.read_text(encoding="utf-8"), re.MULTILINE)
        for path in sorted(source_dir.rglob("*.py"))
    )


def network_reaching_members() -> list[tuple[str, frozenset[str]]]:
    """`(distribution, clients)` for every published member whose source reaches outward."""
    found: list[tuple[str, frozenset[str]]] = []
    for member in publishing_members():
        if member.module is None:
            continue
        clients = reaches_the_network(member.directory / "src")
        if clients:
            found.append((member.name, clients))
    return found


def test_the_sweep_finds_the_distributions_that_reach_the_network() -> None:
    """The floor. A matcher that found none would report none undisclosed."""
    # Act
    reaching = dict(network_reaching_members())

    # Assert
    assert reaching, "no published distribution was found importing a network client"
    assert "weft-openai" in reaching, (
        "`weft-openai` is a credentialed provider and must read as reaching the network; a sweep "
        "that cannot see it is not reading imports"
    )
    assert "weft-qdrant" in reaching


def test_every_distribution_that_reaches_the_network_declares_a_disclosure() -> None:
    """The property. `02` §2's one real control, applied to built-ins too."""
    # Arrange
    reaching = network_reaching_members()
    by_name = {member.name: member for member in publishing_members()}

    # Act
    silent = sorted(
        f"{name} (imports {', '.join(sorted(clients))})"
        for name, clients in reaching
        if not declares_a_disclosure(by_name[name].directory / "src")
        and name not in NETWORK_PACKS_WITHOUT_A_DISCLOSURE
    )

    # Assert
    assert not silent, (
        f"{silent} reach outside the process and declare no `DISCLOSURE`. `02` §2 states the "
        f"posture instead of simulating a control, and disclosure is the control it offers "
        f"instead — a built-in that skips it is exempt from the discipline the release page "
        f"recommends to everyone, which is requirement 4's own failure."
    )


def test_the_waiver_is_empty() -> None:
    """`01` item 0's ratchet discipline: an exemption is a visible act in a diff, and there is no
    honest reason for one here — a pack that reaches outward and says nothing is the whole defect.
    """
    assert not NETWORK_PACKS_WITHOUT_A_DISCLOSURE, (
        "a distribution has been waived out of disclosing. There is no waiver policy: the pack "
        "either says what it touches or it does not reach outward. Fix it, or explain in the "
        "decision log why a first-party pack may keep quiet where a third party is asked not to."
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Planted through both real readers — the tree agrees once this task lands, so this is the
    only place either is seen disagreeing (`docs/lessons.md` L5.19).

    The pair that matters is a module that *imports* a client versus one that merely names it in
    prose: the first owes a disclosure and the second does not, or the check becomes a grep for a
    word and is switched off the first time it fires on a docstring.
    """
    # Arrange
    silent = tmp_path / "silent"
    silent.mkdir()
    (silent / "mod.py").write_text("import httpx\n\ndef go() -> None: ...\n", encoding="utf-8")
    speaking = tmp_path / "speaking"
    speaking.mkdir()
    (speaking / "mod.py").write_text("import httpx\n\nDISCLOSURE = object()\n", encoding="utf-8")
    discussing = tmp_path / "discussing"
    discussing.mkdir()
    (discussing / "mod.py").write_text(
        '"""Unlike httpx, this pack opens no socket."""\n', encoding="utf-8"
    )

    # Act / Assert
    assert reaches_the_network(silent) == frozenset({"httpx"})
    assert not declares_a_disclosure(silent), "the planted silent pack must read as undisclosed"
    assert declares_a_disclosure(speaking)
    assert reaches_the_network(discussing) == frozenset(), (
        "a docstring naming a client is not a module importing one"
    )
