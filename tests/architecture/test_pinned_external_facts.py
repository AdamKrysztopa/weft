"""A pinned fact about the outside world has one copy and a date — ledger task **8.14**.

`docs/internal/lessons.md` L8.13 is what this file exists to stop recurring.
`weft_openai.llm.DEFAULT_MODEL` sat at `gpt-4o-mini` two model generations past its currency, and
two properties of the tree — not the value itself — are what made that invisible and would have made
repointing it silently partial:

- **The constant had copies.** `tests/integration/test_hypothetical_questions_pipeline.py` and
  `test_raptor_pipeline.py` each hardcoded the literal in a `RoleMapping` handed to the *real*
  provider rather than importing the constant, so both would have gone on placing live, billable
  calls against the old model after the pin moved, while the one test that imports it followed.
  A constant with copies is not a constant; it is a convention.
- **It carried no date**, while its own neighbour does. `weft_eval.pricing.RATES_AS_OF` exists
  because a rate table goes stale and a `RunPrice` that did not say when its rates were checked
  would be a number that looks current forever. A pinned model is the same kind of fact and was
  admitting nothing, so nothing in the repository could ever report the staleness — only a person
  noticing.

**What this file does not do, deliberately: it does not decide when a pin is too old.** No
assertion here compares a date against the wall clock. `09` §4.4's argument against inventing a
threshold is about quality targets, but its reason generalises exactly — *"a number nobody can
defend gets re-baselined until it means nothing"* — and a test that starts failing on a day nobody
changed anything, at an interval chosen by whoever wrote the test, is that failure with a timer
attached. What the age *should* be is a policy question, filed for `implement-ll` rather than
settled here by implication. The two properties below are the ones that can be checked without
choosing anything: **the pin is priced**, and **the pin is not copied**.

Both were whole-tree properties across two distributions until **G19** (2026-09-09) folded
`weft_openai` into the `weft-rag` wheel behind the `openai` extra. The property is unchanged and
so is the direction of the ban — `weft_openai` publishes the model, the rates live elsewhere, and
no pack may import another's constants across that line — but the two now share a wheel, so this
can only
live in a test, never in either package's own code.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Final

from weft_eval.pricing import DEFAULT_RATES, RATES_AS_OF
from weft_openai.llm import DEFAULT_MODEL, MODEL_PINNED_AS_OF

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: The `provider:model` key `weft_eval.run_record.RunRecord.model_versions` and
#: `weft_eval.pricing.PricedCall` both speak. Built here rather than imported because neither
#: package may import the other — see the module docstring.
_OPENAI_PROVIDER: Final[str] = "openai"

#: An ISO date, and nothing looser. Both pins are read by a human deciding whether to re-check.
_ISO_DATE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Files permitted to name the pinned model as a bare literal. **Pinned empty.** Every caller
#: that needs the default imports it; a test that needs *some* model uses any other string, and
#: the several that already do (`model="m"`, `model="go"`) are the proof that nothing here needs
#: the real name. An entry is a dated decision in a diff, never a silent edit.
LITERAL_COPY_WAIVED: Final[frozenset[str]] = frozenset()


def _tracked_python_files() -> tuple[Path, ...]:
    """Every tracked `.py` file, from `git ls-files` — never a directory walk.

    `docs/internal/lessons.md` L8.8's scoping half: a walk finds build artefacts, virtualenvs and a
    stranger's checkout sitting in the tree, and a check that reads those is reporting on
    something other than this repository.
    """
    # `shutil.which` rather than a bare "git", on `test_ff17_citations_resolve.py`'s own
    # footing: ruff's S607 refuses a partial executable path, and it is right to.
    git = shutil.which("git")
    assert git is not None, "git is not on PATH, so this check cannot enumerate tracked files"
    listed = subprocess.run(  # noqa: S603 — a literal argv, no shell, nothing interpolated
        [git, "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    # `.is_file()`, on `test_ff17_citations_resolve.py`'s own footing: `git ls-files` lists a
    # path that is tracked, which is not the same as a path that is on disk right now — a
    # staged deletion, or a checkout mid-rebase, leaves an entry whose file is gone. Found by
    # planting a violation and deleting it again, where the sweep raised `FileNotFoundError`
    # instead of reporting nothing: a check that crashes on the state its own non-vacuity
    # exercise produces is a check nobody can safely demonstrate.
    return tuple(path for line in listed if line and (path := REPO_ROOT / line).is_file())


def test_the_default_chat_model_has_a_rate_so_a_real_run_can_be_priced() -> None:
    # `weft_eval.pricing.price_calls` does not fail for a model it has no rate for — it counts
    # the call in `unpriced_calls` and names the model in `unpriced_models`, which is the honest
    # behaviour for a *caller's* model. For the model this tree ships as its own default it is
    # the wrong outcome quietly: every run under the default would report a total excluding its
    # own calls, and V5's "the money and wall-clock cost of one full run" would be unanswerable
    # for the one configuration a user gets without choosing anything.
    key = f"{_OPENAI_PROVIDER}:{DEFAULT_MODEL}"

    assert key in DEFAULT_RATES, (
        f"the shipped default chat model is '{DEFAULT_MODEL}', and "
        f"weft_eval.pricing.DEFAULT_RATES has no '{key}' entry, so every run under the default "
        f"prices as unpriced. Rates present: {sorted(DEFAULT_RATES)}. Add the entry in the same "
        f"commit that moves the pin, and move RATES_AS_OF with it."
    )


def test_both_pinned_external_facts_carry_a_date() -> None:
    # Symmetry is the whole point: `RATES_AS_OF` already existed and `MODEL_PINNED_AS_OF` did
    # not, which is why one of the two could be reported as stale and the other could not.
    assert _ISO_DATE.match(RATES_AS_OF), f"RATES_AS_OF is not an ISO date: {RATES_AS_OF!r}"
    assert _ISO_DATE.match(MODEL_PINNED_AS_OF), (
        f"MODEL_PINNED_AS_OF is not an ISO date: {MODEL_PINNED_AS_OF!r}"
    )


def test_no_tracked_file_copies_the_pinned_model_as_a_literal() -> None:
    # Arrange — the copied-constant half of L8.13. `weft_openai/llm.py` is where the pin lives,
    # so it is the one file that must name it; every other caller imports it.
    home = REPO_ROOT / "packages" / "weft-rag" / "src" / "weft_openai" / "llm.py"
    literal = f'"{DEFAULT_MODEL}"'
    alt_literal = f"'{DEFAULT_MODEL}'"

    # Act
    copies: list[str] = []
    for path in _tracked_python_files():
        if path == home:
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in LITERAL_COPY_WAIVED:
            continue
        text = path.read_text(encoding="utf-8")
        if literal in text or alt_literal in text:
            copies.append(relative)

    # Assert
    assert not copies, (
        f"these files name the pinned default model '{DEFAULT_MODEL}' as a literal instead of "
        f"importing weft_openai.llm.DEFAULT_MODEL: {sorted(copies)}. A copy means repointing the "
        f"pin leaves them calling the old model — and for an integration test against a real "
        f"account, billing it. Import the constant, or use any other string where the test only "
        f"needs some model name."
    )


def test_the_copy_sweep_is_not_vacuous() -> None:
    # `docs/internal/lessons.md` L5.19 and L6.29: a sweep whose subject is legitimately empty passes
    # while matching nothing at all, and the two are indistinguishable from the green. The
    # non-vacuity question is not "is the literal present somewhere" — it is "does the sweep
    # fire on it" — so this plants the exact shape the real check looks for and asserts the
    # matcher finds it, rather than asserting anything about the tree.
    planted = f'    provider="openai", model="{DEFAULT_MODEL}",\n'

    assert f'"{DEFAULT_MODEL}"' in planted, (
        "the sweep's own matcher does not fire on a line that copies the pinned model, so a "
        "green from test_no_tracked_file_copies_the_pinned_model_as_a_literal would mean "
        "nothing is being looked at"
    )
    assert _tracked_python_files(), "git ls-files returned no Python files — the sweep read nothing"
