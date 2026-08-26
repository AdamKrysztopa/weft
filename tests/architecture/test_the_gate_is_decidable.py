"""No member of the canonical gate depends on a third-party service — ledger task **6.28**.

`docs/09-release.md` §4.3, prerequisite **V5**: "a **deterministic subset** that runs in CI with no
credentials and no network, so a regression is caught by the gate rather than by a quarterly
ritual."

**The failure that produced this task.** Task 6.24's implementer ran `poe ci-checks` and got
`tests/integration/test_hypothetical_questions_pipeline.py` failing with `vector search must find
something in a store that was just populated: assert []`, then passing twice on immediate reruns
with no code change. It reaches the live OpenAI API.

**Gating on the credential is not enough, and all four files already did.** Every integration
module that reaches OpenAI skips when `OPENAI_API_KEY` is unset — so a CI runner without one is
deterministic, and that is where the discipline was checked. The machine it is *not* deterministic
on is a developer's, where the key is exported for other work. **Having a credential in the
environment is not asking for a network run**, and the difference matters because of what a
non-deterministic gate teaches: re-run red tests until they are green, which is the habit that lets
a real regression through. It also makes a dispatched agent's "green" unfalsifiable — a failure it
did not cause is indistinguishable from one it did, and that cost three separate diagnostic detours
in one session (`docs/lessons.md` L6.27).

**So the opt-in is explicit and separate from the credential.** `WEFT_LIVE_API_TESTS` says *"I am
asking for a network run"*; `OPENAI_API_KEY` says *"I could"*. Both are required, and the check
below is that every module which can reach the network says so.

**Why the guard is repeated in each file rather than shared.** The same reason each of those
modules already repeats its container-skip discipline and says so: each should read as one
self-contained scenario. What is shared is the *variable name*, and this check is what keeps the
four copies honest — a module that reaches the network and forgets the guard fails here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT

INTEGRATION: Final[Path] = REPO_ROOT / "tests" / "integration"

#: The explicit opt-in. Separate from any credential on purpose — see the module docstring.
OPT_IN_VAR: Final[str] = "WEFT_LIVE_API_TESTS"

#: What "reaches a third-party service" looks like in an import. Read off imports rather than off
#: prose, because a module's docstring discussing OpenAI is not a module calling it
#: (`docs/lessons.md` L5.23 — a property about code needs a structural check).
_NETWORK_IMPORT: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:from|import)\s+(weft_openai|openai)\b", re.MULTILINE
)


def modules_reaching_the_network() -> list[Path]:
    """Every integration module that imports a client for a third-party service."""
    return [
        path
        for path in sorted(INTEGRATION.glob("test_*.py"))
        if _NETWORK_IMPORT.search(path.read_text(encoding="utf-8"))
    ]


def test_every_module_that_reaches_the_network_requires_the_explicit_opt_in() -> None:
    """V5's property, checked where it is actually decided."""
    # Arrange
    reaching = modules_reaching_the_network()

    # Act
    ungated = [path.name for path in reaching if OPT_IN_VAR not in path.read_text(encoding="utf-8")]

    # Assert — non-vacuity first: a matcher that found nothing would report nothing ungated.
    assert reaching, (
        f"no module under {INTEGRATION} was found importing a third-party client. Four do; the "
        f"matcher is wrong, not the tree."
    )
    assert not ungated, (
        f"{ungated} can reach a third-party service and do not require `{OPT_IN_VAR}`. `09` §4.3's "
        f"V5 asks for a deterministic subset; a gate whose green depends on what a live service "
        f"answered teaches whoever runs it to re-run red tests until they pass, which is the habit "
        f"that lets a real regression through."
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Planted through the real matcher — the real tree agrees once this task lands, so this is
    the only place the comparison is seen disagreeing (`docs/lessons.md` L5.19).

    The pair that matters is a module that *imports* a client versus one that merely *mentions*
    the service in prose: the first must be caught and the second must not, or the check becomes
    a grep for a word and gets switched off.
    """
    # Arrange
    reaching = tmp_path / "test_reaching.py"
    reaching.write_text("from weft_openai import Settings\n", encoding="utf-8")
    discussing = tmp_path / "test_discussing.py"
    discussing.write_text(
        '"""Unlike weft_openai, this pack needs no account and no network."""\n', encoding="utf-8"
    )

    # Act
    caught = bool(_NETWORK_IMPORT.search(reaching.read_text(encoding="utf-8")))
    prose = bool(_NETWORK_IMPORT.search(discussing.read_text(encoding="utf-8")))

    # Assert
    assert caught, "an import of a third-party client must be caught"
    assert not prose, "a docstring naming the service is not a module calling it"
